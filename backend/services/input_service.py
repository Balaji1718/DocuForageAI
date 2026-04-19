from __future__ import annotations

import base64
import json
import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document

log = logging.getLogger("docuforge.input.service")
OCR_ENABLED = os.getenv("OCR_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


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


def _extract_docx_text(raw: bytes) -> str:
    document = Document(BytesIO(raw))
    return "\n".join([p.text for p in document.paragraphs if p.text.strip()])


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
        if extracted.strip() or not OCR_ENABLED:
            return extracted

        ocr_text = _extract_scanned_pdf_text(raw)
        if ocr_text.strip():
            return ocr_text
        return "[PDF parsed, but no extractable text was found.]"
    except Exception as exc:  # noqa: BLE001
        return f"[PDF extraction failed: {exc}]"


def _ocr_image_bytes(raw: bytes) -> str:
    if not OCR_ENABLED:
        return ""

    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return ""

    try:
        image = Image.open(BytesIO(raw))
        return (pytesseract.image_to_string(image) or "").strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("Image OCR failed: %s", exc)
        return ""


def _extract_scanned_pdf_text(raw: bytes) -> str:
    if not OCR_ENABLED:
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
    max_file_bytes: int = 3_000_000,
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
