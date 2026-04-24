# DocuForge AI — FastAPI Backend

Rule-driven document compilation service. Generates DOCX (`python-docx`) and PDF (`reportlab`) from user content + formatting rules, with a multi-AI fallback (Groq → OpenRouter → Cohere → rule-based).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Place your Firebase service-account JSON next to `main.py` as `serviceAccount.json`
(or set `GOOGLE_APPLICATION_CREDENTIALS=/path/to/serviceAccount.json`).

Get it from: Firebase Console → Project settings → Service accounts → Generate new private key.

Set environment variables (or use a `.env` file):

```bash
export GROQ_API_KEY="gsk_..."
export OPENROUTER_API_KEY="sk-or-v1-..."
export COHERE_API_KEY="..."
# Optional CORS (comma-separated). Defaults to "*".
export ALLOWED_ORIGINS="https://your-frontend.example.com"
# Optional: enable OCR for image/scanned-PDF inputs (requires local tesseract runtime).
export OCR_ENABLED="true"
# Optional: run a final coherence pass when input is chunked.
export ENABLE_LARGE_CONTENT_REFINEMENT="true"
```

Optional OCR extras (not required for normal backend startup):

```bash
pip install pillow pytesseract
```

## Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Run Frontend + Backend On One Server

Build the frontend from `frontend/` first:

```bash
cd ../frontend
npm install
npm run build
```

Then start FastAPI from `backend/`:

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

FastAPI will serve:
- API endpoints on the same host (for example `/generate`, `/reports/{userId}`)
- frontend static files from `../dist`
- SPA routes via fallback to `dist/index.html`

If you want a single command that rebuilds the frontend and then starts FastAPI, run:

```bash
python main.py --host 0.0.0.0 --port 8000
```

Optional:
- set `FRONTEND_DIST_DIR` if your built frontend path is not `../dist`

## Endpoints

| Method | Path                | Description                              |
|--------|---------------------|------------------------------------------|
| POST   | `/generate`         | Generate report (requires `Authorization: Bearer <Firebase ID token>`) |
| GET    | `/reports/{userId}` | List user reports (auth required)        |
| GET    | `/files/{filename}` | Download generated PDF/DOCX              |
| GET    | `/health`           | Liveness check                           |

## Deploy

Works on any Python host (Render, Fly.io, Railway, Google Cloud Run, a VPS).
Persist the `outputs/` directory if you want files to survive restarts.

After deploying, open the DocuForge AI frontend → Settings → set the Backend URL to your deployed URL.

## Generation V2 Production Gates

Run the real Docker + LibreOffice self-compare check:

```bash
docker compose -f docker-compose.generation-v2.yml run --rm generation-v2-real-render-test
```

This target builds the pinned LibreOffice renderer image and runs:
- `tests/test_generation_v2_real_renderer.py`

Template registry persistence rollout plan is tracked in:
- `docs/template_registry_persistence_plan.md`

Template registry backend selection:
- `GENV2_TEMPLATE_REGISTRY_BACKEND=memory|postgres`
- `GENV2_TEMPLATE_REGISTRY_DSN=postgresql://...` (or `DATABASE_URL`)

CI production gates workflow:
- `.github/workflows/generation-v2-production-gates.yml`
