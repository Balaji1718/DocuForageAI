from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from firebase_admin import firestore
from pydantic import BaseModel, Field

from services.orchestration_service import run_generation_pipeline
from services.rule_resolver import resolve_rules, create_rules_record, validate_rules
from rule_extractor import extract_rules
from utils.helpers import safe_filename

log = logging.getLogger("docuforge.routes")


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_rule_overrides(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = payload or {}
    out: dict[str, Any] = {}

    body_font = str(raw.get("bodyFont") or "").strip()
    if body_font:
        out["body_font"] = body_font

    body_size_pt = _to_float(raw.get("bodySizePt"))
    if body_size_pt and body_size_pt > 0:
        out["body_size_halfpt"] = int(round(body_size_pt * 2.0))

    margin_map = {
        "marginTopIn": "margin_top_dxa",
        "marginLeftIn": "margin_left_dxa",
        "marginBottomIn": "margin_bottom_dxa",
        "marginRightIn": "margin_right_dxa",
    }
    for source_key, target_key in margin_map.items():
        margin_in = _to_float(raw.get(source_key))
        if margin_in is not None and margin_in >= 0:
            out[target_key] = int(round(margin_in * 1440.0))

    line_spacing_pt = _to_float(raw.get("lineSpacingPt"))
    if line_spacing_pt and line_spacing_pt > 0:
        # body_line_spacing_val uses twips (1/20 pt)
        out["body_line_spacing_val"] = int(round(line_spacing_pt * 20.0))

    return out


def _sanitize_sections(items: list[dict[str, str]] | None) -> list[dict[str, str]]:
    allowed_modes = {"auto_generate", "user_provides", "skip"}
    sanitized: list[dict[str, str]] = []
    for item in items or []:
        title = str(item.get("title") or "").strip()[:200]
        if not title:
            continue
        mode = str(item.get("mode") or "auto_generate").strip()
        if mode not in allowed_modes:
            mode = "auto_generate"
        sanitized.append({"title": title, "mode": mode})
    return sanitized


def _public_error_message(detail: str, quality_failure: bool) -> str:
    if detail.startswith("INPUT_VALIDATION:"):
        return detail.replace("INPUT_VALIDATION:", "", 1).strip()
    if detail.startswith("RENDER_VALIDATION:"):
        return "Generated output did not meet render fidelity requirements."
    if quality_failure:
        return "Generated output did not meet quality requirements after retry."
    return "Generation failed due to a temporary processing issue. Please try again."


def _error_code(detail: str, quality_failure: bool) -> str:
    if detail.startswith("INPUT_VALIDATION:"):
        return "input_validation"
    if detail.startswith("RENDER_VALIDATION:"):
        return "render_validation"
    if quality_failure:
        return "quality_validation"
    return "processing_failure"


def _report_artifact_path(output_dir: Path, value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    filename = Path(raw.split("?", 1)[0]).name
    if not filename:
        return None
    return output_dir / safe_filename(filename)


def _delete_report_artifacts(output_dir: Path, report_data: dict[str, Any]) -> list[str]:
    removed_files: list[str] = []
    for key in ("pdfUrl", "docxUrl"):
        artifact_path = _report_artifact_path(output_dir, report_data.get(key))
        if artifact_path is None:
            continue

        try:
            if artifact_path.exists():
                artifact_path.unlink()
                removed_files.append(artifact_path.name)
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to delete report artifact %s: %s", artifact_path, exc)

    return removed_files


class GenerateRequest(BaseModel):
    userId: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=300)
    rules: str = Field(default="", max_length=10_000)
    rulesId: str = Field(default="", max_length=200)
    referenceContent: str = Field(default="", max_length=100_000)
    referenceMimeType: str = Field(default="text/plain", max_length=200)
    content: str = Field(default="", max_length=200_000)
    inputFiles: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    sections: list[dict[str, str]] = Field(default_factory=list)
    ruleOverrides: dict[str, Any] = Field(default_factory=dict)


def create_report_router(
    db,
    output_dir: Path,
    max_content_chars: int,
    verify_token: Callable[..., dict],
) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict:
        return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}

    @router.get("/files/{filename}")
    def get_file(filename: str):
        safe = safe_filename(filename)
        path = output_dir / safe
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        media = (
            "application/pdf"
            if path.suffix.lower() == ".pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        return FileResponse(path, media_type=media, filename=safe)

    @router.get("/reports/{user_id}")
    def list_reports(user_id: str, user=Depends(verify_token)):
        log.info("Listing reports for user %s", user_id)
        if user.get("uid") != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        docs = db.collection("reports").where("userId", "==", user_id).stream()
        items: list[dict[str, Any]] = []
        for doc in docs:
            data = doc.to_dict() or {}
            data["id"] = doc.id
            for key in ("createdAt", "updatedAt"):
                value = data.get(key)
                if hasattr(value, "isoformat"):
                    data[key] = value.isoformat()
            items.append(data)

        items.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
        return {"reports": items}

    @router.delete("/reports/{report_id}")
    def delete_report(report_id: str, user=Depends(verify_token)):
        log.info("Delete report request for report %s", report_id)

        report_ref = db.collection("reports").document(report_id)
        report_doc = report_ref.get()
        if not getattr(report_doc, "exists", False):
            raise HTTPException(status_code=404, detail="Report not found")

        report_data = report_doc.to_dict() or {}
        if user.get("uid") != report_data.get("userId"):
            raise HTTPException(status_code=403, detail="Forbidden")

        removed_files = _delete_report_artifacts(output_dir, report_data)
        report_ref.delete()

        return {
            "status": "deleted",
            "reportId": report_id,
            "removedFiles": removed_files,
        }

    @router.post("/extract-rules")
    async def extract_document_rules(
        reference: UploadFile | None = File(None),
        file: UploadFile | None = File(None),
        document_type: str = "generic",
        notes: str = "",
        user=Depends(verify_token)
    ):
        """
        Extract formatting rules from a DOCX document.
        
        Phase 2: Rules Extraction & Storage
        - Accepts DOCX file upload
        - Extracts formatting using Phase 1 extractor
        - Merges with system defaults
        - Stores in Firestore
        - Returns rules_id for later use
        """
        try:
            upload = reference or file
            if upload is None:
                return JSONResponse(status_code=422, content={"error": "reference file is required"})

            log.info("Extract rules request from user %s for file %s", user.get("uid"), upload.filename)
            
            # Read file content
            content = await upload.read()
            
            if not content:
                return JSONResponse(status_code=422, content={"error": "file is empty"})
            
            if len(content) > 50_000_000:  # 50MB max
                return JSONResponse(status_code=422, content={"error": "file too large (max 50MB)"})
            
            # Phase 1: Extract rules from DOCX
            log.info("Extracting rules from %s", upload.filename)
            extracted_rules = extract_rules(content, upload.filename)
            
            # Phase 2: Merge with system defaults
            log.info("Resolving rules with system defaults")
            resolved_rules = resolve_rules(extracted_rules=extracted_rules)
            
            # Validate merged rules
            is_valid, warnings = validate_rules(resolved_rules)
            if not is_valid:
                log.warning("Rule validation warnings: %s", warnings)
            
            # Create storage record
            record = create_rules_record(
                resolved_rules,
                document_name=upload.filename,
                document_type=document_type,
                notes=notes,
            )
            
            # Store in Firestore
            log.info("Storing rules with ID %s", record["rules_id"])
            rules_ref = db.collection("document_rules").document(record["rules_id"])
            rules_ref.set({
                "user_id": user.get("uid"),
                "source_filename": upload.filename,
                "rules_id": record["rules_id"],
                "document_name": record["document_name"],
                "document_type": record["document_type"],
                "notes": record["notes"],
                "created_at": record["created_at"],
                "status": record["status"],
                "rules": record["rules"],
                "confidence": resolved_rules.get("confidence", "high"),
                "validation": {
                    "is_valid": is_valid,
                    "warnings": warnings,
                },
                "firestore_timestamp": firestore.SERVER_TIMESTAMP,
            })
            
            # Return success response
            return {
                "rules_id": record["rules_id"],
                "rules": record["rules"],
                "success": True,
                "message": f"Rules extracted from {upload.filename}",
                "validation": {
                    "is_valid": is_valid,
                    "warnings": warnings,
                },
                "rules_summary": {
                    "page_width": f"{resolved_rules['page_width_dxa']/1440:.2f}\"",
                    "page_height": f"{resolved_rules['page_height_dxa']/1440:.2f}\"",
                    "margins": {
                        "top": f"{resolved_rules['margin_top_dxa']/1440:.2f}\"",
                        "left": f"{resolved_rules['margin_left_dxa']/1440:.2f}\"",
                    },
                    "body_font": resolved_rules["body_font"],
                    "body_size": f"{resolved_rules['body_size_halfpt']/2}pt",
                    "sections_detected": len(resolved_rules.get("detected_section_headings", [])),
                    "tables_found": resolved_rules.get("table_count", 0),
                    "confidence": resolved_rules.get("confidence", "unknown"),
                },
            }
            
        except HTTPException:
            raise
        except Exception as e:
            log.error("Error extracting rules: %s", str(e))
            return JSONResponse(status_code=422, content={"error": f"Failed to extract rules: {str(e)}"})

    @router.post("/generate")
    def generate(req: GenerateRequest, user=Depends(verify_token)):
        log.info("Generate request received for user %s", req.userId)

        if user.get("uid") != req.userId:
            raise HTTPException(status_code=403, detail="userId does not match authenticated user")

        if len(req.content) > max_content_chars:
            raise HTTPException(
                status_code=413,
                detail=f"Content too large; max {max_content_chars} characters.",
            )

        report_ref = db.collection("reports").document()
        report_id = report_ref.id
        resolved_rules: dict[str, Any] | None = None

        # Optional: load previously extracted+resolved rules by rulesId.
        if req.rulesId:
            try:
                rules_collection = db.collection("document_rules")
                rules_doc_ref = rules_collection.document(req.rulesId)
                rules_doc = rules_doc_ref.get()
                if getattr(rules_doc, "exists", False):
                    rules_payload = rules_doc.to_dict() or {}
                    maybe_rules = rules_payload.get("rules")
                    if isinstance(maybe_rules, dict):
                        resolved_rules = maybe_rules
                        log.info("Loaded stored rules for rulesId=%s", req.rulesId)
                    else:
                        log.warning("document_rules %s found but missing rules payload", req.rulesId)
                else:
                    log.warning("No stored rules found for rulesId=%s", req.rulesId)
            except Exception as exc:  # noqa: BLE001
                # Never block generation if optional rules lookup fails.
                log.warning("Failed to load stored rules for rulesId=%s: %s", req.rulesId, exc)

        sections_payload = _sanitize_sections(req.sections)
        overrides_payload = _build_rule_overrides(req.ruleOverrides)
        if resolved_rules is None:
            resolved_rules = resolve_rules(user_overrides=overrides_payload or None)
        else:
            resolved_rules = resolve_rules(extracted_rules=resolved_rules, user_overrides=overrides_payload or None)

        report_ref.set(
            {
                "userId": req.userId,
                "title": req.title,
                "rules": req.rules,
                "rulesId": req.rulesId,
                "referenceContent": req.referenceContent,
                "referenceMimeType": req.referenceMimeType,
                "content": req.content,
                "inputFiles": [
                    {
                        "filename": str(item.get("filename") or "unnamed")[:260],
                        "mimeType": str(item.get("mimeType") or "application/octet-stream")[:200],
                        "role": str(item.get("role") or "content")[:20],
                    }
                    for item in req.inputFiles
                ],
                "metadata": {
                    k: str(v)[:500] for k, v in (req.metadata or {}).items()
                },
                "sections": sections_payload,
                "ruleOverrides": {
                    k: str(v)[:200] for k, v in (req.ruleOverrides or {}).items()
                },
                "inputProcessing": {"processed": 0, "failed": 0, "files": []},
                "status": "pending",
                "pdfUrl": "",
                "docxUrl": "",
                "createdAt": firestore.SERVER_TIMESTAMP,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }
        )

        try:
            report_ref.update({"status": "processing", "updatedAt": firestore.SERVER_TIMESTAMP})

            pipeline = run_generation_pipeline(
                report_id=report_id,
                title=req.title,
                rules=req.rules,
                resolved_rules=resolved_rules,
                content=req.content,
                reference_content=req.referenceContent,
                reference_mime_type=req.referenceMimeType,
                input_files=req.inputFiles,
                sections=sections_payload,
                max_content_chars=max_content_chars,
                output_dir=output_dir,
            )

            report_ref.update(
                {
                    "content": pipeline["mergedContent"],
                    "inputProcessing": pipeline["inputProcessing"],
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                }
            )

            report_ref.update(
                {
                    "parsedRules": pipeline["parsedRules"],
                    "parsedReference": pipeline["parsedReference"],
                    "documentModel": pipeline.get("documentModel", {}),
                    "layoutPlan": pipeline.get("layoutPlan", {}),
                    "preRenderSimulation": pipeline.get("preRenderSimulation", {}),
                    "layoutCorrections": pipeline.get("layoutCorrections", []),
                    "renderValidation": pipeline.get("renderValidation", {}),
                    "structuredFeedback": pipeline.get("structuredFeedback", {}),
                    "validation": pipeline["validation"],
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                }
            )

            report_ref.update(
                {
                    "status": "completed",
                    "pdfUrl": pipeline["pdfUrl"],
                    "docxUrl": pipeline["docxUrl"],
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                }
            )
            return {
                "status": "completed",
                "reportId": report_id,
                "pdfUrl": pipeline["pdfUrl"],
                "docxUrl": pipeline["docxUrl"],
            }

        except Exception as exc:  # noqa: BLE001
            log.exception("Generation failed for report %s: %s", report_id, exc)
            detail = str(exc)
            if detail.startswith("INPUT_VALIDATION:"):
                status_code = 400
            else:
                status_code = 500
            quality_failure = "Output quality validation failed after one retry" in detail or detail.startswith("RENDER_VALIDATION:")
            error_text = _public_error_message(detail, quality_failure)
            error_code = _error_code(detail, quality_failure)
            quality_errors: list[str] = []
            if quality_failure:
                parts = detail.split(":", 1)
                if len(parts) == 2:
                    quality_errors = [p.strip() for p in parts[1].split(";") if p.strip()]
            report_ref.update(
                {
                    "status": "failed",
                    "error": error_text,
                    "errorCode": error_code,
                    "qualityFailure": quality_failure,
                    "qualityErrors": quality_errors,
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                }
            )
            return JSONResponse(
                status_code=status_code,
                content={
                    "status": "failed",
                    "reportId": report_id,
                    "error": error_text,
                    "errorCode": error_code,
                    "qualityFailure": quality_failure,
                    "qualityErrors": quality_errors,
                },
            )

    return router
