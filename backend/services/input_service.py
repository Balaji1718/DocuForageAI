from __future__ import annotations

import base64
import json
import logging
import os
import re
import zipfile
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from docx import Document

log = logging.getLogger("docuforge.input.service")
PPTX_NAMESPACES = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
XLSX_NAMESPACES = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
DOCX_NAMESPACES = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
PPTX_EXTENSIONS = {".pptx", ".pptm", ".ppsx"}
XLSX_EXTENSIONS = {".xlsx", ".xlsm", ".xltx", ".xltm"}
TRUE_VALUES = {"1", "true", "yes", "on"}


def _decode_file(payload_b64: str) -> bytes:
    try:
        return base64.b64decode(payload_b64, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid base64 file payload: {exc}") from exc


def _bytes_to_text(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _extract_docx_xml_text(xml_bytes: bytes) -> str:
    try:
        root = ET.fromstring(xml_bytes)
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to parse DOCX XML: %s", exc)
        return ""

    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", DOCX_NAMESPACES):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", DOCX_NAMESPACES)).strip()
        if text:
            paragraphs.append(text)

    return "\n".join(paragraphs).strip()


def _extract_docx_text(raw: bytes) -> str:
    primary_error: Exception | None = None

    try:
        document = Document(BytesIO(raw))
        extracted = "\n".join([p.text for p in document.paragraphs if p.text.strip()]).strip()
        if extracted:
            return extracted
    except Exception as exc:  # noqa: BLE001
        primary_error = exc
        log.warning("python-docx extraction failed: %s", exc)

    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            archive_names = archive.namelist()
            available_names = set(archive_names)
            candidate_names = ["word/document.xml"]
            candidate_names.extend(
                name for name in archive_names if re.fullmatch(r"word/(?:header|footer)\d+\.xml", name)
            )
            candidate_names.extend(
                name for name in archive_names if re.fullmatch(r"word/(?:footnotes|endnotes|comments)\.xml", name)
            )

            sections: list[str] = []
            for part_name in candidate_names:
                if part_name not in available_names:
                    continue
                part_text = _extract_docx_xml_text(archive.read(part_name))
                if part_text:
                    sections.append(part_text)

            extracted = "\n\n".join(sections).strip()
            if extracted:
                if primary_error is not None:
                    log.warning("Recovered DOCX text via direct OOXML parsing after python-docx failure.")
                return extracted
    except Exception as exc:  # noqa: BLE001
        if primary_error is not None:
            return f"[DOCX extraction failed: {primary_error}; fallback failed: {exc}]"
        return f"[DOCX extraction failed: {exc}]"

    if primary_error is not None:
        return f"[DOCX extraction failed: {primary_error}]"
    return "[DOCX parsed, but no extractable text was found.]"


@lru_cache(maxsize=1)
def _get_ocr_reader() -> Any | None:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:  # noqa: BLE001
        log.warning("RapidOCR is unavailable: %s", exc)
        return None

    try:
        return RapidOCR()
    except Exception as exc:  # noqa: BLE001
        log.warning("RapidOCR initialization failed: %s", exc)
        return None


def _ocr_is_enabled() -> bool:
    raw = os.getenv("OCR_ENABLED")
    if raw is None:
        return _get_ocr_reader() is not None
    return raw.strip().lower() in TRUE_VALUES


def _ocr_result_lines(result: Any) -> list[str]:
    lines: list[str] = []
    if not result:
        return lines

    for item in result:
        if not item or len(item) < 2:
            continue
        text = str(item[1] or "").strip()
        if text:
            lines.append(text)
    return lines


def _zip_member_sort_key(name: str) -> tuple[int, str]:
    match = re.search(r"(\d+)(?=\.xml$)", name)
    if match:
        return int(match.group(1)), name
    return (10**9, name)


def _extract_pptx_text(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            slide_names = sorted(
                [name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)],
                key=_zip_member_sort_key,
            )
            sections: list[str] = []

            for slide_name in slide_names:
                try:
                    root = ET.fromstring(archive.read(slide_name))
                except Exception as exc:  # noqa: BLE001
                    log.warning("Failed to parse PPTX slide %s: %s", slide_name, exc)
                    continue

                paragraphs: list[str] = []
                for paragraph in root.findall(".//a:p", PPTX_NAMESPACES):
                    text = "".join(node.text or "" for node in paragraph.findall(".//a:t", PPTX_NAMESPACES)).strip()
                    if text:
                        paragraphs.append(text)

                if paragraphs:
                    slide_number_match = re.search(r"slide(\d+)\.xml$", slide_name)
                    slide_label = f"Slide {int(slide_number_match.group(1))}" if slide_number_match else slide_name
                    sections.append(f"### {slide_label}\n" + "\n".join(paragraphs))

            extracted = "\n\n".join(sections).strip()
            if extracted:
                return extracted
            return "[PPTX parsed, but no extractable text was found.]"
    except Exception as exc:  # noqa: BLE001
        return f"[PPTX extraction failed: {exc}]"


def _read_xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []

    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to parse XLSX shared strings: %s", exc)
        return []

    strings: list[str] = []
    for shared_item in root.findall("main:si", XLSX_NAMESPACES):
        text = "".join(node.text or "" for node in shared_item.findall(".//main:t", XLSX_NAMESPACES)).strip()
        strings.append(text)
    return strings


def _resolve_xlsx_sheet_paths(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    sheet_paths: list[tuple[str, str]] = []

    workbook_name = "xl/workbook.xml"
    rels_name = "xl/_rels/workbook.xml.rels"
    if workbook_name in archive.namelist() and rels_name in archive.namelist():
        try:
            workbook_root = ET.fromstring(archive.read(workbook_name))
            rels_root = ET.fromstring(archive.read(rels_name))
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to parse XLSX workbook metadata: %s", exc)
        else:
            rel_targets = {
                rel.get("Id"): rel.get("Target")
                for rel in rels_root.findall("pkgrel:Relationship", XLSX_NAMESPACES)
                if rel.get("Id") and rel.get("Target")
            }
            for sheet in workbook_root.findall(".//main:sheets/main:sheet", XLSX_NAMESPACES):
                sheet_name = str(sheet.get("name") or "Sheet").strip() or "Sheet"
                rel_id = sheet.get(f"{{{XLSX_NAMESPACES['rel']}}}id")
                target = rel_targets.get(rel_id or "")
                if not target:
                    continue
                normalized_target = target.lstrip("/")
                if normalized_target.startswith("../"):
                    normalized_target = normalized_target.replace("../", "", 1)
                if not normalized_target.startswith("xl/"):
                    normalized_target = f"xl/{normalized_target}"
                sheet_paths.append((sheet_name, normalized_target))

    if sheet_paths:
        return sheet_paths

    # Fallback for minimal or nonstandard XLSX archives in tests/exports.
    for candidate in sorted(archive.namelist()):
        if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", candidate):
            sheet_label = Path(candidate).stem
            sheet_paths.append((sheet_label, candidate))

    return sheet_paths


def _extract_xlsx_text(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            shared_strings = _read_xlsx_shared_strings(archive)
            sheet_paths = _resolve_xlsx_sheet_paths(archive)
            sections: list[str] = []

            for sheet_name, sheet_path in sheet_paths:
                try:
                    root = ET.fromstring(archive.read(sheet_path))
                except Exception as exc:  # noqa: BLE001
                    log.warning("Failed to parse XLSX sheet %s: %s", sheet_path, exc)
                    continue

                rows: list[str] = []
                for row in root.findall(".//main:sheetData/main:row", XLSX_NAMESPACES):
                    cells: list[str] = []
                    for cell in row.findall("main:c", XLSX_NAMESPACES):
                        cell_type = str(cell.get("t") or "").strip()
                        value = ""

                        if cell_type == "inlineStr":
                            value = "".join(node.text or "" for node in cell.findall(".//main:is//main:t", XLSX_NAMESPACES)).strip()
                        elif cell_type == "s":
                            raw_index = cell.findtext("main:v", default="", namespaces=XLSX_NAMESPACES).strip()
                            try:
                                index = int(raw_index)
                                value = shared_strings[index] if 0 <= index < len(shared_strings) else raw_index
                            except ValueError:
                                value = raw_index
                        else:
                            value = cell.findtext("main:v", default="", namespaces=XLSX_NAMESPACES).strip()
                            if cell_type == "b":
                                value = "TRUE" if value in {"1", "true", "TRUE"} else "FALSE"

                        if value:
                            cells.append(value)

                    row_text = "\t".join(cells).strip()
                    if row_text:
                        rows.append(row_text)

                if rows:
                    sections.append(f"### Sheet: {sheet_name}\n" + "\n".join(rows))

            extracted = "\n\n".join(sections).strip()
            if extracted:
                return extracted
            return "[XLSX parsed, but no extractable text was found.]"
    except Exception as exc:  # noqa: BLE001
        return f"[XLSX extraction failed: {exc}]"


def _extract_pdf_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return "[PDF file received, but PDF text extraction is unavailable because pypdf is not installed.]"

    try:
        reader = PdfReader(BytesIO(raw))
        chunks: list[str] = []
        for page in reader.pages:
            text = (page.extract_text() or "").strip()
            if text:
                chunks.append(text)
        extracted = "\n\n".join(chunks)
        if extracted.strip() or not _ocr_is_enabled():
            return extracted

        ocr_text = _extract_scanned_pdf_text(raw)
        if ocr_text.strip():
            return ocr_text
        return "[PDF parsed, but no extractable text was found after OCR.]"
    except Exception as exc:  # noqa: BLE001
        return f"[PDF extraction failed: {exc}]"


def _ocr_image_bytes(raw: bytes) -> str:
    if not _ocr_is_enabled():
        return ""

    reader = _get_ocr_reader()
    if reader is None:
        return ""

    try:
        result, _elapsed = reader(raw)
        return "\n".join(_ocr_result_lines(result)).strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("Image OCR failed: %s", exc)
        return ""


def _extract_scanned_pdf_text(raw: bytes) -> str:
    if not _ocr_is_enabled():
        return ""
    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    out: list[str] = []
    try:
        reader = PdfReader(BytesIO(raw))
        for page in reader.pages:
            images = getattr(page, "images", []) or []
            for image in images:
                text = _ocr_image_bytes(getattr(image, "data", b""))
                if text:
                    out.append(text)
    except Exception as exc:  # noqa: BLE001
        log.warning("Scanned PDF OCR failed: %s", exc)

    return "\n\n".join(out)


def _extract_by_type(filename: str, mime_type: str, raw: bytes) -> str:
    ext = Path(filename).suffix.lower()
    mt = (mime_type or "").lower()

    if mt.startswith("text/") or ext in {".txt", ".md", ".csv", ".html", ".htm", ".xml", ".yaml", ".yml"}:
        return _bytes_to_text(raw)

    if mt == "application/json" or ext == ".json":
        decoded = _bytes_to_text(raw)
        try:
            parsed = json.loads(decoded)
            return json.dumps(parsed, indent=2)
        except json.JSONDecodeError:
            return decoded

    if mt in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    } or ext in {".docx", ".doc"}:
        return _extract_docx_text(raw)

    if mt in {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.ms-powerpoint.presentation.macroenabled.12",
        "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
    } or ext in PPTX_EXTENSIONS:
        return _extract_pptx_text(raw)

    if mt in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel.sheet.macroenabled.12",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
    } or ext in XLSX_EXTENSIONS:
        return _extract_xlsx_text(raw)

    if mt == "application/pdf" or ext == ".pdf":
        return _extract_pdf_text(raw)

    if mt.startswith("image/") or ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}:
        ocr_text = _ocr_image_bytes(raw)
        if ocr_text.strip():
            return ocr_text
        return (
            f"[Image file '{filename}' received ({mime_type or 'unknown mime'}). "
            "OCR did not run or returned no text, so only file metadata is included.]"
        )

    # Final fallback: try text decode; if unusable, provide metadata only.
    as_text = _bytes_to_text(raw).strip()
    if as_text:
        return as_text
    return f"[Unsupported binary file '{filename}' received; no extractable text content.]"


def ingest_input_files(
    files: list[dict[str, Any]] | None,
    max_chars: int,
    max_file_bytes: int = 50_000_000,
) -> dict[str, Any]:
    if not files:
        return {
            "content_text": "",
            "reference_text": "",
            "summary": {"processed": 0, "failed": 0, "files": []},
        }

    content_parts: list[str] = []
    reference_parts: list[str] = []
    summary_files: list[dict[str, Any]] = []
    failed = 0

    for item in files:
        filename = str(item.get("filename") or "unnamed")[:260]
        mime_type = str(item.get("mimeType") or "application/octet-stream")[:200]
        role = str(item.get("role") or "content").lower().strip()
        payload_b64 = str(item.get("contentBase64") or "")

        try:
            raw = _decode_file(payload_b64)
            if len(raw) > max_file_bytes:
                raise ValueError(f"File '{filename}' is too large; limit is {max_file_bytes} bytes")

            text = _extract_by_type(filename, mime_type, raw)
            block = f"\n\n### Source File: {filename}\n{text.strip()}\n"

            if role == "reference":
                reference_parts.append(block)
            else:
                content_parts.append(block)

            summary_files.append(
                {
                    "filename": filename,
                    "mimeType": mime_type,
                    "role": role,
                    "bytes": len(raw),
                    "status": "processed",
                }
            )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            msg = str(exc)
            log.warning("Failed to ingest file %s: %s", filename, msg)
            summary_files.append(
                {
                    "filename": filename,
                    "mimeType": mime_type,
                    "role": role,
                    "status": "failed",
                    "error": msg,
                }
            )

    content_text = "\n".join(content_parts).strip()
    reference_text = "\n".join(reference_parts).strip()

    if len(content_text) > max_chars:
        content_text = content_text[:max_chars]

    if len(reference_text) > max_chars:
        reference_text = reference_text[:max_chars]

    return {
        "content_text": content_text,
        "reference_text": reference_text,
        "summary": {
            "processed": len(summary_files) - failed,
            "failed": failed,
            "files": summary_files,
        },
    }
