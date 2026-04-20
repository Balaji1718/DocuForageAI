from __future__ import annotations

import re
from typing import Any


SECTION_KEYWORDS = {
    "introduction": "Introduction",
    "background": "Background",
    "methodology": "Methodology",
    "analysis": "Analysis",
    "discussion": "Discussion",
    "results": "Results",
    "conclusion": "Conclusion",
    "references": "References",
}

DEFAULT_REQUIRED_SECTIONS = ["Introduction", "Body", "Conclusion"]


def _extract_headings(lines: list[str]) -> list[dict[str, Any]]:
    headings: list[dict[str, Any]] = []
    numbered = re.compile(r"^(\d+(?:\.\d+)*)\s*[-.)]?\s+(.+)$")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("### "):
            headings.append({"level": 3, "title": stripped[4:].strip()})
            continue
        if stripped.startswith("## "):
            headings.append({"level": 2, "title": stripped[3:].strip()})
            continue
        if stripped.startswith("# "):
            headings.append({"level": 1, "title": stripped[2:].strip()})
            continue

        match = numbered.match(stripped)
        if match:
            token = match.group(1)
            title = match.group(2).strip()
            level = token.count(".") + 1
            headings.append({"level": max(1, min(level, 4)), "title": title})

    return headings


def _extract_formatting_preferences(rules_text: str) -> dict[str, Any]:
    lower = rules_text.lower()
    citation = "none"
    if "apa" in lower:
        citation = "APA"
    elif "mla" in lower:
        citation = "MLA"
    elif "harvard" in lower:
        citation = "Harvard"
    elif "ieee" in lower:
        citation = "IEEE"

    alignment = "unspecified"
    if "justify" in lower or "justified" in lower:
        alignment = "justified"
    elif "left align" in lower or "left-aligned" in lower:
        alignment = "left"
    elif "center" in lower or "centred" in lower or "centered" in lower:
        alignment = "center"

    line_spacing = "single"
    if "double spacing" in lower or "double-spaced" in lower:
        line_spacing = "double"
    elif "1.5" in lower or "one and a half" in lower:
        line_spacing = "1.5"

    return {
        "require_bullets": any(token in lower for token in ("bullet", "list", "points")),
        "require_numbering": any(token in lower for token in ("numbered", "1.", "2.", "section numbering")),
        "heading_numbering": any(token in lower for token in ("numbered heading", "numbered headings", "section numbering")),
        "citation_style": citation,
        "tone": "formal" if "formal" in lower or "academic" in lower else "unspecified",
        "paragraph_spacing": "wide" if "paragraph spacing" in lower and "extra" in lower else "normal",
        "line_spacing": line_spacing,
        "alignment": alignment,
        "font_family": "Times New Roman" if "times new roman" in lower else "unspecified",
    }


def _extract_required_sections(headings: list[dict[str, Any]], rules_text: str) -> list[str]:
    found: set[str] = set()
    for heading in headings:
        title = str(heading.get("title") or "").strip().lower()
        for keyword, section_name in SECTION_KEYWORDS.items():
            if keyword in title:
                found.add(section_name)

    lower_rules = rules_text.lower()
    for keyword, section_name in SECTION_KEYWORDS.items():
        if keyword in lower_rules:
            found.add(section_name)

    core = set(DEFAULT_REQUIRED_SECTIONS)
    if found.intersection(core):
        found.update(core)

    if not found:
        return DEFAULT_REQUIRED_SECTIONS

    ordered: list[str] = []
    for section in DEFAULT_REQUIRED_SECTIONS:
        if section in found:
            ordered.append(section)
    extras = sorted([name for name in found if name not in core])
    ordered.extend(extras)
    return ordered


def _extract_structural_requirements(rules_text: str, headings: list[dict[str, Any]]) -> dict[str, Any]:
    lower = rules_text.lower()
    max_heading_depth = max([int(h.get("level") or 1) for h in headings], default=3)
    page_match = re.search(r"(?:up\s*to|max(?:imum)?|around|about)?\s*(\d{1,3})\s*pages?", lower)
    target_pages = int(page_match.group(1)) if page_match else 0
    target_words = 1500 if "long" in lower else 800 if "medium" in lower else 500
    if target_pages > 0:
        # Use an academic average of ~300 words/page to calibrate long-form generation.
        target_words = max(target_words, target_pages * 300)

    return {
        "require_intro_body_conclusion": all(
            keyword in lower for keyword in ("introduction", "body", "conclusion")
        )
        or max_heading_depth >= 2,
        "prefer_tables": "table" in lower,
        "prefer_images": "image" in lower or "figure" in lower,
        "max_heading_depth": max_heading_depth,
        "include_references": "references" in lower or "bibliography" in lower,
        "target_length_words": target_words,
        "target_length_pages": target_pages,
    }


def _extract_constraints(lines: list[str]) -> dict[str, list[str]]:
    hard: list[str] = []
    soft: list[str] = []
    for line in lines:
        stripped = line.strip(" -\t")
        if not stripped:
            continue
        lower = stripped.lower()
        if any(token in lower for token in ("must", "required", "always", "do not", "never")):
            hard.append(stripped)
        elif any(token in lower for token in ("should", "prefer", "ideally", "recommended")):
            soft.append(stripped)
    return {"hard": hard, "soft": soft}


def _detect_conflicts(formatting: dict[str, Any], rules_text: str) -> list[str]:
    lower = rules_text.lower()
    conflicts: list[str] = []

    if "single spacing" in lower and "double spacing" in lower:
        conflicts.append("Conflicting line spacing instructions: single and double.")
    if "left align" in lower and ("justify" in lower or "justified" in lower):
        conflicts.append("Conflicting alignment instructions: left and justified.")
    if "no bullet" in lower and formatting.get("require_bullets"):
        conflicts.append("Conflicting list instructions: bullets required and prohibited.")
    return conflicts


def _detect_ambiguities(required_sections: list[str], rules_text: str) -> list[str]:
    ambiguities: list[str] = []
    if len(required_sections) <= 1:
        ambiguities.append("Sections are not clearly specified; defaults may be applied.")
    if not rules_text.strip():
        ambiguities.append("No rules provided; standard academic defaults will be applied.")
    return ambiguities


def parse_rules_text(rules_text: str) -> dict[str, Any]:
    """Convert free-form rules text into normalized structured JSON."""
    cleaned = (rules_text or "").strip()
    lines = [line.rstrip() for line in cleaned.splitlines()]
    headings = _extract_headings(lines)

    instructions = [
        line.strip(" -\t")
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]

    required_sections = _extract_required_sections(headings, cleaned)
    formatting = _extract_formatting_preferences(cleaned)
    structural = _extract_structural_requirements(cleaned, headings)
    constraints = _extract_constraints(lines)
    conflicts = _detect_conflicts(formatting, cleaned)
    ambiguities = _detect_ambiguities(required_sections, cleaned)

    return {
        "raw": cleaned,
        "headings": headings,
        "required_sections": required_sections,
        "formatting": formatting,
        "structural_requirements": structural,
        "constraints": constraints,
        "instructions": instructions,
        "conflicts": conflicts,
        "ambiguities": ambiguities,
    }


def build_rules_guidance(parsed_rules: dict[str, Any]) -> str:
    """Build a consistent prompt-friendly representation of parsed rules."""
    if not parsed_rules:
        return "Use standard academic formatting with clear section hierarchy."

    required_sections = parsed_rules.get("required_sections") or DEFAULT_REQUIRED_SECTIONS
    headings = parsed_rules.get("headings") or []
    formatting = parsed_rules.get("formatting") or {}
    structural = parsed_rules.get("structural_requirements") or {}
    constraints = parsed_rules.get("constraints") or {}
    instructions = parsed_rules.get("instructions") or []

    guidance_lines: list[str] = [
        "Required sections: " + ", ".join(required_sections),
        "Formatting preferences:",
        f"- Bullets: {'yes' if formatting.get('require_bullets') else 'no'}",
        f"- Numbering: {'yes' if formatting.get('require_numbering') else 'no'}",
        f"- Citation style: {formatting.get('citation_style', 'none')}",
        f"- Tone: {formatting.get('tone', 'unspecified')}",
        f"- Alignment: {formatting.get('alignment', 'unspecified')}",
        f"- Line spacing: {formatting.get('line_spacing', 'single')}",
        f"- Paragraph spacing: {formatting.get('paragraph_spacing', 'normal')}",
        "Structural requirements:",
        f"- Include references: {'yes' if structural.get('include_references') else 'no'}",
        f"- Prefer tables: {'yes' if structural.get('prefer_tables') else 'no'}",
        f"- Prefer images: {'yes' if structural.get('prefer_images') else 'no'}",
        f"- Max heading depth: {structural.get('max_heading_depth', 3)}",
        f"- Target length (words): {structural.get('target_length_words', 500)}",
    ]

    if headings:
        guidance_lines.append("Heading outline:")
        for heading in headings:
            level = int(heading.get("level") or 1)
            title = str(heading.get("title") or "Untitled")
            guidance_lines.append(f"- H{level}: {title}")

    if instructions:
        guidance_lines.append("Additional instructions:")
        for instruction in instructions[:20]:
            guidance_lines.append(f"- {instruction}")

    hard_constraints = constraints.get("hard") or []
    soft_constraints = constraints.get("soft") or []
    if hard_constraints:
        guidance_lines.append("Hard constraints:")
        for item in hard_constraints[:15]:
            guidance_lines.append(f"- {item}")
    if soft_constraints:
        guidance_lines.append("Soft constraints:")
        for item in soft_constraints[:15]:
            guidance_lines.append(f"- {item}")

    conflicts = parsed_rules.get("conflicts") or []
    ambiguities = parsed_rules.get("ambiguities") or []
    if conflicts:
        guidance_lines.append("Detected conflicts (resolve with latest instruction):")
        for item in conflicts[:10]:
            guidance_lines.append(f"- {item}")
    if ambiguities:
        guidance_lines.append("Detected ambiguities (apply defaults where needed):")
        for item in ambiguities[:10]:
            guidance_lines.append(f"- {item}")

    return "\n".join(guidance_lines)
