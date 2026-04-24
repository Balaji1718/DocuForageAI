from __future__ import annotations

import re
from typing import Any


def is_style_reference_rules(reference_rules: dict[str, Any] | None) -> bool:
    if not reference_rules:
        return False

    if str(reference_rules.get("source_filename") or "").strip():
        return True
    if int(reference_rules.get("footer_count") or 0) > 0:
        return True
    if int(reference_rules.get("header_count") or 0) > 0:
        return True
    if int(reference_rules.get("section_count") or 0) > 0:
        return True
    if int(reference_rules.get("table_count") or 0) > 0:
        return True
    if int(reference_rules.get("image_count") or 0) > 0:
        return True
    if reference_rules.get("detected_section_headings"):
        return True
    return False


def _extract_headings(reference_text: str) -> list[dict[str, Any]]:
    headings: list[dict[str, Any]] = []
    numbered = re.compile(r"^(\d+(?:\.\d+)*)\s*[-.)]?\s+(.+)$")

    for raw_line in reference_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("### "):
            headings.append({"level": 3, "title": line[4:].strip()})
            continue
        if line.startswith("## "):
            headings.append({"level": 2, "title": line[3:].strip()})
            continue
        if line.startswith("# "):
            headings.append({"level": 1, "title": line[2:].strip()})
            continue

        match = numbered.match(line)
        if match:
            token = match.group(1)
            title = match.group(2).strip()
            level = min(4, token.count(".") + 1)
            headings.append({"level": level, "title": title})
            continue

        # Short all-caps line often indicates a section heading in academic references.
        if len(line) <= 80 and line.upper() == line and any(char.isalpha() for char in line):
            headings.append({"level": 2, "title": line.title()})
            continue

        if len(line) <= 90 and line.endswith(":"):
            headings.append({"level": 3, "title": line.rstrip(":")})

    return headings


def parse_reference_content(
    reference_content: str | None,
    reference_mime_type: str | None = None,
) -> dict[str, Any]:
    content = (reference_content or "").strip()
    mime = (reference_mime_type or "").strip().lower()

    if not content:
        return {
            "enabled": False,
            "mimeType": mime or "text/plain",
            "headings": [],
            "section_order": [],
            "style": {},
            "notes": "No reference content provided.",
        }

    headings = _extract_headings(content)
    style = {
        "uses_markdown_headings": "# " in content,
        "uses_numbered_sections": bool(re.search(r"^\d+(?:\.\d+)*\s", content, flags=re.MULTILINE)),
        "uses_bullets": bool(re.search(r"^\s*[-*•]\s+", content, flags=re.MULTILINE)),
        "avg_heading_level": round(
            sum(int(h.get("level") or 1) for h in headings) / len(headings),
            2,
        )
        if headings
        else 0,
    }

    notes = "Reference structure extracted from text."
    if mime.startswith("image/"):
        notes = (
            "Image MIME type received. Structure extraction is based only on provided text payload; "
            "no OCR was applied."
        )

    return {
        "enabled": True,
        "mimeType": mime or "text/plain",
        "headings": headings[:30],
        "section_order": [str(h.get("title") or "").strip() for h in headings[:30] if h.get("title")],
        "style": style,
        "notes": notes,
    }


def build_reference_guidance(reference_json: dict[str, Any]) -> str:
    if not reference_json or not reference_json.get("enabled"):
        return "No reference alignment requested."

    order = reference_json.get("section_order") or []
    style = reference_json.get("style") or {}
    headings = reference_json.get("headings") or []

    lines = [
        "Use the reference only for organization and formatting similarity.",
        "Do not copy wording, sentences, or unique phrasing from the reference.",
        "Preserve user-provided facts and content as the source of truth.",
        f"Target section order: {', '.join(order) if order else 'No explicit order detected'}",
        "Style cues:",
        f"- Markdown headings: {'yes' if style.get('uses_markdown_headings') else 'no'}",
        f"- Numbered sections: {'yes' if style.get('uses_numbered_sections') else 'no'}",
        f"- Bullet usage: {'yes' if style.get('uses_bullets') else 'no'}",
    ]

    if headings:
        lines.append("Reference heading blueprint:")
        for heading in headings[:12]:
            lines.append(f"- H{int(heading.get('level') or 1)}: {str(heading.get('title') or 'Untitled')}")

    return "\n".join(lines)


def build_style_reference_guidance(reference_rules: dict[str, Any] | None) -> str:
    if not is_style_reference_rules(reference_rules):
        return "No DOCX style reference provided."

    rules = reference_rules or {}
    headings = [str(item).strip() for item in (rules.get("detected_section_headings") or []) if str(item).strip()]
    body_size = rules.get("body_size_halfpt")
    body_size_pt = round(float(body_size) / 2.0, 1) if body_size else "unknown"
    title_size = rules.get("cover_title_size_pt")
    subtitle_size = rules.get("cover_subtitle_size_pt")
    left_indent = rules.get("body_left_indent_dxa")
    first_line = rules.get("body_first_line_indent_dxa")
    right_indent = rules.get("body_right_indent_dxa")
    list_indent = rules.get("list_left_indent_pt")
    page_format = str(rules.get("prelim_page_format") or "lowerRoman")
    body_page_format = str(rules.get("body_page_format") or "decimal")

    lines = [
        "DOCX STYLE BLUEPRINT:",
        "- Use the uploaded DOCX only as a structural and visual reference, not as wording to copy.",
        f"- Body font: {rules.get('body_font') or 'Times New Roman'}",
        f"- Body size: {body_size_pt}pt",
        f"- Body alignment: {rules.get('body_alignment') or 'both'}",
        f"- Body line spacing: {rules.get('body_line_spacing_val') or 360}",
        f"- Body indents: left {left_indent or 'n/a'} dxa, first-line {first_line or 'n/a'} dxa, right {right_indent or 'n/a'} dxa",
        f"- List left indent: {list_indent or 'n/a'} pt",
        f"- Cover title size: {title_size or 'n/a'} pt",
        f"- Cover subtitle size: {subtitle_size or 'n/a'} pt",
        f"- Page numbering: prelim {page_format}, body {body_page_format}",
        f"- Sections detected: {int(rules.get('section_count') or len(headings) or 0)}",
        f"- Tables detected: {int(rules.get('table_count') or 0)}",
        f"- Images detected: {int(rules.get('image_count') or 0)}",
    ]

    if headings:
        lines.append("Reference heading blueprint:")
        for heading in headings[:16]:
            lines.append(f"- {heading}")

    return "\n".join(lines)
