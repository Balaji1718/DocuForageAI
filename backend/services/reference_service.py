from __future__ import annotations

import re
from typing import Any


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
