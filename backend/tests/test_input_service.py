from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from services.input_service import ingest_input_files


def _encode_bytes(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _load_test_font(size: int = 64):
    for candidate in (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\calibri.ttf"):
        font_path = Path(candidate)
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size)
    return ImageFont.load_default()


def _make_pptx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>Quarterly Update</a:t></a:r></a:p>
          <a:p><a:r><a:t>Goals and milestones</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
""",
        )
        archive.writestr(
            "ppt/slides/slide2.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>Next steps</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
""",
        )
    return buffer.getvalue()


def _make_xlsx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Summary" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
                Target="worksheets/sheet1.xml"/>
</Relationships>
""",
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="2" uniqueCount="2">
  <si><t>Quarterly</t></si>
  <si><t>Report</t></si>
</sst>
""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="s"><v>1</v></c>
      <c r="C1"><v>2026</v></c>
    </row>
    <row r="2">
      <c r="A2" t="inlineStr"><is><t>Completed</t></is></c>
      <c r="B2" t="n"><v>42</v></c>
    </row>
  </sheetData>
</worksheet>
""",
        )
    return buffer.getvalue()


def _make_docx_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>{text}</w:t></w:r></w:p>
  </w:body>
</w:document>
""",
        )
    return buffer.getvalue()


def _make_ocr_image_bytes(text: str) -> bytes:
    img = Image.new("RGB", (1600, 500), "white")
    draw = ImageDraw.Draw(img)
    font = _load_test_font()
    draw.text((40, 80), text, fill="black", font=font)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _make_scanned_pdf_bytes(text: str) -> bytes:
    with TemporaryDirectory() as td:
        td_path = Path(td)
        image_path = td_path / "scan.png"
        pdf_path = td_path / "scan.pdf"

        img = Image.new("RGB", (1600, 500), "white")
        draw = ImageDraw.Draw(img)
        font = _load_test_font()
        draw.text((40, 80), text, fill="black", font=font)
        img.save(image_path)

        pdf = canvas.Canvas(str(pdf_path), pagesize=letter)
        pdf.drawImage(str(image_path), 72, 500, width=420, height=110, mask="auto")
        pdf.showPage()
        pdf.save()

        return pdf_path.read_bytes()


def test_ingest_input_files_extracts_pptx_text() -> None:
    raw = _make_pptx_bytes()
    result = ingest_input_files(
        [
            {
                "filename": "sample.pptx",
                "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "contentBase64": _encode_bytes(raw),
                "role": "content",
            }
        ],
        max_chars=50_000,
    )

    assert result["summary"]["failed"] == 0
    assert result["summary"]["files"][0]["status"] == "processed"
    assert "Quarterly Update" in result["content_text"]
    assert "Goals and milestones" in result["content_text"]
    assert "Next steps" in result["content_text"]
    assert "PK" not in result["content_text"]


def test_ingest_input_files_extracts_xlsx_text() -> None:
    raw = _make_xlsx_bytes()
    result = ingest_input_files(
        [
            {
                "filename": "sample.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "contentBase64": _encode_bytes(raw),
                "role": "content",
            }
        ],
        max_chars=50_000,
    )

    assert result["summary"]["failed"] == 0
    assert result["summary"]["files"][0]["status"] == "processed"
    assert "Quarterly" in result["content_text"]
    assert "Report" in result["content_text"]
    assert "Completed" in result["content_text"]
    assert "42" in result["content_text"]
    assert "PK" not in result["content_text"]


def test_ingest_input_files_extracts_docx_text_when_python_docx_fails(monkeypatch) -> None:
    raw = _make_docx_bytes("Fallback Success")

    class FailingDocument:
        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr("services.input_service.Document", FailingDocument)

    result = ingest_input_files(
        [
            {
                "filename": "sample.docx",
                "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "contentBase64": _encode_bytes(raw),
                "role": "content",
            }
        ],
        max_chars=50_000,
    )

    assert result["summary"]["failed"] == 0
    assert result["summary"]["files"][0]["status"] == "processed"
    assert "Fallback Success" in result["content_text"]


def test_ingest_input_files_accepts_files_over_three_mb_limit() -> None:
    raw = b"A" * 3_500_000
    result = ingest_input_files(
        [
            {
                "filename": "large.txt",
                "mimeType": "text/plain",
                "contentBase64": _encode_bytes(raw),
                "role": "content",
            }
        ],
        max_chars=200,
    )

    assert result["summary"]["failed"] == 0
    assert result["summary"]["files"][0]["status"] == "processed"
    assert result["summary"]["files"][0]["bytes"] == len(raw)
    assert "AAAAAAAAAA" in result["content_text"]

def test_ingest_input_files_ocr_extracts_image_text() -> None:
    raw = _make_ocr_image_bytes("Hello OCR 123")
    result = ingest_input_files(
        [
            {
                "filename": "ocr.png",
                "mimeType": "image/png",
                "contentBase64": _encode_bytes(raw),
                "role": "content",
            }
        ],
        max_chars=20_000,
    )

    assert result["summary"]["failed"] == 0
    assert result["summary"]["files"][0]["status"] == "processed"
    assert "Hello OCR" in result["content_text"]
    assert "123" in result["content_text"]
    assert "OCR did not run" not in result["content_text"]


def test_ingest_input_files_ocr_extracts_scanned_pdf_text() -> None:
    raw = _make_scanned_pdf_bytes("Hello OCR 123")
    result = ingest_input_files(
        [
            {
                "filename": "scan.pdf",
                "mimeType": "application/pdf",
                "contentBase64": _encode_bytes(raw),
                "role": "content",
            }
        ],
        max_chars=20_000,
    )

    assert result["summary"]["failed"] == 0
    assert result["summary"]["files"][0]["status"] == "processed"
    assert "Hello OCR" in result["content_text"]
    assert "123" in result["content_text"]
