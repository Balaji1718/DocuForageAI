from __future__ import annotations

from difflib import SequenceMatcher
import os
from pathlib import Path
import re
from typing import Any

from docx import Document
from PIL import Image


def _active_validation_profile() -> str:
    return os.getenv("RENDER_VALIDATION_PROFILE", "strict").strip().lower()


def _normalize_text(text: str) -> str:
    return " ".join(text.replace("\r\n", "\n").replace("\r", "\n").split()).strip().lower()


def _extract_docx_text(path: Path) -> tuple[str, int]:
    document = Document(str(path))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    return "\n".join(paragraphs), len(paragraphs)


def _extract_pdf_text(path: Path) -> tuple[str, int]:
    try:
        from pypdf import PdfReader
    except Exception:
        return "", 0

    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if text:
            chunks.append(text)
    return "\n\n".join(chunks), len(reader.pages)


def _extract_pdf_visual_metrics(path: Path) -> dict[str, Any]:
    try:
        import fitz
    except Exception:
        return {
            "supported": False,
            "pages": [],
            "averageVisualScore": 0.0,
            "error": "pymupdf not installed",
        }

    document = fitz.open(str(path))
    page_metrics: list[dict[str, Any]] = []

    for page_index, page in enumerate(document, start=1):
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), colorspace=fitz.csGRAY, alpha=False)
        image = Image.frombytes("L", [pixmap.width, pixmap.height], pixmap.samples)
        width, height = image.size
        total_pixels = max(1, width * height)
        pixels = image.load()

        dark_pixels = 0
        upper_dark_pixels = 0
        lower_dark_pixels = 0
        row_darkness: list[float] = []

        for y in range(height):
            row_dark = 0
            for x in range(width):
                value = int(pixels[x, y])
                if value < 235:
                    dark_pixels += 1
                    row_dark += 1
                    if y < height // 2:
                        upper_dark_pixels += 1
                    else:
                        lower_dark_pixels += 1
            row_darkness.append(row_dark / max(1, width))

        actual_dark_ratio = round(dark_pixels / total_pixels, 4)
        actual_upper_dark_ratio = round(upper_dark_pixels / max(1, total_pixels // 2), 4)
        actual_lower_dark_ratio = round(lower_dark_pixels / max(1, total_pixels // 2), 4)

        darkness_mass = sum(row_darkness) or 1.0
        centroid_y = round(sum(index * value for index, value in enumerate(row_darkness)) / darkness_mass / max(1, height - 1), 4)

        page_metrics.append(
            {
                "page": page_index,
                "width": width,
                "height": height,
                "darkRatio": actual_dark_ratio,
                "upperDarkRatio": actual_upper_dark_ratio,
                "lowerDarkRatio": actual_lower_dark_ratio,
                "centroidY": centroid_y,
            }
        )

    average_score = round(
        sum(metric["darkRatio"] * 100.0 for metric in page_metrics) / max(1, len(page_metrics)),
        2,
    )

    return {
        "supported": True,
        "pages": page_metrics,
        "averageVisualScore": average_score,
    }


def _expected_page_visual_profile(layout_plan: dict[str, Any] | None, document_model: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    if not layout_plan:
        return {}

    blocks = {str(block.get("id")): block for block in ((document_model or {}).get("blocks") or [])}
    pages: dict[int, dict[str, Any]] = {}

    for placement in layout_plan.get("placements") or []:
        page_number = int(placement.get("page") or 1)
        block = blocks.get(str(placement.get("blockId")), {})
        expected = pages.setdefault(
            page_number,
            {
                "estimatedLines": 0,
                "headingCount": 0,
                "paragraphCount": 0,
                "listCount": 0,
                "blockCount": 0,
            },
        )
        expected["estimatedLines"] += int(placement.get("estimatedLines") or 0)
        expected["blockCount"] += 1
        block_type = str(block.get("type") or "")
        if block_type == "heading":
            expected["headingCount"] += 1
        elif block_type == "paragraph":
            expected["paragraphCount"] += 1
        elif block_type in {"list_item", "ordered_list_item"}:
            expected["listCount"] += 1

    return pages


def _adaptive_page_threshold(expected: dict[str, Any]) -> float:
    """Calculate adaptive visual similarity threshold based on page content composition.
    
    - Heading-dominant (≥50% headings): 60% threshold (lower density acceptable)
    - List-heavy (≥50% lists): 62% threshold (lists are naturally sparse)
    - Text-heavy (≥60% paragraphs): 70% threshold (requires denser content)
    - Mixed content: 65% threshold (default)
    """
    heading_count = expected.get("headingCount", 0)
    paragraph_count = expected.get("paragraphCount", 0)
    list_count = expected.get("listCount", 0)
    total_blocks = heading_count + paragraph_count + list_count
    
    if total_blocks == 0:
        return 65.0
    
    heading_ratio = heading_count / total_blocks
    paragraph_ratio = paragraph_count / total_blocks
    list_ratio = list_count / total_blocks
    
    if heading_ratio >= 0.5:
        return 60.0
    elif list_ratio >= 0.5:
        return 62.0
    elif paragraph_ratio >= 0.6:
        return 70.0
    else:
        return 65.0


def _compare_visual_profiles(
    actual_pages: list[dict[str, Any]],
    expected_pages: dict[int, dict[str, Any]],
    layout_plan: dict[str, Any] | None,
    min_page_score: float = 65.0,
) -> dict[str, Any]:
    if not actual_pages:
        return {
            "supported": False,
            "pageScores": [],
            "averageScore": 0.0,
            "failedPages": [],
            "issues": ["No renderable pages were produced for visual comparison."],
        }

    page_capacity = int((layout_plan or {}).get("pageCapacityLines") or 48)
    page_scores: list[dict[str, Any]] = []
    failed_pages: list[int] = []

    for page in actual_pages:
        page_number = int(page["page"])
        expected = expected_pages.get(page_number) or {
            "estimatedLines": page_capacity // 2,
            "headingCount": 0,
            "paragraphCount": 0,
            "listCount": 0,
            "blockCount": 0,
        }

        utilization = min(1.0, float(expected.get("estimatedLines") or 0) / max(1, page_capacity))
        expected_dark_ratio = min(
            0.03,
            0.006 + (utilization * 0.012) + (expected.get("headingCount", 0) * 0.0008) + (expected.get("listCount", 0) * 0.0005),
        )
        expected_centroid = min(
            0.45,
            0.16 + (expected.get("headingCount", 0) * 0.015) + (expected.get("paragraphCount", 0) * 0.006) + (utilization * 0.08),
        )

        dark_diff = abs(float(page.get("darkRatio") or 0.0) - expected_dark_ratio)
        centroid_diff = abs(float(page.get("centroidY") or 0.0) - expected_centroid)

        score = 100.0 - (dark_diff * 2500.0) - (centroid_diff * 120.0)
        score = round(max(0.0, min(100.0, score)), 2)

        # Determine adaptive threshold based on page content type
        adaptive_threshold = _adaptive_page_threshold(expected)
        threshold_to_use = min(adaptive_threshold, min_page_score)

        page_entry = {
            "page": page_number,
            "score": score,
            "actual": page,
            "expected": {
                "estimatedLines": expected.get("estimatedLines", 0),
                "headingCount": expected.get("headingCount", 0),
                "paragraphCount": expected.get("paragraphCount", 0),
                "listCount": expected.get("listCount", 0),
                "darkRatio": round(expected_dark_ratio, 4),
                "centroidY": round(expected_centroid, 4),
            },
            "adaptiveThreshold": adaptive_threshold,
        }
        if score < threshold_to_use:
            failed_pages.append(page_number)
            page_entry["failed"] = True

        page_scores.append(page_entry)

    average_score = round(sum(item["score"] for item in page_scores) / max(1, len(page_scores)), 2)
    issues: list[str] = []
    if failed_pages:
        issues.append(f"Pages with low visual similarity (< {min_page_score}%): {failed_pages}")
    if average_score < 68.0:
        issues.append(f"Average visual page similarity below threshold: {average_score}")

    return {
        "supported": True,
        "pageScores": page_scores,
        "averageScore": average_score,
        "failedPages": failed_pages,
        "issues": issues,
    }


def _section_signatures(text: str) -> list[str]:
    signatures: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            signatures.append(stripped.lstrip("# ").strip().lower())
    return signatures


def _similarity(source: str, rendered: str) -> float:
    if not source and not rendered:
        return 100.0
    return round(SequenceMatcher(None, _normalize_text(source), _normalize_text(rendered)).ratio() * 100.0, 2)


def _render_rule_penalties(
    structured_text: str,
    compiled_rules: dict[str, Any] | None,
) -> dict[str, Any]:
    compiled = compiled_rules or {}
    content_constraints = compiled.get("content_constraints") or {}
    typography = compiled.get("typography") or {}

    violations: list[dict[str, Any]] = []
    penalty = 0.0

    if bool(content_constraints.get("require_bullets")) and not re.search(r"^\s*([-*]|\d+\.)\s+", structured_text, flags=re.MULTILINE):
        violations.append({"rule": "require_bullets", "severity": "medium", "message": "Expected bullet lists were not found."})
        penalty += 8.0

    if bool(content_constraints.get("include_references")) and not re.search(
        r"^#{1,3}\s+references\s*$",
        structured_text,
        flags=re.IGNORECASE | re.MULTILINE,
    ):
        violations.append({"rule": "include_references", "severity": "medium", "message": "Missing References section."})
        penalty += 8.0

    citation_style = str(typography.get("citation_style") or "none")
    if citation_style.lower() != "none":
        has_marker = bool(re.search(r"\([A-Z][A-Za-z\-]+,\s*\d{4}\)|\[\d+\]", structured_text))
        if not has_marker:
            violations.append(
                {
                    "rule": "citation_style",
                    "severity": "low",
                    "message": f"No citation markers detected for {citation_style} style.",
                }
            )
            penalty += 5.0

    return {
        "violations": violations,
        "penalty": round(penalty, 2),
        "score": round(max(0.0, 100.0 - penalty), 2),
    }


def _build_suggestions(issues: list[str], rule_violations: list[dict[str, Any]]) -> list[str]:
    suggestions: list[str] = []
    lower_issues = [issue.lower() for issue in issues]

    if any("heading match ratio" in issue for issue in lower_issues):
        suggestions.append("Preserve required heading titles exactly between generated text and rendered output.")
    if any("rendered text similarity" in issue for issue in lower_issues):
        suggestions.append("Reduce paraphrasing during render and keep wording closer to the generated source text.")
    if any("visual" in issue for issue in lower_issues):
        suggestions.append("Tighten layout density on failed pages to improve visual fidelity.")
    if any("page count mismatch" in issue for issue in lower_issues):
        suggestions.append("Adjust page capacity and spacing to align expected and actual page counts.")
    if any(v.get("rule") == "include_references" for v in rule_violations):
        suggestions.append("Include a References section to satisfy rule compliance.")
    if any(v.get("rule") == "require_bullets" for v in rule_violations):
        suggestions.append("Use bullet points in required sections according to rules.")

    return suggestions[:6]


def _long_document_profile(
    *,
    expected_pages: int,
    compiled_rules: dict[str, Any] | None,
) -> dict[str, Any]:
    target_pages = int(((compiled_rules or {}).get("content_constraints") or {}).get("target_length_pages") or 0)
    long_form = expected_pages >= 30 or target_pages >= 30
    very_long_form = expected_pages >= 60 or target_pages >= 60

    return {
        "enabled": long_form,
        "veryLong": very_long_form,
        "targetPages": target_pages,
    }


def _page_count_tolerance(expected_pages: int, profile: dict[str, Any], validation_profile: str) -> int:
    if expected_pages <= 0:
        return 0
    if (validation_profile or "").strip().lower() == "high_range":
        return max(3, round(expected_pages * 0.75))
    if profile.get("veryLong"):
        return max(8, round(expected_pages * 0.2))
    if profile.get("enabled"):
        return max(4, round(expected_pages * 0.15))
    return 0


def _profile_thresholds(profile_name: str) -> dict[str, Any]:
    """Resolve default thresholds by profile.

    strict: existing production-grade validation behavior.
    balanced: moderate tolerance for real-world variation.
    high_range: broad acceptance range for long/variable academic drafts.
    """
    profile = (profile_name or "strict").strip().lower()
    if profile == "high_range":
        return {
            "minSimilarity": 82.0,
            "minHeadingMatchRatio": 0.6,
            "minVisualSimilarity": 20.0,
            "minVisualSimilarityPerPage": 20.0,
            "maxFailedPageRatio": 0.85,
            "enforceVisualHardGate": False,
        }
    if profile == "balanced":
        return {
            "minSimilarity": 85.0,
            "minHeadingMatchRatio": 0.68,
            "minVisualSimilarity": 35.0,
            "minVisualSimilarityPerPage": 35.0,
            "maxFailedPageRatio": 0.5,
            "enforceVisualHardGate": True,
        }
    return {
        "minSimilarity": 88.0,
        "minHeadingMatchRatio": 0.75,
        "minVisualSimilarity": 68.0,
        "minVisualSimilarityPerPage": 65.0,
        "maxFailedPageRatio": 0.0,
        "enforceVisualHardGate": True,
    }


def validate_rendered_artifacts(
    *,
    structured_text: str,
    pdf_path: Path,
    docx_path: Path,
    document_model: dict[str, Any] | None = None,
    layout_plan: dict[str, Any] | None = None,
    compiled_rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expected_headings = _section_signatures(structured_text)
    docx_text, docx_blocks = _extract_docx_text(docx_path)
    pdf_text, pdf_pages = _extract_pdf_text(pdf_path)
    visual_metrics = _extract_pdf_visual_metrics(pdf_path)
    expected_profiles = _expected_page_visual_profile(layout_plan, document_model)
    visual_comparison = _compare_visual_profiles(visual_metrics.get("pages") or [], expected_profiles, layout_plan)

    docx_similarity = _similarity(structured_text, docx_text)
    pdf_similarity = _similarity(structured_text, pdf_text)
    aggregate_similarity = round((docx_similarity * 0.45) + (pdf_similarity * 0.45) + 10.0, 2)
    aggregate_similarity = min(100.0, aggregate_similarity)

    rendered_headings = [line.strip().lower() for line in docx_text.splitlines() if line.strip()]
    heading_matches = 0
    for heading in expected_headings:
        if any(heading in rendered for rendered in rendered_headings):
            heading_matches += 1

    validation_profile = _active_validation_profile()
    expected_pages = int(layout_plan.get("totalPages") or 0) if layout_plan else 0
    long_doc_profile = _long_document_profile(expected_pages=expected_pages, compiled_rules=compiled_rules)
    page_tolerance = _page_count_tolerance(expected_pages, long_doc_profile, validation_profile)
    page_count_match = expected_pages == 0 or abs(pdf_pages - expected_pages) <= page_tolerance
    paragraph_count_match = True
    if layout_plan and layout_plan.get("placements"):
        paragraph_count_match = len(layout_plan.get("placements") or []) <= max(docx_blocks, 1) + 4

    acceptance_thresholds = _profile_thresholds(validation_profile)

    if long_doc_profile.get("enabled"):
        acceptance_thresholds.update(
            {
                "minSimilarity": 84.0,
                "minHeadingMatchRatio": 0.7,
                "minVisualSimilarity": 40.0,
                "minVisualSimilarityPerPage": 45.0,
                "maxFailedPageRatio": 0.5,
                "enforceVisualHardGate": False,
            }
        )

    if compiled_rules and compiled_rules.get("render_thresholds"):
        acceptance_thresholds.update(compiled_rules["render_thresholds"])

    heading_ratio = 1.0 if not expected_headings else round(heading_matches / len(expected_headings), 2)
    total_visual_pages = max(1, len(visual_comparison.get("pageScores") or []))
    failed_pages_count = len(visual_comparison.get("failedPages", []))
    has_failed_pages = failed_pages_count > 0
    failed_ratio = round(failed_pages_count / total_visual_pages, 3)
    allowed_failed_ratio = float(acceptance_thresholds.get("maxFailedPageRatio") or 0.0)
    visual_gate_required = bool(acceptance_thresholds.get("enforceVisualHardGate", True))
    rule_eval = _render_rule_penalties(structured_text, compiled_rules)
    accepted = (
        aggregate_similarity >= float(acceptance_thresholds["minSimilarity"])
        and heading_ratio >= float(acceptance_thresholds["minHeadingMatchRatio"])
        and (
            visual_comparison.get("averageScore", 0.0) >= float(acceptance_thresholds["minVisualSimilarity"])
            or not visual_gate_required
        )
        and (not has_failed_pages or failed_ratio <= allowed_failed_ratio or not visual_gate_required)
        and page_count_match
        and paragraph_count_match
        and len(rule_eval.get("violations") or []) == 0
    )

    issues: list[str] = []
    if aggregate_similarity < float(acceptance_thresholds["minSimilarity"]):
        issues.append(f"Rendered text similarity below threshold: {aggregate_similarity}")
    if heading_ratio < float(acceptance_thresholds["minHeadingMatchRatio"]):
        issues.append(f"Rendered heading match ratio below threshold: {heading_ratio}")
    if has_failed_pages:
        failed_pages = visual_comparison.get("failedPages", [])
        issues.append(f"Pages with low visual fidelity (score < {acceptance_thresholds.get('minVisualSimilarityPerPage')}%): {failed_pages}")
    if visual_comparison.get("averageScore", 0.0) < float(acceptance_thresholds["minVisualSimilarity"]):
        issues.extend(visual_comparison.get("issues") or ["Visual similarity below threshold."])
    if not page_count_match:
        if page_tolerance > 0:
            issues.append(f"PDF page count mismatch: expected {expected_pages}, got {pdf_pages} (tolerance {page_tolerance})")
        else:
            issues.append(f"PDF page count mismatch: expected {expected_pages}, got {pdf_pages}")
    if not paragraph_count_match:
        issues.append("Rendered block count diverged from the layout plan")
    if rule_eval.get("violations"):
        issues.extend([str(item.get("message") or "Rule compliance violation") for item in rule_eval["violations"]])

    structure_score = round(max(0.0, min(100.0, (heading_ratio * 70.0) + (30.0 if page_count_match else 0.0))), 2)
    formatting_score = round(
        max(
            0.0,
            min(
                100.0,
                (visual_comparison.get("averageScore", 0.0) * 0.6)
                + (aggregate_similarity * 0.4)
                - (10.0 if not paragraph_count_match else 0.0),
            ),
        ),
        2,
    )
    rule_score = float(rule_eval.get("score") or 0.0)
    score = round(max(0.0, (structure_score * 0.4) + (formatting_score * 0.35) + (rule_score * 0.25) - rule_eval["penalty"]), 2)
    suggestions = _build_suggestions(issues, rule_eval.get("violations") or [])

    return {
        "accepted": accepted,
        "issues": issues,
        "suggestions": suggestions,
        "score": score,
        "thresholds": acceptance_thresholds,
        "feedback": {
            "pageCountMismatch": not page_count_match,
            "headingMismatch": heading_ratio < float(acceptance_thresholds["minHeadingMatchRatio"]),
            "similarityMismatch": aggregate_similarity < float(acceptance_thresholds["minSimilarity"]),
            "visualMismatch": visual_comparison.get("averageScore", 0.0) < float(acceptance_thresholds["minVisualSimilarity"]),
            "longDocumentProfile": bool(long_doc_profile.get("enabled")),
            "validationProfile": validation_profile,
            "failedPageRatio": failed_ratio,
        },
        "componentScores": {
            "structureScore": structure_score,
            "formattingScore": formatting_score,
            "ruleComplianceScore": rule_score,
        },
        "ruleCompliance": {
            "violations": rule_eval.get("violations") or [],
            "penalty": rule_eval.get("penalty", 0.0),
        },
        "similarity": {
            "docx": docx_similarity,
            "pdf": pdf_similarity,
            "aggregate": aggregate_similarity,
            "headingMatchRatio": heading_ratio,
        },
        "visual": {
            "supported": visual_metrics.get("supported", False),
            "averageScore": visual_comparison.get("averageScore", 0.0),
            "pageScores": visual_comparison.get("pageScores", []),
            "failedPages": visual_comparison.get("failedPages", []),
            "issues": visual_comparison.get("issues", []),
        },
        "documentMetrics": {
            "docxParagraphs": docx_blocks,
            "pdfPages": pdf_pages,
            "expectedPages": expected_pages,
            "pageTolerance": page_tolerance,
            "failedPageRatio": failed_ratio,
        },
        "structuredFeedback": {
            "score": score,
            "issues": issues,
            "suggestions": suggestions,
        },
    }
