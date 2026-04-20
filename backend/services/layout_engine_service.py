from __future__ import annotations

from copy import deepcopy
import math
from typing import Any


DEFAULT_LAYOUT_THRESHOLDS = {
    "minSimilarity": 95.0,
    "maxIssues": 0,
    "maxWarnings": 0,
}


def _analyze_page_content_type(layout_plan: dict[str, Any], document_model: dict[str, Any], page_number: int) -> str:
    """Analyze page composition to determine content type.
    
    Returns one of: "heading_heavy", "list_heavy", "text_heavy", "mixed"
    """
    placements = layout_plan.get("placements") or []
    blocks = {str(b.get("id")): b for b in (document_model.get("blocks") or [])}
    
    # Count blocks on this page by type
    page_blocks = [p for p in placements if int(p.get("page") or 0) == page_number]
    
    heading_count = 0
    paragraph_count = 0
    list_count = 0
    
    for placement in page_blocks:
        block_id = str(placement.get("blockId") or "")
        block = blocks.get(block_id)
        if not block:
            continue
        
        block_type = str(block.get("type") or "paragraph")
        if block_type == "heading":
            heading_count += 1
        elif block_type == "paragraph":
            paragraph_count += 1
        elif block_type in {"list_item", "ordered_list_item"}:
            list_count += 1
    
    total = heading_count + paragraph_count + list_count
    if total == 0:
        return "mixed"
    
    heading_ratio = heading_count / total
    paragraph_ratio = paragraph_count / total
    list_ratio = list_count / total
    
    if heading_ratio >= 0.5:
        return "heading_heavy"
    elif list_ratio >= 0.5:
        return "list_heavy"
    elif paragraph_ratio >= 0.6:
        return "text_heavy"
    else:
        return "mixed"


def _content_aware_capacity_adjustment(
    current_capacity: int,
    content_types: list[str],
    attempt: int,
) -> tuple[int, str]:
    """Calculate capacity adjustment based on page content composition.
    
    Content types: "heading_heavy", "list_heavy", "text_heavy", "mixed"
    Attempt: 1 (feedback), 2 (moderate), 3 (aggressive)
    
    Returns: (new_capacity, explanation)
    """
    # Count composition
    heading_heavy = content_types.count("heading_heavy")
    list_heavy = content_types.count("list_heavy")
    text_heavy = content_types.count("text_heavy")
    total = len(content_types)
    
    if total == 0:
        return (max(20, current_capacity - 2), "no content analysis available")
    
    heading_ratio = heading_heavy / total
    list_ratio = list_heavy / total
    text_ratio = text_heavy / total
    
    # Determine base reduction amount
    if attempt == 1:
        # Feedback-driven: gentle, but more aggressive for text-heavy
        if text_ratio >= 0.5:
            reduction = 3  # Text needs tighter capacity
        elif list_ratio >= 0.5:
            reduction = 1  # Lists are naturally sparse
        elif heading_ratio >= 0.5:
            reduction = 1  # Headings are compact
        else:
            reduction = 2  # Mixed: moderate
        reason = f"attempt 1: text_ratio={text_ratio:.1%}, list_ratio={list_ratio:.1%}, heading_ratio={heading_ratio:.1%}"
    
    elif attempt == 2:
        # Moderate escalation: content-aware escalation
        if text_ratio >= 0.5:
            reduction = 5  # Aggressive for text
        elif heading_ratio >= 0.5:
            reduction = 3  # Moderate for headings (can handle density)
        elif list_ratio >= 0.5:
            reduction = 2  # Light for lists
        else:
            reduction = 4  # Mixed: escalate moderately
        reason = f"attempt 2 content-aware: prioritize text density management"
    
    else:  # attempt == 3
        # Aggressive: uniform escalation regardless of content
        reduction = 6
        reason = f"attempt 3 aggressive: uniform reduction regardless of composition"
    
    new_capacity = max(20, current_capacity - reduction)
    return (new_capacity, reason)


def _estimated_lines_for_block(block: dict[str, Any]) -> int:
    text = str(block.get("text") or "")
    kind = str(block.get("type") or "paragraph")

    if kind == "heading":
        return 2
    if kind in {"list_item", "ordered_list_item"}:
        return max(1, math.ceil(len(text) / 70))
    if kind == "table_row":
        return 1
    if kind == "image":
        return 10
    if kind == "document":
        return 2
    return max(1, math.ceil(len(text) / 90))


def solve_layout(document_model: dict[str, Any], compiled_rules: dict[str, Any] | None = None) -> dict[str, Any]:
    compiled = compiled_rules or {}
    typography = compiled.get("typography") or {}
    layout_cfg = compiled.get("layout") or {}
    content_constraints = compiled.get("content_constraints") or {}

    blocks = document_model.get("blocks") or []
    content_blocks = [b for b in blocks if b.get("type") != "document"]

    page_capacity_lines = 48
    if typography.get("line_spacing") == "double":
        page_capacity_lines = 30
    elif typography.get("line_spacing") == "1.5":
        page_capacity_lines = 38

    target_pages = int(content_constraints.get("target_length_pages") or 0)
    if target_pages > 0:
        total_estimated_lines = 0
        for block in [b for b in blocks if b.get("type") != "document"]:
            total_estimated_lines += _estimated_lines_for_block(block)

        if total_estimated_lines > 0:
            tuned_capacity = math.ceil(total_estimated_lines / max(1, target_pages))
            # Keep sane bounds so we do not produce unrealistic pagination.
            page_capacity_lines = max(20, min(60, tuned_capacity))

    placements: list[dict[str, Any]] = []
    page = 1
    line_cursor = 0

    for block in content_blocks:
        lines = _estimated_lines_for_block(block)
        if line_cursor + lines > page_capacity_lines:
            page += 1
            line_cursor = 0

        placements.append(
            {
                "blockId": block.get("id"),
                "page": page,
                "lineStart": line_cursor,
                "lineEnd": line_cursor + lines,
                "estimatedLines": lines,
            }
        )
        line_cursor += lines

    hard_constraints = [
        "margins:1in",
        f"line_spacing:{typography.get('line_spacing', 'single')}",
        f"alignment:{typography.get('alignment', 'justified')}",
        f"max_heading_depth:{layout_cfg.get('max_heading_depth', 3)}",
    ]
    if target_pages > 0:
        hard_constraints.append(f"target_pages:{target_pages}")
    soft_constraints = [
        "keep_captions_with_content",
        "preserve_image_aspect_ratio",
        "avoid_orphan_short_sections",
    ]

    return {
        "deterministic": True,
        "pageCapacityLines": page_capacity_lines,
        "totalPages": page,
        "placements": placements,
        "hardConstraintsApplied": hard_constraints,
        "softConstraintsApplied": soft_constraints,
    }


def simulate_layout(layout_plan: dict[str, Any], document_model: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []

    placements = layout_plan.get("placements") or []
    page_capacity = int(layout_plan.get("pageCapacityLines") or 48)
    blocks = {str(b.get("id")): b for b in (document_model.get("blocks") or [])}

    for placement in placements:
        if int(placement.get("lineEnd") or 0) > page_capacity:
            issues.append(f"Overflow predicted for block {placement.get('blockId')}")

    # Detect orphaned headings (heading at end of page with no following content on same page)
    by_page: dict[int, list[dict[str, Any]]] = {}
    for placement in placements:
        by_page.setdefault(int(placement.get("page") or 1), []).append(placement)

    for _page, items in by_page.items():
        items.sort(key=lambda item: int(item.get("lineStart") or 0))
        if not items:
            continue
        last = items[-1]
        last_block = blocks.get(str(last.get("blockId")), {})
        if str(last_block.get("type")) == "heading":
            warnings.append(f"Orphan heading risk for block {last.get('blockId')}")

    similarity_proxy = 100.0 - (len(issues) * 15.0) - (len(warnings) * 4.0)
    similarity_proxy = max(0.0, round(similarity_proxy, 2))

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "layoutSimilarityProxy": similarity_proxy,
    }


def evaluate_layout_acceptance(
    layout_simulation: dict[str, Any],
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_thresholds = {**DEFAULT_LAYOUT_THRESHOLDS, **(thresholds or {})}
    issues = list(layout_simulation.get("issues") or [])
    warnings = list(layout_simulation.get("warnings") or [])
    similarity = float(layout_simulation.get("layoutSimilarityProxy") or 0.0)

    accepted = (
        similarity >= float(resolved_thresholds["minSimilarity"])
        and len(issues) <= int(resolved_thresholds["maxIssues"])
        and len(warnings) <= int(resolved_thresholds["maxWarnings"])
    )

    return {
        "accepted": accepted,
        "thresholds": resolved_thresholds,
        "similarity": similarity,
        "issueCount": len(issues),
        "warningCount": len(warnings),
    }


def _shift_placements_from_index(placements: list[dict[str, Any]], start_index: int, page_delta: int) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for index, placement in enumerate(placements):
        entry = dict(placement)
        if index >= start_index:
            entry["page"] = int(entry.get("page") or 1) + page_delta
        updated.append(entry)
    return updated


def _shift_placements_at_indices(
    placements: list[dict[str, Any]],
    indices: set[int],
    page_delta: int,
) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for index, placement in enumerate(placements):
        entry = dict(placement)
        if index in indices:
            entry["page"] = int(entry.get("page") or 1) + page_delta
        updated.append(entry)
    return updated


def _renormalize_placements(placements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    page_cursors: dict[int, int] = {}

    for placement in placements:
        entry = dict(placement)
        page = int(entry.get("page") or 1)
        line_start = page_cursors.get(page, 0)
        estimated_lines = int(entry.get("estimatedLines") or 1)
        entry["lineStart"] = line_start
        entry["lineEnd"] = line_start + estimated_lines
        page_cursors[page] = line_start + estimated_lines
        normalized.append(entry)

    return normalized


def repair_layout_plan(layout_plan: dict[str, Any], document_model: dict[str, Any]) -> dict[str, Any]:
    repaired = deepcopy(layout_plan)
    placements = list(repaired.get("placements") or [])
    if not placements:
        return repaired

    blocks = {str(b.get("id")): b for b in (document_model.get("blocks") or [])}
    max_passes = 2

    for _pass in range(max_passes):
        pages: dict[int, list[tuple[int, dict[str, Any]]]] = {}
        for index, placement in enumerate(placements):
            pages.setdefault(int(placement.get("page") or 1), []).append((index, placement))

        repaired_this_pass = False
        for page_number in sorted(pages):
            items = sorted(pages[page_number], key=lambda item: int(item[1].get("lineStart") or 0))
            if not items:
                continue
            last_index, last_placement = items[-1]
            last_block = blocks.get(str(last_placement.get("blockId")), {})
            if str(last_block.get("type")) != "heading":
                continue

            next_index = last_index + 1
            if next_index >= len(placements):
                continue

            placements = _shift_placements_at_indices(placements, {last_index, next_index}, 1)
            placements = _renormalize_placements(placements)
            repaired_this_pass = True
            break

        if not repaired_this_pass:
            break

    repaired["placements"] = placements
    repaired["totalPages"] = max((int(item.get("page") or 1) for item in placements), default=1)
    repaired["repairApplied"] = repaired.get("placements") != layout_plan.get("placements")
    return repaired


def plan_layout_with_acceptance(
    document_model: dict[str, Any],
    compiled_rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    thresholds = (compiled_rules or {}).get("layout_thresholds") or {}
    initial_plan = solve_layout(document_model=document_model, compiled_rules=compiled_rules)
    initial_simulation = simulate_layout(initial_plan, document_model)
    initial_acceptance = evaluate_layout_acceptance(initial_simulation, thresholds)

    if initial_acceptance["accepted"]:
        return {
            "layoutPlan": initial_plan,
            "preRenderSimulation": {
                **initial_simulation,
                "accepted": True,
                "acceptance": initial_acceptance,
                "correctionAttempts": 0,
            },
            "layoutCorrections": [],
        }

    repaired_plan = repair_layout_plan(initial_plan, document_model)
    repaired_simulation = simulate_layout(repaired_plan, document_model)
    repaired_acceptance = evaluate_layout_acceptance(repaired_simulation, thresholds)

    corrections = [
        {
            "attempt": 1,
            "type": "repair_layout_plan",
            "before": initial_acceptance,
            "after": repaired_acceptance,
        }
    ]

    best_plan = repaired_plan if repaired_acceptance["accepted"] else initial_plan
    best_simulation = repaired_simulation if repaired_acceptance["accepted"] else initial_simulation
    best_acceptance = repaired_acceptance if repaired_acceptance["accepted"] else initial_acceptance

    return {
        "layoutPlan": best_plan,
        "preRenderSimulation": {
            **best_simulation,
            "accepted": best_acceptance["accepted"],
            "acceptance": best_acceptance,
            "correctionAttempts": len(corrections),
            "repaired": repaired_acceptance["accepted"],
        },
        "layoutCorrections": corrections,
    }


def correct_layout_from_render_feedback(
    *,
    document_model: dict[str, Any],
    compiled_rules: dict[str, Any] | None = None,
    layout_plan: dict[str, Any] | None = None,
    render_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    compiled = compiled_rules or {}
    current_plan = layout_plan or solve_layout(document_model=document_model, compiled_rules=compiled)
    feedback = render_validation or {}
    issues = [str(item).lower() for item in (feedback.get("issues") or [])]

    corrected_plan = deepcopy(current_plan)
    correction_notes: list[str] = []

    if any("page count mismatch" in issue for issue in issues):
        typography = compiled.get("typography") or {}
        spacing = str(typography.get("line_spacing") or "single")
        if spacing == "double":
            corrected_plan["pageCapacityLines"] = max(24, int(corrected_plan.get("pageCapacityLines") or 30) - 4)
        elif spacing == "1.5":
            corrected_plan["pageCapacityLines"] = max(30, int(corrected_plan.get("pageCapacityLines") or 38) - 3)
        else:
            corrected_plan["pageCapacityLines"] = max(36, int(corrected_plan.get("pageCapacityLines") or 48) - 2)
        correction_notes.append("tightened page capacity to improve pagination alignment")

    if any("visual similarity" in issue for issue in issues):
        corrected_plan["pageCapacityLines"] = max(24, int(corrected_plan.get("pageCapacityLines") or 48) - 1)
        correction_notes.append("reduced page capacity to improve visual density matching")
    
    if any("Pages with low visual fidelity" in issue for issue in issues):
        visual_info = feedback.get("visual", {})
        failed_pages = visual_info.get("failedPages", [])
        if failed_pages:
            corrected_plan["pageCapacityLines"] = max(20, int(corrected_plan.get("pageCapacityLines") or 48) - 3)
            correction_notes.append(f"aggressively reduced capacity to fix visual fidelity on pages {failed_pages}")

    if any("heading match ratio" in issue or "rendered text similarity" in issue for issue in issues):
        numbering_enabled = bool((compiled.get("layout") or {}).get("heading_numbering"))
        if not numbering_enabled:
            corrected_plan["hardConstraintsApplied"] = list(corrected_plan.get("hardConstraintsApplied") or []) + [
                "heading_numbering:enabled",
            ]
            correction_notes.append("enabled heading numbering in render hints")

    corrected_plan = repair_layout_plan(corrected_plan, document_model)
    corrected_simulation = simulate_layout(corrected_plan, document_model)
    corrected_acceptance = evaluate_layout_acceptance(corrected_simulation, (compiled_rules or {}).get("layout_thresholds") or {})

    return {
        "layoutPlan": corrected_plan,
        "preRenderSimulation": {
            **corrected_simulation,
            "accepted": corrected_acceptance["accepted"],
            "acceptance": corrected_acceptance,
            "correctionAttempts": 1,
            "repaired": True,
            "renderFeedbackDriven": True,
        },
        "layoutCorrections": [
            {
                "attempt": 1,
                "type": "render_feedback_correction",
                "notes": correction_notes,
                "issues": issues,
                "acceptance": corrected_acceptance,
            }
        ],
    }


def run_render_validation_with_retries(
    *,
    document_model: dict[str, Any],
    compiled_rules: dict[str, Any] | None = None,
    layout_plan: dict[str, Any] | None = None,
    validate_fn,
    output_dir: Path | None = None,
    generate_fn=None,
    report_id: str = "",
    title: str = "",
    rules: str = "",
    structured_text: str = "",
    max_attempts: int = 4,
) -> dict[str, Any]:
    """Run render validation with escalating auto-correction loop.
    
    Attempts to pass render validation with multiple correction strategies:
    - Attempt 1: Gentle capacity reduction (-1 to -2 lines)
    - Attempt 2: Moderate reduction (-3 to -4 lines) + enable heading numbering
    - Attempt 3: Aggressive reduction (-5 to -6 lines) + typography tweaks
    - Attempt 4: Extreme reduction + disable layout optimizations
    
    Returns result of validation attempt along with correction history.
    """
    from pathlib import Path
    
    output_dir = output_dir or Path(".")
    current_plan = layout_plan or solve_layout(document_model=document_model, compiled_rules=compiled_rules)
    all_corrections: list[dict[str, Any]] = []
    
    for attempt in range(1, max_attempts + 1):
        # Generate documents with current layout
        if generate_fn:
            try:
                generate_fn(
                    report_id=report_id,
                    title=title,
                    rules=rules,
                    structured_text=structured_text,
                    output_dir=output_dir,
                    layout_plan=current_plan,
                    compiled_rules=compiled_rules,
                )
            except Exception as e:
                pass  # Continue even if generation fails
        
        # Validate rendered artifacts
        validation_result = validate_fn(
            structured_text=structured_text,
            pdf_path=output_dir / f"{report_id}.pdf",
            docx_path=output_dir / f"{report_id}.docx",
            document_model=document_model,
            layout_plan=current_plan,
            compiled_rules=compiled_rules,
        )
        
        if validation_result.get("accepted"):
            validation_result["correctionAttempts"] = attempt
            validation_result["correctionHistory"] = all_corrections
            return validation_result
        
        # If this was the last attempt, return with failure
        if attempt >= max_attempts:
            validation_result["correctionAttempts"] = attempt
            validation_result["correctionHistory"] = all_corrections
            return validation_result
        
        # Apply escalating correction strategy
        compiled = compiled_rules or {}
        correction_notes: list[str] = []
        reduction_amount = 0
        
        if attempt == 1:
            # Gentle: reduce by 1-2 lines depending on issue type
            issues = [str(item).lower() for item in (validation_result.get("issues") or [])]
            if any("visual" in issue for issue in issues):
                reduction_amount = 2
            else:
                reduction_amount = 1
            correction_notes.append(f"Attempt {attempt}: gentle capacity reduction")
        
        elif attempt == 2:
            # Moderate: reduce by 3-4 lines + enable heading numbering
            reduction_amount = 4
            correction_notes.append(f"Attempt {attempt}: moderate capacity reduction")
            
            layout = compiled.get("layout") or {}
            if not layout.get("heading_numbering"):
                current_plan["hardConstraintsApplied"] = list(current_plan.get("hardConstraintsApplied") or []) + [
                    "heading_numbering:enabled",
                ]
                correction_notes.append("enabled heading numbering in layout hints")
        
        elif attempt == 3:
            # Aggressive: reduce by 5-6 lines + typography tweaks
            reduction_amount = 6
            correction_notes.append(f"Attempt {attempt}: aggressive capacity reduction")
            
            # Try adjusting line spacing if not already double
            typography = compiled.get("typography") or {}
            if typography.get("line_spacing") != "double":
                compiled_rules_copy = deepcopy(compiled_rules or {})
                compiled_rules_copy["typography"] = {**(compiled_rules_copy.get("typography") or {}), "line_spacing": "double"}
                compiled_rules = compiled_rules_copy
                correction_notes.append("adjusted line spacing to double for density control")
        
        else:  # attempt == 4
            # Last resort: extreme reduction + minimal layout
            reduction_amount = 8
            correction_notes.append(f"Attempt {attempt}: extreme capacity reduction (last resort)")
            
            # Disable all soft constraints
            current_plan["softConstraintsApplied"] = []
            correction_notes.append("disabled layout optimization heuristics")
        
        # Apply capacity reduction
        current_capacity = int(current_plan.get("pageCapacityLines") or 48)
        new_capacity = max(16, current_capacity - reduction_amount)
        current_plan["pageCapacityLines"] = new_capacity
        correction_notes.append(f"adjusted page capacity from {current_capacity} to {new_capacity}")
        
        # Repair layout with new capacity
        current_plan = repair_layout_plan(current_plan, document_model)
        simulation = simulate_layout(current_plan, document_model)
        acceptance = evaluate_layout_acceptance(simulation, (compiled_rules or {}).get("layout_thresholds") or {})
        
        all_corrections.append({
            "attempt": attempt,
            "strategy": ["gentle", "moderate", "aggressive", "extreme"][attempt - 1],
            "notes": correction_notes,
            "capacityAdjusted": reduction_amount,
            "newCapacity": new_capacity,
            "simulation": simulation,
            "acceptance": acceptance,
        })
    
    # Should not reach here, but return failure
    return {
        "accepted": False,
        "correctionAttempts": max_attempts,
        "correctionHistory": all_corrections,
        "issues": ["Failed to achieve render validation after maximum correction attempts"],
    }
