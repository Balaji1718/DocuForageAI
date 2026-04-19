from __future__ import annotations

import re
from typing import Any

PLACEHOLDER_SENTENCE = "Content for this required section was not explicitly generated."


def _canonical_section_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).title()


def ensure_required_sections(text: str, required_sections: list[str]) -> str:
    out = text.strip()

    for section in required_sections:
        canon = _canonical_section_name(section)
        if not canon:
            continue

        # Check for markdown heading with this section title.
        heading_pattern = re.compile(rf"^#{{1,3}}\s+{re.escape(canon)}\s*$", flags=re.IGNORECASE | re.MULTILINE)
        if not heading_pattern.search(out):
            out += (
                f"\n\n## {canon}\n"
                f"{PLACEHOLDER_SENTENCE} "
                "This placeholder preserves the required structure."
            )

    return out


def _count_heading_lines(text: str) -> int:
    return len(re.findall(r"^#{1,3}\s+.+$", text, flags=re.MULTILINE))


def _has_very_long_unbroken_paragraph(text: str, threshold: int = 1200) -> bool:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return any(len(p) > threshold and "\n" not in p for p in paragraphs)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _extract_section_bodies(text: str) -> dict[str, str]:
    lines = text.splitlines()
    sections: dict[str, list[str]] = {}
    current = "_preamble"
    sections[current] = []

    heading_pattern = re.compile(r"^#{1,3}\s+(.+?)\s*$")
    for line in lines:
        match = heading_pattern.match(line.strip())
        if match:
            current = _canonical_section_name(match.group(1))
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)

    return {name: "\n".join(content).strip() for name, content in sections.items()}


def _contains_bullets(text: str) -> bool:
    return bool(re.search(r"^\s*([-*]|\d+\.)\s+", text, flags=re.MULTILINE))


def _rule_compliance_checks(text: str, compiled_rules: dict[str, Any] | None = None) -> dict[str, Any]:
    compiled = compiled_rules or {}
    typography = compiled.get("typography") or {}
    content_constraints = compiled.get("content_constraints") or {}
    hard_constraints = [str(item).strip() for item in (compiled.get("hard_constraints") or []) if str(item).strip()]
    soft_constraints = [str(item).strip() for item in (compiled.get("soft_constraints") or []) if str(item).strip()]

    violations: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    penalty = 0.0
    lower = text.lower()

    require_bullets = bool(content_constraints.get("require_bullets"))
    has_bullets = _contains_bullets(text)
    checks.append({"name": "require_bullets", "expected": require_bullets, "actual": has_bullets})
    if require_bullets and not has_bullets:
        violations.append({"rule": "require_bullets", "severity": "medium", "message": "Rules require bullet points."})
        penalty += 10.0

    include_references = bool(content_constraints.get("include_references"))
    has_references = bool(re.search(r"^#{1,3}\s+references\s*$", text, flags=re.IGNORECASE | re.MULTILINE))
    checks.append({"name": "include_references", "expected": include_references, "actual": has_references})
    if include_references and not has_references:
        violations.append({"rule": "include_references", "severity": "medium", "message": "Rules require a References section."})
        penalty += 10.0

    citation_style = str(typography.get("citation_style") or "none")
    has_citation = True
    if citation_style and citation_style.lower() != "none":
        if citation_style.upper() == "IEEE":
            has_citation = bool(re.search(r"\[\d+\]", text))
        else:
            has_citation = bool(re.search(r"\([A-Z][A-Za-z\-]+,\s*\d{4}\)", text))
        checks.append({"name": "citation_style", "expected": citation_style, "actual": has_citation})
        if not has_citation:
            violations.append(
                {
                    "rule": "citation_style",
                    "severity": "low",
                    "message": f"Expected {citation_style} citation markers were not detected.",
                }
            )
            penalty += 6.0

    for constraint in hard_constraints:
        matched = constraint.lower() in lower
        checks.append({"name": "hard_constraint", "expected": constraint, "actual": matched})
        if not matched:
            violations.append({"rule": constraint, "severity": "high", "message": f"Missing hard constraint text: {constraint}"})
            penalty += 12.0

    for constraint in soft_constraints:
        matched = constraint.lower() in lower
        checks.append({"name": "soft_constraint", "expected": constraint, "actual": matched})
        if not matched:
            violations.append({"rule": constraint, "severity": "low", "message": f"Missing soft constraint text: {constraint}"})
            penalty += 3.0

    compliance_score = max(0.0, 100.0 - penalty)
    return {
        "score": round(compliance_score, 2),
        "checks": checks,
        "violations": violations,
        "penalty": round(penalty, 2),
    }


def _formatting_score(text: str) -> tuple[float, dict[str, Any]]:
    heading_count = _count_heading_lines(text)
    very_long_para = _has_very_long_unbroken_paragraph(text)
    bullets = _contains_bullets(text)
    penalty = 0.0
    details: dict[str, Any] = {
        "headingCount": heading_count,
        "containsBullets": bullets,
        "veryLongParagraph": very_long_para,
    }
    if heading_count < 3:
        penalty += 20.0
    if very_long_para:
        penalty += 25.0
    if not bullets:
        penalty += 5.0
    return round(max(0.0, 100.0 - penalty), 2), details


def _structure_score(text: str, required_sections: list[str]) -> tuple[float, dict[str, Any]]:
    sections = _extract_section_bodies(text)
    missing: list[str] = []
    weak: list[str] = []
    penalty = 0.0

    for section in required_sections:
        canon = _canonical_section_name(section)
        if not canon:
            continue
        if not re.search(rf"^#{{1,3}}\s+{re.escape(canon)}\s*$", text, flags=re.IGNORECASE | re.MULTILINE):
            missing.append(canon)
            penalty += 18.0
            continue

        body = sections.get(canon, "")
        words = _word_count(body)
        minimum = 15 if canon.lower() != "body" else 25
        if words < minimum:
            weak.append(canon)
            penalty += 10.0

    if _has_very_long_unbroken_paragraph(text):
        penalty += 12.0

    return (
        round(max(0.0, 100.0 - penalty), 2),
        {
            "missingSections": missing,
            "weakSections": weak,
            "requiredSectionCount": len(required_sections),
            "detectedSectionCount": max(0, len(sections) - (1 if "_preamble" in sections else 0)),
        },
    )


def _build_suggestions(errors: list[str], warnings: list[str], rule_violations: list[dict[str, Any]]) -> list[str]:
    suggestions: list[str] = []

    if any("missing required section heading" in error.lower() for error in errors):
        suggestions.append("Add markdown headings for all required sections in the requested order.")
    if any("section too short" in error.lower() for error in errors):
        suggestions.append("Expand weak sections with concrete details, examples, and evidence.")
    if any("very long unstructured paragraphs" in error.lower() for error in errors):
        suggestions.append("Split long paragraphs into shorter units and use bullets for readability.")
    if any(violation.get("rule") == "citation_style" for violation in rule_violations):
        suggestions.append("Add citation markers aligned with the requested citation style.")
    if any(violation.get("rule") == "require_bullets" for violation in rule_violations):
        suggestions.append("Use bullet lists for key points where required by the rules.")
    if any(violation.get("rule") == "include_references" for violation in rule_violations):
        suggestions.append("Add a References section with properly formatted sources.")
    if warnings and not suggestions:
        suggestions.append("Increase depth and specificity to improve overall report quality.")

    return suggestions[:6]


def validate_structured_output(
    text: str,
    required_sections: list[str],
    compiled_rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not text.strip():
        errors.append("Generated output is empty.")

    heading_count = _count_heading_lines(text)
    if heading_count < 3:
        errors.append("Output has insufficient heading structure (expected at least 3 headings).")

    for section in required_sections:
        canon = _canonical_section_name(section)
        if not canon:
            continue
        if not re.search(rf"^#{{1,3}}\s+{re.escape(canon)}\s*$", text, flags=re.IGNORECASE | re.MULTILINE):
            errors.append(f"Missing required section heading: {canon}")

    sections = _extract_section_bodies(text)
    for section in required_sections:
        canon = _canonical_section_name(section)
        body = sections.get(canon, "")
        if not body:
            errors.append(f"Section has no content: {canon}")
            continue
        words = _word_count(body)
        minimum = 15 if canon.lower() != "body" else 25
        if words < minimum:
            errors.append(f"Section too short ({words} words): {canon} (minimum {minimum})")

    if _has_very_long_unbroken_paragraph(text):
        errors.append("Output contains very long unstructured paragraphs.")

    if PLACEHOLDER_SENTENCE in text:
        errors.append("Output still contains placeholder section content.")

    total_words = _word_count(text)
    if total_words < 180:
        warnings.append("Document is very short; quality may be limited.")

    quality_score = max(0.0, 100.0 - (len(errors) * 18.0) - (len(warnings) * 4.0))
    structure_score, structure_metrics = _structure_score(text, required_sections)
    formatting_score, formatting_metrics = _formatting_score(text)
    rule_checks = _rule_compliance_checks(text, compiled_rules)
    rule_score = rule_checks["score"]

    enhanced_score = round(
        max(0.0, (structure_score * 0.45) + (formatting_score * 0.25) + (rule_score * 0.30) - rule_checks["penalty"]),
        2,
    )

    suggestions = _build_suggestions(errors, warnings, rule_checks["violations"])
    weak_sections = sorted(
        set(structure_metrics.get("missingSections") or []).union(structure_metrics.get("weakSections") or [])
    )

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "headingCount": heading_count,
        "totalWords": total_words,
        "requiredSections": [_canonical_section_name(s) for s in required_sections if _canonical_section_name(s)],
        "qualityScore": round(quality_score, 2),
        "componentScores": {
            "structureScore": structure_score,
            "formattingScore": formatting_score,
            "ruleComplianceScore": rule_score,
        },
        "componentMetrics": {
            "structure": structure_metrics,
            "formatting": formatting_metrics,
            "ruleCompliance": {
                "checks": rule_checks["checks"],
                "violations": rule_checks["violations"],
                "penalty": rule_checks["penalty"],
            },
        },
        "enhancedScore": enhanced_score,
        "ruleViolations": rule_checks["violations"],
        "weakSections": weak_sections,
        "issues": errors + warnings,
        "suggestions": suggestions,
        "structuredFeedback": {
            "score": enhanced_score,
            "issues": errors + warnings,
            "suggestions": suggestions,
        },
    }


def enforce_and_validate(
    text: str,
    required_sections: list[str],
    compiled_rules: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    enforced = ensure_required_sections(text, required_sections)
    report = validate_structured_output(enforced, required_sections, compiled_rules=compiled_rules)
    return enforced, report
