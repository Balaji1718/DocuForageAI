"""DocuForge AI — FastAPI backend.

Endpoints:
  POST /generate            — generate a report (auth required)
  GET  /reports/{userId}    — list reports for a user (auth required)
  GET  /files/{filename}    — download generated PDF/DOCX
  GET  /health              — liveness
"""
from __future__ import annotations

import argparse
import os
import logging
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

import firebase_admin
from firebase_admin import credentials, firestore

from routes.report_routes import create_report_router
from utils.auth import verify_token

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

FRONTEND_DIST_DIR = Path(
    os.getenv("FRONTEND_DIST_DIR", Path(__file__).resolve().parent.parent / "dist")
)
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"

MAX_CONTENT_CHARS = int(os.getenv("MAX_CONTENT_CHARS", "200000"))  # 200k hard limit

def _frontend_index_or_404() -> FileResponse:
    if not FRONTEND_INDEX_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Frontend build not found. Run 'npm run build' in the frontend folder "
                "or set FRONTEND_DIST_DIR."
            ),
        )
    return FileResponse(FRONTEND_INDEX_FILE)


def _ensure_frontend_build() -> None:
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    if not frontend_dir.exists():
        raise RuntimeError(f"Frontend directory not found at {frontend_dir}")

    npm_executable = shutil.which("npm")
    if not npm_executable:
        raise RuntimeError("npm is required to build the frontend automatically.")

    node_modules_dir = frontend_dir / "node_modules"
    if not node_modules_dir.exists():
        log.info("Installing frontend dependencies in %s", frontend_dir)
        subprocess.run([npm_executable, "install"], cwd=frontend_dir, check=True)

    log.info("Building frontend in %s", frontend_dir)
    subprocess.run([npm_executable, "run", "build"], cwd=frontend_dir, check=True)

    if not FRONTEND_INDEX_FILE.exists():
        raise RuntimeError(
                        f"Frontend build completed but {FRONTEND_INDEX_FILE} is still missing."
        )


app.include_router(
    create_report_router(
        db=db,
        output_dir=OUTPUT_DIR,
        max_content_chars=MAX_CONTENT_CHARS,
        verify_token=verify_token,
    )
)


@app.get("/", include_in_schema=False)
def frontend_root():
    return _frontend_index_or_404()


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):  # pragma: no cover
    log.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_fallback(full_path: str):
    # Prevent catch-all from masking API/docs endpoints when a route truly does not exist.
    reserved_prefixes = ("generate", "reports", "files", "health", "docs", "redoc", "openapi.json")
    if full_path == "" or full_path.startswith(reserved_prefixes):
        raise HTTPException(status_code=404, detail="Not found")

    candidate = (FRONTEND_DIST_DIR / full_path).resolve()
    try:
        candidate.relative_to(FRONTEND_DIST_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if candidate.exists() and candidate.is_file():
        return FileResponse(candidate)

    return _frontend_index_or_404()


def _main() -> None:
    parser = argparse.ArgumentParser(description="Start DocuForge AI as a single server.")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    args = parser.parse_args()

    _ensure_frontend_build()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    _main()
