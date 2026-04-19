from __future__ import annotations

import logging
import os
import re

from ai_fallback import generate_with_collaboration
from services.rule_compiler import build_compiled_rules_guidance, compile_rules
from services.reference_service import build_reference_guidance, parse_reference_content
from services.rule_service import parse_rules_text
from services.validation_service import enforce_and_validate
from utils.helpers import chunk_text

log = logging.getLogger("docuforge.ai.service")
ENABLE_LARGE_CONTENT_REFINEMENT = os.getenv("ENABLE_LARGE_CONTENT_REFINEMENT", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def generate_structured_text(
    title: str,
    rules: str,
    content: str,
    reference_content: str = "",
    reference_mime_type: str = "",
    chunk_size: int = 8000,
    retries: int = 1,
) -> tuple[str, dict, dict, dict]:
    chunks = chunk_text(content, chunk_size)
    parsed_rules = parse_rules_text(rules)
    compiled_rules = compile_rules(parsed_rules)
    parsed_rules["compiled"] = compiled_rules
    rules_guidance = build_compiled_rules_guidance(compiled_rules)
    parsed_reference = parse_reference_content(reference_content, reference_mime_type)
    reference_guidance = build_reference_guidance(parsed_reference)
    required_sections = parsed_rules.get("required_sections") or ["Introduction", "Body", "Conclusion"]

    def _extract_sections(markdown_text: str) -> list[dict[str, str]]:
        section_pattern = re.compile(r"(?ms)^#{1,3}\s+(.+?)\s*$")
        matches = list(section_pattern.finditer(markdown_text))
        if not matches:
            return [{"name": "Document", "content": markdown_text.strip()}]

        sections: list[dict[str, str]] = []
        for index, match in enumerate(matches):
            name = match.group(1).strip()
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_text)
            sections.append({"name": name, "content": markdown_text[start:end].strip()})
        return sections

    def _rebuild_sections(sections: list[dict[str, str]]) -> str:
        return "\n\n".join(section.get("content", "").strip() for section in sections if section.get("content", "")).strip()

    def _build_correction_guidance(report: dict) -> str:
        issues = [str(item) for item in (report.get("issues") or report.get("errors") or []) if str(item).strip()]
        suggestions = [str(item) for item in (report.get("suggestions") or []) if str(item).strip()]
        weak_sections = [str(item) for item in (report.get("weakSections") or []) if str(item).strip()]

        buckets = {
            "missing_headings": any("missing required section heading" in issue.lower() for issue in issues),
            "poor_structure": any(
                token in issue.lower() for issue in issues for token in ["section too short", "insufficient heading", "very long"]
            ),
            "formatting_inconsistencies": any(
                token in issue.lower() for issue in issues for token in ["paragraph", "placeholder", "heading"]
            ),
            "rule_violations": bool(report.get("ruleViolations") or []),
        }

        lines = [
            "TARGETED CORRECTION FEEDBACK:",
            f"- Missing headings detected: {'yes' if buckets['missing_headings'] else 'no'}",
            f"- Poor structure detected: {'yes' if buckets['poor_structure'] else 'no'}",
            f"- Formatting inconsistencies detected: {'yes' if buckets['formatting_inconsistencies'] else 'no'}",
            f"- Rule compliance violations detected: {'yes' if buckets['rule_violations'] else 'no'}",
        ]
        if weak_sections:
            lines.append("Weak sections to prioritize: " + ", ".join(weak_sections[:8]))
        if issues:
            lines.append("Detected issues:")
            for issue in issues[:10]:
                lines.append(f"- {issue}")
        if suggestions:
            lines.append("Improvement hints:")
            for suggestion in suggestions[:8]:
                lines.append(f"- {suggestion}")

        lines.append("Apply only necessary edits and preserve already-correct sections.")
        return "\n".join(lines)

    def _apply_partial_regeneration(
        current_text: str,
        report: dict,
        guidance: str,
    ) -> str:
        weak_sections = [str(item).strip() for item in (report.get("weakSections") or []) if str(item).strip()]
        if not weak_sections:
            return current_text

        sections = _extract_sections(current_text)
        if not sections:
            return current_text

        replaced = 0
        for idx, section in enumerate(sections):
            section_name = section.get("name", "").strip()
            if section_name.lower() not in {item.lower() for item in weak_sections}:
                continue

            try:
                regenerated = generate_with_collaboration(
                    title=title,
                    rules=(
                        f"{guidance}\n\n"
                        "PARTIAL REGENERATION TASK:\n"
                        f"- Regenerate only this section: {section_name}\n"
                        "- Return markdown beginning with the same section heading.\n"
                        "- Keep scope focused and avoid rewriting unrelated sections."
                    ),
                    content=section.get("content", ""),
                    chunk_index=1,
                    total_chunks=1,
                )
                regenerated = regenerated.strip()
                if regenerated:
                    sections[idx]["content"] = regenerated
                    replaced += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("Partial regeneration failed for section %s: %s", section_name, exc)

        if replaced == 0:
            return current_text
        return _rebuild_sections(sections)

    def _generate_chunks_with_guidance(guidance: str) -> str:
        sections: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            for attempt in range(retries + 1):
                try:
                    section = generate_with_collaboration(
                        title=title,
                        rules=guidance,
                        content=chunk,
                        chunk_index=idx,
                        total_chunks=len(chunks),
                    )
                    sections.append(section)
                    break
                except Exception as exc:  # noqa: BLE001
                    if attempt >= retries:
                        log.exception("AI generation failed after retry for chunk %s: %s", idx, exc)
                        raise
                    log.warning(
                        "AI generation failed for chunk %s (attempt %s/%s): %s",
                        idx,
                        attempt + 1,
                        retries + 1,
                        exc,
                    )
        return "\n\n".join(sections)

    def _refine_large_output_if_needed(joined: str, guidance: str) -> str:
        if len(chunks) <= 1 or not ENABLE_LARGE_CONTENT_REFINEMENT:
            return joined
        try:
            log.info("Running large-content coherence refinement for %s chunks", len(chunks))
            return generate_with_collaboration(
                title=title,
                rules=(
                    f"{guidance}\n\n"
                    "FINAL COHERENCE PASS:\n"
                    "- Merge and harmonize chunk sections into one consistent academic report.\n"
                    "- Preserve factual content; do not invent new claims.\n"
                    "- Ensure section continuity and remove duplicated transitions."
                ),
                content=joined,
                chunk_index=1,
                total_chunks=1,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Large-content refinement skipped due to error: %s", exc)
            return joined

    combined_guidance = f"{rules_guidance}\n\nREFERENCE ALIGNMENT:\n{reference_guidance}"
    first_pass = _generate_chunks_with_guidance(combined_guidance)
    first_pass = _refine_large_output_if_needed(first_pass, combined_guidance)
    first_enforced, first_report = enforce_and_validate(first_pass, required_sections, compiled_rules=compiled_rules)

    if first_report.get("ok"):
        first_report["retried"] = False
        return first_enforced, parsed_rules, parsed_reference, first_report

    log.warning("Validation failed on first pass. Retrying once with stricter guidance: %s", first_report.get("errors"))
    correction_guidance = _build_correction_guidance(first_report)

    # Try targeted partial regeneration before full retry.
    partially_corrected = _apply_partial_regeneration(first_enforced, first_report, f"{combined_guidance}\n\n{correction_guidance}")
    if partially_corrected != first_enforced:
        partial_enforced, partial_report = enforce_and_validate(
            partially_corrected,
            required_sections,
            compiled_rules=compiled_rules,
        )
        if partial_report.get("ok"):
            partial_report["retried"] = True
            partial_report["partialRegeneration"] = True
            return partial_enforced, parsed_rules, parsed_reference, partial_report

    retry_guidance = (
        f"{combined_guidance}\n\n{correction_guidance}\n\n"
        "STRICT OUTPUT ENFORCEMENT:\n"
        "- You must include markdown headings for all required sections.\n"
        "- Use short, structured paragraphs and bullet points when helpful.\n"
        "- Avoid long unbroken text blocks.\n"
        "- Ensure Introduction, Body, and Conclusion are present unless explicit replacements are required."
    )
    second_pass = _generate_chunks_with_guidance(retry_guidance)
    second_pass = _refine_large_output_if_needed(second_pass, retry_guidance)
    second_enforced, second_report = enforce_and_validate(second_pass, required_sections, compiled_rules=compiled_rules)
    second_report["retried"] = True
    second_report["partialRegeneration"] = bool(first_report.get("weakSections"))

    if not second_report.get("ok"):
        raise ValueError(
            "Output quality validation failed after one retry: "
            + "; ".join(second_report.get("errors") or ["unknown validation error"])
        )

    return second_enforced, parsed_rules, parsed_reference, second_report
