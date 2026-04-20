# DocuForge AI

DocuForge AI is a full-stack report generation system with:

- FastAPI backend for authenticated report generation and file delivery
- React + Vite frontend for authentication, report creation, and downloads
- Firebase Auth/Firestore integration
- DOCX and PDF generation pipelines

## Run (Single Server Mode)

Preferred one-command startup (Windows PowerShell):

```powershell
./run-single-server.ps1 -Port 8006
```

This command:
- builds the frontend into `dist/`
- installs backend requirements
- starts FastAPI, serving both API and frontend from one server

Manual mode:

1. Build frontend from `frontend/`:

```bash
cd frontend
npm install
npm run build
```

2. Start backend from `backend/`:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Open: `http://localhost:8000`
