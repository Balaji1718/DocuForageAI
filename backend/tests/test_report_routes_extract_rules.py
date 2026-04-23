from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.report_routes import create_report_router


class FakeDoc:
    def __init__(self, doc_id: str):
        self.id = doc_id
        self.payload = {}

    def set(self, payload):
        self.payload.update(payload)


class FakeCollection:
    def __init__(self):
        self.docs = {}

    def document(self, doc_id: str | None = None):
        if doc_id is None:
            doc_id = f"doc_{len(self.docs) + 1}"
        doc = self.docs.get(doc_id)
        if doc is None:
            doc = FakeDoc(doc_id)
            self.docs[doc_id] = doc
        return doc


class FakeDB:
    def __init__(self):
        self.collections = {"document_rules": FakeCollection()}

    def collection(self, name):
        return self.collections[name]


def _verify_token():
    return {"uid": "u1"}


def _minimal_docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Reference</w:t></w:r></w:p>
  </w:body>
</w:document>
""",
        )
        archive.writestr(
            "word/styles.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>
""",
        )
        archive.writestr(
            "word/numbering.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>
""",
        )
    return buffer.getvalue()


def test_extract_rules_accepts_reference_field(monkeypatch):
    app = FastAPI()
    db = FakeDB()
    out_dir = Path(__file__).parent / "_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "routes.report_routes.extract_rules",
        lambda content, source_filename="": {
            "page_width_dxa": 11906,
            "page_height_dxa": 16838,
            "margin_top_dxa": 1440,
            "margin_bottom_dxa": 1440,
            "margin_left_dxa": 1800,
            "margin_right_dxa": 1440,
            "margin_header_dxa": 720,
            "margin_footer_dxa": 720,
            "body_font": "Times New Roman",
            "body_size_halfpt": 24,
            "body_line_spacing_val": 360,
            "body_line_spacing_rule": "auto",
            "body_space_before": 0,
            "body_space_after": 120,
            "body_alignment": "both",
            "body_first_line_indent_dxa": 0,
            "headings": {},
            "has_page_numbers": True,
            "page_number_alignment": "center",
            "prelim_page_format": "lowerRoman",
            "body_page_format": "decimal",
            "page_number_section_restart": False,
            "section_count": 1,
            "has_cover_section": False,
            "has_prelim_section": False,
            "has_body_section": True,
            "sections_have_different_margins": False,
            "detected_section_headings": [],
            "has_toc": False,
            "has_numbered_lists": False,
            "has_bulleted_lists": False,
            "table_count": 0,
            "tables_use_borders": True,
            "image_count": 0,
            "has_cover_image": False,
            "has_markdown_leak": False,
            "has_xml_artifact_numbers": False,
            "has_mixed_fonts": False,
            "font_substitution_detected": False,
            "source_filename": source_filename,
            "extraction_warnings": [],
            "confidence": "high",
        },
    )

    app.include_router(
        create_report_router(
            db=db,
            output_dir=out_dir,
            max_content_chars=200000,
            verify_token=lambda: _verify_token(),
        )
    )

    client = TestClient(app)
    response = client.post(
        "/extract-rules",
        files={"reference": ("sample.docx", _minimal_docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rules_id"]
    assert body["rules"]["body_font"] == "Times New Roman"
    assert body["success"] is True
