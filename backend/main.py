"""DocuForge AI — FastAPI backend.

Endpoints:
  POST /generate            — generate a report (auth required)
  GET  /reports/{userId}    — list reports for a user (auth required)
  GET  /files/{filename}    — download generated PDF/DOCX
  GET  /health              — liveness
"""
from __future__ import annotations

import os
import re
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import firebase_admin
from firebase_admin import auth as fb_auth, credentials, firestore

from ai_fallback import generate_with_fallback
from doc_generator import build_docx, build_pdf

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("docuforge")

# ---- Firebase Admin init -----------------------------------------------------
SERVICE_ACCOUNT = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or str(
    Path(__file__).parent / "serviceAccount.json"
)

if not firebase_admin._apps:
    if Path(SERVICE_ACCOUNT).exists():
        cred = credentials.Certificate(SERVICE_ACCOUNT)
        firebase_admin.initialize_app(cred)
        log.info("Firebase Admin initialized with service account: %s", SERVICE_ACCOUNT)
    else:
        # Application Default Credentials (e.g., on GCP)
        firebase_admin.initialize_app()
        log.warning("serviceAccount.json not found; using Application Default Credentials.")

db = firestore.client()

# ---- App ---------------------------------------------------------------------
app = FastAPI(title="DocuForge AI", version="1.0.0")

origins_env = os.getenv("ALLOWED_ORIGINS", "*")
origins = [o.strip() for o in origins_env.split(",")] if origins_env != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", Path(__file__).parent / "outputs"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MAX_CONTENT_CHARS = int(os.getenv("MAX_CONTENT_CHARS", "200000"))  # 200k hard limit


# ---- Auth dependency ---------------------------------------------------------
def verify_token(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        decoded = fb_auth.verify_id_token(token)
        return decoded
    except Exception as e:  # pragma: no cover
        log.warning("Token verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid token")


# ---- Models ------------------------------------------------------------------
class GenerateRequest(BaseModel):
    userId: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=300)
    rules: str = Field(default="", max_length=10_000)
    content: str = Field(..., min_length=1)


# ---- Helpers -----------------------------------------------------------------
def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:120]


def _chunk(text: str, size: int = 8000) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


# ---- Routes ------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/files/{filename}")
def get_file(filename: str):
    safe = _safe_filename(filename)
    path = OUTPUT_DIR / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    media = (
        "application/pdf"
        if path.suffix.lower() == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(path, media_type=media, filename=safe)


@app.get("/reports/{user_id}")
def list_reports(user_id: str, user=Depends(verify_token)):
    if user.get("uid") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    docs = (
        db.collection("reports")
        .where("userId", "==", user_id)
        .stream()
    )
    items: list[dict[str, Any]] = []
    for d in docs:
        data = d.to_dict() or {}
        data["id"] = d.id
        # Convert Firestore timestamps to ISO strings for JSON
        for k in ("createdAt", "updatedAt"):
            v = data.get(k)
            if hasattr(v, "isoformat"):
                data[k] = v.isoformat()
        items.append(data)
    items.sort(key=lambda x: str(x.get("createdAt") or ""), reverse=True)
    return {"reports": items}


@app.post("/generate")
def generate(req: GenerateRequest, user=Depends(verify_token)):
    if user.get("uid") != req.userId:
        raise HTTPException(status_code=403, detail="userId does not match authenticated user")

    if len(req.content) > MAX_CONTENT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Content too large; max {MAX_CONTENT_CHARS} characters.",
        )

    # 1) Create report doc with status=pending
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
        # 2) Move to processing
        report_ref.update({"status": "processing", "updatedAt": firestore.SERVER_TIMESTAMP})

        # 3) AI step (with chunking for large content) + fallback
        chunks = _chunk(req.content, 8000)
        structured_sections: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            section = generate_with_fallback(
                title=req.title,
                rules=req.rules,
                content=chunk,
                chunk_index=idx,
                total_chunks=len(chunks),
            )
            structured_sections.append(section)
        structured_text = "\n\n".join(structured_sections)

        # 4) Generate files
        docx_path = OUTPUT_DIR / f"{report_id}.docx"
        pdf_path = OUTPUT_DIR / f"{report_id}.pdf"
        build_docx(req.title, req.rules, structured_text, docx_path)
        build_pdf(req.title, req.rules, structured_text, pdf_path)

        pdf_url = f"/files/{report_id}.pdf"
        docx_url = f"/files/{report_id}.docx"

        # 5) Mark completed
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

    except Exception as e:  # noqa: BLE001
        log.exception("Generation failed: %s", e)
        report_ref.update(
            {
                "status": "failed",
                "error": str(e),
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }
        )
        return JSONResponse(
            status_code=500,
            content={"status": "failed", "reportId": report_id, "error": str(e)},
        )


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):  # pragma: no cover
    log.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"error": str(exc)})
