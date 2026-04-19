from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from firebase_admin import firestore
from pydantic import BaseModel, Field

from services.ai_service import generate_structured_text
from services.doc_service import generate_documents
from utils.helpers import safe_filename

log = logging.getLogger("docuforge.routes")


class GenerateRequest(BaseModel):
    userId: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=300)
    rules: str = Field(default="", max_length=10_000)
    content: str = Field(..., min_length=1)


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
                "content": req.content,
                "status": "pending",
                "pdfUrl": "",
                "docxUrl": "",
                "createdAt": firestore.SERVER_TIMESTAMP,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }
        )

        try:
            report_ref.update({"status": "processing", "updatedAt": firestore.SERVER_TIMESTAMP})

            structured_text = generate_structured_text(
                title=req.title,
                rules=req.rules,
                content=req.content,
                chunk_size=8000,
                retries=1,
            )

            pdf_url, docx_url = generate_documents(
                report_id=report_id,
                title=req.title,
                rules=req.rules,
                structured_text=structured_text,
                output_dir=output_dir,
            )

            report_ref.update(
                {
                    "status": "completed",
                    "pdfUrl": pdf_url,
                    "docxUrl": docx_url,
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                }
            )
            return {
                "status": "completed",
                "reportId": report_id,
                "pdfUrl": pdf_url,
                "docxUrl": docx_url,
            }

        except Exception as exc:  # noqa: BLE001
            log.exception("Generation failed for report %s: %s", report_id, exc)
            report_ref.update(
                {
                    "status": "failed",
                    "error": str(exc),
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                }
            )
            return JSONResponse(
                status_code=500,
                content={"status": "failed", "reportId": report_id, "error": str(exc)},
            )

    return router
