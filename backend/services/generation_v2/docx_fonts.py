from __future__ import annotations

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.run import Run


def apply_run_font_override(run: Run, font_name: str) -> None:
    if not font_name.strip():
        raise ValueError("font_name must be non-empty")

    run.font.name = font_name

    r_pr = run._r.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.append(r_fonts)

    # Explicitly set all script buckets so Word/LibreOffice do not fall back to theme fonts.
    r_fonts.set(qn("w:ascii"), font_name)
    r_fonts.set(qn("w:hAnsi"), font_name)
    r_fonts.set(qn("w:eastAsia"), font_name)
    r_fonts.set(qn("w:cs"), font_name)
