from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from firebase_admin import firestore
from pydantic import BaseModel, Field

from services.orchestration_service import run_generation_pipeline
from utils.helpers import safe_filename

log = logging.getLogger("docuforge.routes")


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


class GenerateRequest(BaseModel):
    userId: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=300)
    rules: str = Field(default="", max_length=10_000)
    referenceContent: str = Field(default="", max_length=100_000)
    referenceMimeType: str = Field(default="text/plain", max_length=200)
    content: str = Field(default="", max_length=200_000)
    inputFiles: list[dict[str, Any]] = Field(default_factory=list)


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
        report_ref.set(
            {
                "userId": req.userId,
                "title": req.title,
                "rules": req.rules,
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
                content=req.content,
                reference_content=req.referenceContent,
                reference_mime_type=req.referenceMimeType,
                input_files=req.inputFiles,
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
