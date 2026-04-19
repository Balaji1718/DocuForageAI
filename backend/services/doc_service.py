from __future__ import annotations

import logging
from pathlib import Path

from doc_generator import build_docx, build_pdf

log = logging.getLogger("docuforge.doc.service")


def generate_documents(
    report_id: str,
    title: str,
    rules: str,
    structured_text: str,
    output_dir: Path,
) -> tuple[str, str]:
    docx_path = output_dir / f"{report_id}.docx"
    pdf_path = output_dir / f"{report_id}.pdf"

    log.info("Generating DOCX/PDF for report %s", report_id)
    build_docx(title, rules, structured_text, docx_path)
    build_pdf(title, rules, structured_text, pdf_path)

    return f"/files/{report_id}.pdf", f"/files/{report_id}.docx"
