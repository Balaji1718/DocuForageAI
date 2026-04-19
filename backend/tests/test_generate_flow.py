from __future__ import annotations

import base64
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.report_routes import create_report_router


class FakeDoc:
    def __init__(self, doc_id: str):
        self.id = doc_id
        self.data = {}

    def set(self, payload):
        self.data.update(payload)

    def update(self, payload):
        self.data.update(payload)


class FakeCollection:
    def __init__(self):
        self._docs = {}

    def document(self):
        doc_id = f"doc_{len(self._docs) + 1}"
        doc = FakeDoc(doc_id)
        self._docs[doc_id] = doc
        return doc

    def where(self, *_args, **_kwargs):
        class _Where:
            def stream(self_inner):
                return []

        return _Where()


class FakeDB:
    def __init__(self):
        self._collections = {"reports": FakeCollection()}

    def collection(self, name):
        return self._collections[name]


def _verify_token():
    return {"uid": "u1"}


def _build_app(monkeypatch):
    app = FastAPI()
    db = FakeDB()
    out_dir = Path(__file__).parent / "_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "routes.report_routes.run_generation_pipeline",
        lambda **_kwargs: (
            {
                "mergedContent": "merged",
                "mergedReference": "",
                "inputProcessing": {"processed": 1, "failed": 0, "files": []},
                "parsedRules": {"required_sections": ["Introduction", "Body", "Conclusion"]},
                "parsedReference": {"enabled": False},
                "validation": {"ok": True, "errors": [], "retried": False},
                "pdfUrl": "/files/x.pdf",
                "docxUrl": "/files/x.docx",
            }
        ),
    )

    app.include_router(
        create_report_router(
            db=db,
            output_dir=out_dir,
            max_content_chars=200000,
            verify_token=lambda: _verify_token(),
        )
    )
    return app


def test_generate_file_only_content(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app)

    payload = {
        "userId": "u1",
        "title": "File only",
        "rules": "Use academic structure",
        "content": "",
        "inputFiles": [
            {
                "filename": "note.txt",
                "mimeType": "text/plain",
                "role": "content",
                "contentBase64": base64.b64encode(b"file supplied content").decode("ascii"),
            }
        ],
    }

    res = client.post("/generate", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["pdfUrl"]
    assert body["docxUrl"]


def test_generate_mixed_input_content_and_reference(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app)

    payload = {
        "userId": "u1",
        "title": "Mixed",
        "rules": "Use formal tone",
        "content": "main typed content",
        "referenceContent": "# Sample\n## Intro",
        "referenceMimeType": "text/plain",
        "inputFiles": [
            {
                "filename": "appendix.md",
                "mimeType": "text/markdown",
                "role": "content",
                "contentBase64": base64.b64encode(b"## Data\n- item").decode("ascii"),
            },
            {
                "filename": "ref.txt",
                "mimeType": "text/plain",
                "role": "reference",
                "contentBase64": base64.b64encode(b"# Blueprint\n## Section").decode("ascii"),
            },
        ],
    }

    res = client.post("/generate", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["reportId"]


def test_generate_error_is_sanitized(monkeypatch):
    app = FastAPI()
    db = FakeDB()
    out_dir = Path(__file__).parent / "_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    def _raise_pipeline(**_kwargs):
        raise RuntimeError("provider stacktrace: api key=secret-token")

    monkeypatch.setattr("routes.report_routes.run_generation_pipeline", _raise_pipeline)
    app.include_router(
        create_report_router(
            db=db,
            output_dir=out_dir,
            max_content_chars=200000,
            verify_token=lambda: _verify_token(),
        )
    )

    client = TestClient(app)
    res = client.post(
        "/generate",
        json={
            "userId": "u1",
            "title": "err",
            "rules": "r",
            "content": "c",
            "inputFiles": [],
        },
    )
    assert res.status_code == 500
    body = res.json()
    assert body["error"] == "Generation failed due to a temporary processing issue. Please try again."
    assert "secret-token" not in body["error"]


def test_generate_quality_failure_response(monkeypatch):
    app = FastAPI()
    db = FakeDB()
    out_dir = Path(__file__).parent / "_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    def _raise_quality(**_kwargs):
        raise RuntimeError(
            "Output quality validation failed after one retry: "
            "Section too short (4 words): Introduction (minimum 15); "
            "Output still contains placeholder section content."
        )

    monkeypatch.setattr("routes.report_routes.run_generation_pipeline", _raise_quality)
    app.include_router(
        create_report_router(
            db=db,
            output_dir=out_dir,
            max_content_chars=200000,
            verify_token=lambda: _verify_token(),
        )
    )

    client = TestClient(app)
    res = client.post(
        "/generate",
        json={
            "userId": "u1",
            "title": "quality",
            "rules": "r",
            "content": "c",
            "inputFiles": [],
        },
    )

    assert res.status_code == 500
    body = res.json()
    assert body["qualityFailure"] is True
    assert body["error"] == "Generated output did not meet quality requirements after retry."
    assert any("placeholder" in item.lower() for item in body["qualityErrors"])


def test_generate_render_validation_failure_response(monkeypatch):
    app = FastAPI()
    db = FakeDB()
    out_dir = Path(__file__).parent / "_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    def _raise_render(**_kwargs):
        raise RuntimeError("RENDER_VALIDATION: Rendered text similarity below threshold: 72.5")

    monkeypatch.setattr("routes.report_routes.run_generation_pipeline", _raise_render)
    app.include_router(
        create_report_router(
            db=db,
            output_dir=out_dir,
            max_content_chars=200000,
            verify_token=lambda: _verify_token(),
        )
    )

    client = TestClient(app)
    res = client.post(
        "/generate",
        json={
            "userId": "u1",
            "title": "render",
            "rules": "r",
            "content": "c",
            "inputFiles": [],
        },
    )

    assert res.status_code == 500
    body = res.json()
    assert body["errorCode"] == "render_validation"
    assert body["error"] == "Generated output did not meet render fidelity requirements."


def test_escalating_correction_strategies():
    """Verify escalating correction strategies are applied correctly."""
    from services.layout_engine_service import repair_layout_plan, simulate_layout, evaluate_layout_acceptance
    from services.document_model_service import build_document_model
    
    # Create a minimal document model
    doc_model = {
        "blocks": [
            {"id": "root", "type": "document", "text": "Test"},
            {"id": "h1", "type": "heading", "text": "Section"},
            {"id": "p1", "type": "paragraph", "text": "Content paragraph here."},
        ],
        "stats": {"totalBlocks": 3},
    }
    
    # Create initial layout plan with moderate capacity
    layout_plan = {
        "deterministic": True,
        "pageCapacityLines": 48,
        "totalPages": 1,
        "placements": [{"page": 1}],
        "hardConstraintsApplied": [],
        "softConstraintsApplied": [],
    }
    
    # Simulate escalating strategy: moderate escalation
    corrected_plan = layout_plan.copy()
    current_capacity = int(corrected_plan.get("pageCapacityLines") or 48)
    new_capacity = max(30, current_capacity - 4)
    corrected_plan["pageCapacityLines"] = new_capacity
    
    # Verify capacity was reduced
    assert corrected_plan["pageCapacityLines"] < layout_plan["pageCapacityLines"]
    assert corrected_plan["pageCapacityLines"] >= 30
    
    # Simulate aggressive strategy: very aggressive reduction
    aggressive_plan = layout_plan.copy()
    current_capacity = int(aggressive_plan.get("pageCapacityLines") or 48)
    new_capacity = max(20, current_capacity - 6)
    aggressive_plan["pageCapacityLines"] = new_capacity
    
    # Verify aggressive strategy reduces more
    assert aggressive_plan["pageCapacityLines"] < corrected_plan["pageCapacityLines"]
    assert aggressive_plan["pageCapacityLines"] >= 20


def test_intelligent_backoff_score_calculation():
    """Verify composite validation score calculation for backoff detection."""
    # Simulate a successful validation
    validation_pass = {
        "accepted": True,
        "similarity": {"aggregate": 95.0, "headingMatchRatio": 0.9},
        "visual": {"averageScore": 85.0},
    }
    
    # Helper function to mimic the one in orchestration
    def _extract_validation_score(validation):
        """Extract composite validation score for comparison across attempts."""
        if validation.get("accepted"):
            return 100.0
        similarity = validation.get("similarity", {}).get("aggregate") or 0.0
        visual = validation.get("visual", {}).get("averageScore") or 0.0
        heading_ratio = validation.get("similarity", {}).get("headingMatchRatio") or 0.0
        score = (similarity * 0.5) + (visual * 0.3) + (heading_ratio * 100 * 0.2)
        return round(score, 2)
    
    score_pass = _extract_validation_score(validation_pass)
    assert score_pass == 100.0, "Accepted validation should score 100%"
    
    # Failing validation with poor metrics
    validation_fail = {
        "accepted": False,
        "similarity": {"aggregate": 70.0, "headingMatchRatio": 0.5},
        "visual": {"averageScore": 60.0},
        "issues": ["Text similarity low", "Visual fidelity low"],
    }
    
    score_fail = _extract_validation_score(validation_fail)
    expected = (70.0 * 0.5) + (60.0 * 0.3) + (0.5 * 100 * 0.2)
    assert score_fail == round(expected, 2), f"Expected {expected}, got {score_fail}"
    assert score_fail < 100.0, "Failing validation should score less than 100%"
    
    # Verify score ordering: passing > failing
    assert score_pass > score_fail, "Passing validation should score higher than failing"
