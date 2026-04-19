from __future__ import annotations

import pytest

from services.orchestration_service import run_generation_pipeline


def test_retry_skipped_when_improvement_unlikely(monkeypatch, tmp_path):
    generate_calls = {"count": 0}
    correction_calls = {"count": 0}

    monkeypatch.setattr(
        "services.orchestration_service.ingest_input_files",
        lambda input_files, max_chars: {"summary": {"processed": 0, "failed": 0, "files": []}, "content_text": "", "reference_text": ""},
    )
    monkeypatch.setattr(
        "services.orchestration_service.generate_structured_text",
        lambda **kwargs: (
            "# Introduction\nGood intro\n\n## Body\nGood body content with details\n\n## Conclusion\nGood conclusion",
            {"compiled": {}},
            {"enabled": False},
            {"ok": True, "errors": [], "qualityScore": 90.0},
        ),
    )
    monkeypatch.setattr(
        "services.orchestration_service.build_document_model",
        lambda **kwargs: {"blocks": [{"id": "root", "type": "document", "text": "x"}], "stats": {"totalBlocks": 1}},
    )
    monkeypatch.setattr(
        "services.orchestration_service.plan_layout_with_acceptance",
        lambda **kwargs: {
            "layoutPlan": {"placements": [{"page": 1}], "totalPages": 1, "pageCapacityLines": 48},
            "preRenderSimulation": {"ok": True, "accepted": True, "layoutSimilarityProxy": 95.0},
            "layoutCorrections": [],
        },
    )

    def _fake_generate_documents(**kwargs):
        generate_calls["count"] += 1
        return "/files/r.pdf", "/files/r.docx"

    monkeypatch.setattr("services.orchestration_service.generate_documents", _fake_generate_documents)

    monkeypatch.setattr(
        "services.orchestration_service.validate_rendered_artifacts",
        lambda **kwargs: {
            "accepted": False,
            "issues": ["non-fixable renderer crash signature"],
            "similarity": {"aggregate": 70.0, "headingMatchRatio": 0.5},
            "visual": {"averageScore": 70.0},
            "suggestions": [],
        },
    )

    def _fake_correct_layout_from_render_feedback(**kwargs):
        correction_calls["count"] += 1
        return kwargs

    monkeypatch.setattr("services.orchestration_service.correct_layout_from_render_feedback", _fake_correct_layout_from_render_feedback)

    with pytest.raises(ValueError, match="RENDER_VALIDATION"):
        run_generation_pipeline(
            report_id="r1",
            title="Title",
            rules="Rules",
            content="Content",
            reference_content="",
            reference_mime_type="text/plain",
            input_files=[],
            max_content_chars=200000,
            output_dir=tmp_path,
        )

    # Initial generation should happen once, retry loop should skip correction path.
    assert generate_calls["count"] == 1
    assert correction_calls["count"] == 0
