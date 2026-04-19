from __future__ import annotations

import re
from typing import Any


DEFAULT_SECTIONS = ["Introduction", "Body", "Conclusion"]


def _latest_match(text: str, options: dict[str, str]) -> tuple[str | None, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    lower = text.lower()
    for token, value in options.items():
        for match in re.finditer(re.escape(token), lower):
            events.append({"token": token, "value": value, "position": match.start()})
    if not events:
        return None, []
    events.sort(key=lambda item: int(item["position"]))
    return str(events[-1]["value"]), events


def _resolve_conflicts(parsed_rules: dict[str, Any]) -> dict[str, Any]:
    raw = str(parsed_rules.get("raw") or "")
    formatting = parsed_rules.get("formatting") or {}
    trace: list[dict[str, Any]] = []

    resolved: dict[str, Any] = {
        "alignment": formatting.get("alignment") or "unspecified",
        "line_spacing": formatting.get("line_spacing") or "single",
        "citation_style": formatting.get("citation_style") or "none",
        "require_bullets": bool(formatting.get("require_bullets")),
    }

    alignment_value, alignment_events = _latest_match(
        raw,
        {
            "left align": "left",
            "left-aligned": "left",
            "justify": "justified",
            "justified": "justified",
            "center": "center",
            "centered": "center",
            "centred": "center",
        },
    )
    if alignment_events:
        resolved["alignment"] = alignment_value or resolved["alignment"]
        trace.append(
            {
                "field": "alignment",
                "policy": "latest_instruction_overrides",
                "events": alignment_events,
                "resolved_to": resolved["alignment"],
            }
        )

    spacing_value, spacing_events = _latest_match(
        raw,
        {
            "single spacing": "single",
            "double spacing": "double",
            "double-spaced": "double",
            "1.5 spacing": "1.5",
            "one and a half": "1.5",
        },
    )
    if spacing_events:
        resolved["line_spacing"] = spacing_value or resolved["line_spacing"]
        trace.append(
            {
                "field": "line_spacing",
                "policy": "latest_instruction_overrides",
                "events": spacing_events,
                "resolved_to": resolved["line_spacing"],
            }
        )

    citation_value, citation_events = _latest_match(
        raw,
        {
            "apa": "APA",
            "mla": "MLA",
            "harvard": "Harvard",
            "ieee": "IEEE",
        },
    )
    if citation_events:
        resolved["citation_style"] = citation_value or resolved["citation_style"]
        trace.append(
            {
                "field": "citation_style",
                "policy": "latest_instruction_overrides",
                "events": citation_events,
                "resolved_to": resolved["citation_style"],
            }
        )

    bullets_value, bullets_events = _latest_match(
        raw,
        {
            "no bullet": "no",
            "avoid bullet": "no",
            "use bullet": "yes",
            "bullet points": "yes",
        },
    )
    if bullets_events:
        resolved["require_bullets"] = bullets_value == "yes"
        trace.append(
            {
                "field": "require_bullets",
                "policy": "latest_instruction_overrides",
                "events": bullets_events,
                "resolved_to": resolved["require_bullets"],
            }
        )

    return {"resolved": resolved, "trace": trace}


def compile_rules(parsed_rules: dict[str, Any]) -> dict[str, Any]:
    required_sections = parsed_rules.get("required_sections") or DEFAULT_SECTIONS
    formatting = parsed_rules.get("formatting") or {}
    structural = parsed_rules.get("structural_requirements") or {}
    constraints = parsed_rules.get("constraints") or {}
    headings = parsed_rules.get("headings") or []
    conflicts = parsed_rules.get("conflicts") or []
    ambiguities = parsed_rules.get("ambiguities") or []
    conflict_resolution = _resolve_conflicts(parsed_rules)
    resolved = conflict_resolution.get("resolved") or {}

    sections = [{"name": name, "required": True, "order": idx + 1} for idx, name in enumerate(required_sections)]

    applied_defaults: list[str] = []
    citation_style = str(resolved.get("citation_style") or formatting.get("citation_style") or "none")
    if citation_style == "none":
        applied_defaults.append("citation_style:none")

    alignment = str(resolved.get("alignment") or formatting.get("alignment") or "unspecified")
    if alignment == "unspecified":
        alignment = "justified"
        applied_defaults.append("alignment:justified")

    line_spacing = str(resolved.get("line_spacing") or formatting.get("line_spacing") or "single")

    layout = {
        "deterministic": True,
        "heading_numbering": bool(formatting.get("heading_numbering") or formatting.get("require_numbering")),
        "max_heading_depth": int(structural.get("max_heading_depth") or 3),
        "allow_tables": bool(structural.get("prefer_tables")),
        "allow_images": bool(structural.get("prefer_images")),
    }

    typography = {
        "font_family": formatting.get("font_family") or "Times New Roman",
        "alignment": alignment,
        "line_spacing": line_spacing,
        "paragraph_spacing": formatting.get("paragraph_spacing") or "normal",
        "tone": formatting.get("tone") or "formal",
        "citation_style": citation_style,
    }

    compiled = {
        "version": "1.0",
        "deterministic": True,
        "sections": sections,
        "heading_outline": headings,
        "typography": typography,
        "layout": layout,
        "content_constraints": {
            "target_length_words": int(structural.get("target_length_words") or 500),
            "require_bullets": bool(formatting.get("require_bullets")),
            "include_references": bool(structural.get("include_references")),
        },
        "hard_constraints": constraints.get("hard") or [],
        "soft_constraints": constraints.get("soft") or [],
        "conflicts": conflicts,
        "ambiguities": ambiguities,
        "resolution_policy": {
            "conflict": "latest_instruction_overrides",
            "ambiguity": "defaults_applied",
        },
        "conflict_resolution": conflict_resolution,
        "applied_defaults": applied_defaults,
    }
    return compiled


def build_compiled_rules_guidance(compiled_rules: dict[str, Any]) -> str:
    sections = compiled_rules.get("sections") or []
    typography = compiled_rules.get("typography") or {}
    layout = compiled_rules.get("layout") or {}
    content = compiled_rules.get("content_constraints") or {}

    lines = [
        "Compiled constraints (deterministic):",
        "Required section order: "
        + (", ".join([s.get("name", "") for s in sections if s.get("name")]) or "Introduction, Body, Conclusion"),
        "Typography:",
        f"- Font: {typography.get('font_family', 'Times New Roman')}",
        f"- Alignment: {typography.get('alignment', 'justified')}",
        f"- Line spacing: {typography.get('line_spacing', 'single')}",
        f"- Paragraph spacing: {typography.get('paragraph_spacing', 'normal')}",
        f"- Citation style: {typography.get('citation_style', 'none')}",
        "Layout:",
        f"- Heading numbering: {'enabled' if layout.get('heading_numbering') else 'disabled'}",
        f"- Max heading depth: {layout.get('max_heading_depth', 3)}",
        f"- Tables allowed: {'yes' if layout.get('allow_tables') else 'no'}",
        f"- Images allowed: {'yes' if layout.get('allow_images') else 'no'}",
        "Content constraints:",
        f"- Target length words: {content.get('target_length_words', 500)}",
        f"- Use bullets: {'yes' if content.get('require_bullets') else 'no'}",
        f"- Include references: {'yes' if content.get('include_references') else 'no'}",
    ]

    hard = compiled_rules.get("hard_constraints") or []
    soft = compiled_rules.get("soft_constraints") or []
    conflicts = compiled_rules.get("conflicts") or []
    ambiguities = compiled_rules.get("ambiguities") or []
    defaults = compiled_rules.get("applied_defaults") or []

    if hard:
        lines.append("Hard constraints:")
        for item in hard[:15]:
            lines.append(f"- {item}")
    if soft:
        lines.append("Soft constraints:")
        for item in soft[:15]:
            lines.append(f"- {item}")
    if conflicts:
        lines.append("Conflicts detected (resolved by latest instruction):")
        for item in conflicts[:10]:
            lines.append(f"- {item}")
    if ambiguities:
        lines.append("Ambiguities detected (defaults applied):")
        for item in ambiguities[:10]:
            lines.append(f"- {item}")
    if defaults:
        lines.append("Applied defaults:")
        for item in defaults[:10]:
            lines.append(f"- {item}")

    return "\n".join(lines)
