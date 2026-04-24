from __future__ import annotations

import logging
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from services.ai_service import generate_structured_text
from services.doc_service import generate_documents
from services.document_model_service import build_document_model
from services.input_service import ingest_input_files
from services.layout_engine_service import correct_layout_from_render_feedback, plan_layout_with_acceptance
from services.render_validation_service import validate_rendered_artifacts
from utils.log_events import log_event

log = logging.getLogger("docuforge.orchestration")


def run_generation_pipeline(
    *,
    report_id: str,
    title: str,
    rules: str,
    content: str,
    reference_content: str,
    reference_mime_type: str,
    input_files: list[dict[str, Any]],
    sections: list[dict[str, str]] | None = None,
    max_content_chars: int,
    output_dir: Path,
    resolved_rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    log_event(log, logging.INFO, "pipeline_started", report_id=report_id, title=title)

    ingest_started = time.perf_counter()
    ingested = ingest_input_files(input_files, max_chars=max_content_chars)
    log_event(
        log,
        logging.INFO,
        "pipeline_input_processed",
        report_id=report_id,
        processed=ingested["summary"].get("processed", 0),
        failed=ingested["summary"].get("failed", 0),
        elapsed_ms=round((time.perf_counter() - ingest_started) * 1000, 2),
    )

    merged_content = content
    if ingested["content_text"]:
        merged_content = f"{content}\n\n{ingested['content_text']}"

    merged_reference = reference_content
    if ingested["reference_text"]:
        merged_reference = f"{reference_content}\n\n{ingested['reference_text']}".strip()

    if not merged_content.strip():
        raise ValueError("INPUT_VALIDATION: Please provide content text or upload at least one content file.")

    if len(merged_content) > max_content_chars:
        raise ValueError(
            f"INPUT_VALIDATION: Combined content too large after file extraction; max {max_content_chars} characters."
        )

    ai_started = time.perf_counter()
    section_plan = [
        {
            "title": str(item.get("title") or "").strip(),
            "mode": str(item.get("mode") or "auto_generate").strip(),
        }
        for item in (sections or [])
        if str(item.get("title") or "").strip()
    ]
    structured_text, parsed_rules, parsed_reference, validation_report = generate_structured_text(
        title=title,
        rules=rules,
        content=merged_content,
        reference_content=merged_reference,
        reference_mime_type=reference_mime_type,
        style_reference_rules=resolved_rules,
        section_plan=section_plan,
        chunk_size=8000,
        retries=1,
    )
    log_event(
        log,
        logging.INFO,
        "pipeline_ai_completed",
        report_id=report_id,
        validation_ok=bool(validation_report.get("ok")),
        validation_score=validation_report.get("qualityScore"),
        elapsed_ms=round((time.perf_counter() - ai_started) * 1000, 2),
    )

    dom_started = time.perf_counter()
    compiled_rules = (parsed_rules or {}).get("compiled") if isinstance(parsed_rules, dict) else {}
    if resolved_rules:
        compiled_rules = {
            **(compiled_rules or {}),
            "resolved_rules": resolved_rules,
        }
    document_model = build_document_model(title=title, structured_text=structured_text, compiled_rules=compiled_rules)
    log_event(
        log,
        logging.INFO,
        "pipeline_document_model_built",
        report_id=report_id,
        total_blocks=document_model.get("stats", {}).get("totalBlocks", 0),
        elapsed_ms=round((time.perf_counter() - dom_started) * 1000, 2),
    )

    layout_started = time.perf_counter()
    layout_result = plan_layout_with_acceptance(document_model=document_model, compiled_rules=compiled_rules)
    layout_plan = layout_result.get("layoutPlan", {})
    layout_simulation = layout_result.get("preRenderSimulation", {})
    log_event(
        log,
        logging.INFO,
        "pipeline_layout_simulated",
        report_id=report_id,
        total_pages=layout_plan.get("totalPages"),
        simulation_ok=layout_simulation.get("ok"),
        accepted=layout_simulation.get("accepted"),
        similarity_proxy=layout_simulation.get("layoutSimilarityProxy"),
        corrections=len(layout_result.get("layoutCorrections") or []),
        elapsed_ms=round((time.perf_counter() - layout_started) * 1000, 2),
    )

    docs_started = time.perf_counter()
    pdf_url, docx_url = generate_documents(
        report_id=report_id,
        title=title,
        rules=rules,
        structured_text=structured_text,
        output_dir=output_dir,
        layout_plan=layout_plan,
        compiled_rules=compiled_rules,
    )

    render_started = time.perf_counter()
    render_validation = validate_rendered_artifacts(
        structured_text=structured_text,
        pdf_path=output_dir / f"{report_id}.pdf",
        docx_path=output_dir / f"{report_id}.docx",
        document_model=document_model,
        layout_plan=layout_plan,
        compiled_rules=compiled_rules,
    )

    # Auto-correction loop with escalating strategies (max 3 retries = 4 total attempts)
    correction_attempt = 0
    all_correction_history: list[dict[str, Any]] = []
    render_retry_attempted = False
    max_correction_attempts = 3
    
    # Intelligent backoff: track validation scores to detect non-improving attempts
    previous_scores: list[float] = []
    consecutive_no_improvement = 0
    backoff_threshold = 2  # Fail early if 2+ consecutive attempts show no improvement
    
    def _extract_validation_score(validation: dict[str, Any]) -> float:
        """Extract composite validation score for comparison across attempts."""
        if validation.get("accepted"):
            return 100.0
        
        # Composite score: weighted average of available metrics
        similarity = validation.get("similarity", {}).get("aggregate") or 0.0
        visual = validation.get("visual", {}).get("averageScore") or 0.0
        heading_ratio = validation.get("similarity", {}).get("headingMatchRatio") or 0.0
        
        # Weight: text similarity 50%, visual 30%, heading match 20%
        score = (similarity * 0.5) + (visual * 0.3) + (heading_ratio * 100 * 0.2)
        return round(score, 2)
    
    initial_score = _extract_validation_score(render_validation)
    previous_scores.append(initial_score)

    def _improvement_likely(validation: dict[str, Any], score_history: list[float], no_improvement_count: int) -> bool:
        issues = [str(item).lower() for item in (validation.get("issues") or [])]
        if not issues:
            return False

        fixable_tokens = (
            "visual",
            "page count mismatch",
            "heading match ratio",
            "rendered text similarity",
            "block count",
        )
        has_fixable_issue = any(any(token in issue for token in fixable_tokens) for issue in issues)
        if not has_fixable_issue:
            return False

        if no_improvement_count >= backoff_threshold:
            return False

        if len(score_history) >= 3:
            deltas = [score_history[i] - score_history[i - 1] for i in range(1, len(score_history))]
            if all(delta <= 0.2 for delta in deltas[-2:]):
                return False

        return True
    
    while not render_validation.get("accepted") and correction_attempt < max_correction_attempts:
        # Check for intelligent backoff: if previous attempts didn't improve, fail early
        if len(previous_scores) >= 2:
            current_score = previous_scores[-1]
            previous_score = previous_scores[-2]
            
            # No improvement if score is same or worse
            if current_score <= previous_score:
                consecutive_no_improvement += 1
            else:
                consecutive_no_improvement = 0
            
            # Exit early if too many consecutive non-improving attempts
            if consecutive_no_improvement >= backoff_threshold:
                log_event(
                    log,
                    logging.INFO,
                    "pipeline_render_backoff_triggered",
                    report_id=report_id,
                    reason="consecutive non-improving attempts",
                    attempts_analyzed=len(previous_scores),
                    last_score=current_score,
                    elapsed_ms=round((time.perf_counter() - render_started) * 1000, 2),
                )
                # Break out of correction loop early
                break

        if not _improvement_likely(render_validation, previous_scores, consecutive_no_improvement):
            log_event(
                log,
                logging.INFO,
                "pipeline_render_retry_skipped",
                report_id=report_id,
                reason="improvement_unlikely",
                score_history=previous_scores,
                issues=render_validation.get("issues") or [],
                elapsed_ms=round((time.perf_counter() - render_started) * 1000, 2),
            )
            break
        
        render_retry_attempted = True
        correction_attempt += 1
        
        # Escalating correction strategies
        if correction_attempt == 1:
            # Gentle: feedback-driven correction
            correction_result = correct_layout_from_render_feedback(
                document_model=document_model,
                compiled_rules=compiled_rules,
                layout_plan=layout_plan,
                render_validation=render_validation,
            )
            strategy = "feedback_driven"
        else:
            # Escalate: more aggressive capacity reductions
            compiled = compiled_rules or {}
            corrected_plan = deepcopy(layout_plan)
            correction_notes: list[str] = []
            
            # Analyze content type on each page to inform correction strategy
            from services.layout_engine_service import (
                repair_layout_plan, simulate_layout, evaluate_layout_acceptance,
                _analyze_page_content_type, _content_aware_capacity_adjustment
            )
            
            placements = corrected_plan.get("placements") or []
            page_numbers = sorted(set(int(p.get("page") or 0) for p in placements))
            page_content_types = [
                _analyze_page_content_type(corrected_plan, document_model, page_num)
                for page_num in page_numbers
            ]
            
            if correction_attempt == 2:
                # Moderate escalation (content-aware)
                current_capacity = int(corrected_plan.get("pageCapacityLines") or 48)
                new_capacity, capacity_reason = _content_aware_capacity_adjustment(
                    current_capacity, page_content_types, correction_attempt
                )
                corrected_plan["pageCapacityLines"] = new_capacity
                correction_notes.append(f"content-aware moderate: {current_capacity} → {new_capacity} ({capacity_reason})")
                
                # Enable heading numbering if not already
                if not (compiled.get("layout") or {}).get("heading_numbering"):
                    corrected_plan["hardConstraintsApplied"] = list(corrected_plan.get("hardConstraintsApplied") or []) + [
                        "heading_numbering:enabled",
                    ]
                    correction_notes.append("enabled heading numbering for text clarity")
                strategy = "moderate_escalation"
            else:  # correction_attempt == 3
                # Aggressive last attempt (uniform)
                current_capacity = int(corrected_plan.get("pageCapacityLines") or 48)
                new_capacity, capacity_reason = _content_aware_capacity_adjustment(
                    current_capacity, page_content_types, correction_attempt
                )
                corrected_plan["pageCapacityLines"] = new_capacity
                correction_notes.append(f"aggressive: {current_capacity} → {new_capacity} ({capacity_reason})")
                
                # Disable soft constraints
                corrected_plan["softConstraintsApplied"] = []
                correction_notes.append("disabled layout optimization heuristics")
                strategy = "aggressive_escalation"
            
            corrected_plan = repair_layout_plan(corrected_plan, document_model)
            corrected_simulation = simulate_layout(corrected_plan, document_model)
            corrected_acceptance = evaluate_layout_acceptance(corrected_simulation, (compiled_rules or {}).get("layout_thresholds") or {})
            
            correction_result = {
                "layoutPlan": corrected_plan,
                "preRenderSimulation": {
                    **corrected_simulation,
                    "accepted": corrected_acceptance["accepted"],
                    "acceptance": corrected_acceptance,
                    "correctionAttempts": correction_attempt,
                    "repaired": True,
                    "renderFeedbackDriven": False,
                },
                "layoutCorrections": [
                    {
                        "attempt": correction_attempt,
                        "strategy": strategy,
                        "type": "escalated_correction",
                        "notes": correction_notes,
                    }
                ],
            }
        
        all_correction_history.append({
            "attempt": correction_attempt,
            "strategy": strategy,
            "notes": (correction_result.get("layoutCorrections") or [{}])[0].get("notes", []),
        })
        
        layout_result = {
            **layout_result,
            **correction_result,
        }
        layout_plan = layout_result.get("layoutPlan", layout_plan)
        layout_simulation = layout_result.get("preRenderSimulation", layout_simulation)
        
        log_event(
            log,
            logging.INFO,
            "pipeline_render_correction_applied",
            report_id=report_id,
            correction_attempt=correction_attempt,
            strategy=strategy,
            notes=(correction_result.get("layoutCorrections") or [{}])[0].get("notes", []),
            elapsed_ms=round((time.perf_counter() - render_started) * 1000, 2),
        )

        # Regenerate documents with corrected layout
        pdf_url, docx_url = generate_documents(
            report_id=report_id,
            title=title,
            rules=rules,
            structured_text=structured_text,
            output_dir=output_dir,
            layout_plan=layout_plan,
            compiled_rules=compiled_rules,
        )

        # Revalidate
        render_validation = validate_rendered_artifacts(
            structured_text=structured_text,
            pdf_path=output_dir / f"{report_id}.pdf",
            docx_path=output_dir / f"{report_id}.docx",
            document_model=document_model,
            layout_plan=layout_plan,
            compiled_rules=compiled_rules,
        )
        
        # Track validation score for intelligent backoff detection
        attempt_score = _extract_validation_score(render_validation)
        previous_scores.append(attempt_score)
        
        log_event(
            log,
            logging.INFO,
            "pipeline_render_attempt_scored",
            report_id=report_id,
            attempt=correction_attempt,
            score=attempt_score,
            accepted=render_validation.get("accepted"),
        )

    log_event(
        log,
        logging.INFO,
        "pipeline_render_validated",
        report_id=report_id,
        accepted=render_validation.get("accepted"),
        similarity=render_validation.get("similarity", {}).get("aggregate"),
        visual_similarity=render_validation.get("visual", {}).get("averageScore"),
        issues=len(render_validation.get("issues") or []),
        retried=render_retry_attempted,
        correction_attempts=correction_attempt,
        correction_strategies=[c.get("strategy") for c in all_correction_history],
        backoff_triggered=(consecutive_no_improvement >= backoff_threshold),
        validation_score_progression=previous_scores,
        elapsed_ms=round((time.perf_counter() - render_started) * 1000, 2),
    )

    if not render_validation.get("accepted"):
        target_pages = int(((compiled_rules or {}).get("content_constraints") or {}).get("target_length_pages") or 0)
        issues = render_validation.get("issues") or ["Rendered artifacts did not meet fidelity requirements."]
        if target_pages >= 120:
            log_event(
                log,
                logging.WARNING,
                "pipeline_render_validation_relaxed",
                report_id=report_id,
                target_pages=target_pages,
                issues=issues,
            )
        else:
            raise ValueError("RENDER_VALIDATION: " + "; ".join(issues))

    log_event(
        log,
        logging.INFO,
        "pipeline_documents_completed",
        report_id=report_id,
        pdf_url=pdf_url,
        docx_url=docx_url,
        elapsed_ms=round((time.perf_counter() - docs_started) * 1000, 2),
    )

    log_event(
        log,
        logging.INFO,
        "pipeline_completed",
        report_id=report_id,
        total_elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
    )

    return {
        "mergedContent": merged_content,
        "mergedReference": merged_reference,
        "inputProcessing": ingested["summary"],
        "parsedRules": parsed_rules,
        "parsedReference": parsed_reference,
        "documentModel": document_model,
        "layoutPlan": layout_plan,
        "preRenderSimulation": layout_simulation,
        "layoutCorrections": layout_result.get("layoutCorrections", []),
        "correctionHistory": all_correction_history,
        "correctionAttempts": correction_attempt,
        "correctionBackoffTriggered": consecutive_no_improvement >= backoff_threshold,
        "validationScoreProgression": previous_scores,
        "renderValidation": render_validation,
        "structuredFeedback": {
            "score": _extract_validation_score(render_validation),
            "issues": render_validation.get("issues") or [],
            "suggestions": render_validation.get("suggestions") or [],
        },
        "renderRetryAttempted": render_retry_attempted,
        "validation": validation_report,
        "pdfUrl": pdf_url,
        "docxUrl": docx_url,
    }
