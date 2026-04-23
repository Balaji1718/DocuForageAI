# DocuForge AI

DocuForge AI is a full-stack document generation application. It turns user content, formatting rules, and optional reference documents into polished PDF and DOCX reports. The project combines a FastAPI backend, a React + Vite frontend, Firebase authentication, Firestore report storage, and optional AI-assisted generation.

## 1. Application Description

Use DocuForge AI when you want to:

- create structured reports from plain text or uploaded files
- extract formatting rules from a reference DOCX
- generate PDF and DOCX output
- track report history for the current Firebase user
- download completed files from a report details page

## 2. Clone the Repository

```powershell
git clone https://github.com/<your-org-or-user>/DocuForgeAI.git
cd DocuForgeAI
```

If you already have the repo on your machine, open the folder in VS Code and continue with the setup steps below.

## 3. Environment Setup

### Prerequisites

- Windows 10/11 with PowerShell
- Python 3.11 or newer
- Node.js 18 or newer
- Git
- A Firebase project and a valid Firebase Admin service-account JSON file

### Backend setup

This guide uses a root-level virtual environment named `venv`, because the startup script looks for `venv` in the repo root or `backend\\venv`.

1. Create the virtual environment and activate it:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

2. Install backend dependencies:

```powershell
python -m pip install -r backend\requirements.txt
```

3. Create your backend environment file:

- copy `backend/.env.example` to `backend/.env`
- fill in the values you need

Common backend settings:

- `GROQ_API_KEY`
- `OPENROUTER_API_KEY`
- `COHERE_API_KEY`
- `ALLOWED_ORIGINS`
- `MAX_CONTENT_CHARS`
- `RENDER_VALIDATION_PROFILE`
- `AI_TIMEOUT_SECONDS`

Optional backend settings:

- `OCR_ENABLED`
- `ENABLE_LARGE_CONTENT_REFINEMENT`
- `OUTPUT_DIR`
- `FRONTEND_DIST_DIR`

4. Add Firebase Admin credentials:

- place the service-account JSON at `backend/serviceAccount.json`
- or set `GOOGLE_APPLICATION_CREDENTIALS` to the full path of the JSON file

If you are moving the app to a different Firebase project, update the frontend Firebase config in `frontend/src/lib/firebase.ts` and make sure the backend service-account file matches the same project.

### Frontend setup

1. Install frontend dependencies:

```powershell
cd frontend
npm install
```

2. Build the frontend:

```powershell
npm run build
```

The frontend build is configured to output to the repo-level `dist/` folder, which is what the backend serves in single-server mode.

If you want to run the React app separately during development, set `VITE_API_BASE_URL` to your backend URL. For local development, that is usually `http://localhost:8000`.

## 4. Run the Application

### Recommended single-server mode

From the repo root, run:

```powershell
.\run-single-server.ps1 -Port 8006 -InstallDeps
```

This will:

- build the frontend
- install backend requirements if needed
- start FastAPI on `http://localhost:8006`
- serve both the API and the frontend from one local URL

If port 8006 is already in use, rerun with `-ForceRestart` or choose another port.

### Manual run

If you prefer to start each part yourself:

1. Build the frontend:

```powershell
cd frontend
npm run build
```

2. Start the backend:

```powershell
cd ..\backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000` in your browser.

## 5. How to Use the Application

1. Open the app in your browser.
2. Sign in with the Firebase account for this project.
3. Go to the Dashboard and click New Report.
4. Enter a title, the rules you want to follow, and the content to generate from.
5. Optionally add metadata, section structure, or rule overrides.
6. Optionally upload a DOCX reference document to extract formatting rules.
7. Click Generate and wait for the report to finish.
8. Open the report page to view the status, quality information, and download links.
9. Download the PDF or DOCX when the report is completed.

The dashboard refreshes report status automatically, so you can keep it open while generation is running.

## 6. Troubleshooting

- If the app says the frontend build is missing, run `npm run build` in the frontend folder again.
- If the PowerShell startup script cannot find Python, create and activate `venv` first.
- If PowerShell blocks the activation script, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` in the current shell and try again.
- If generation fails, check the backend console for API-key, Firebase, or service-account errors.
- If you run the frontend separately, confirm `VITE_API_BASE_URL` points to the correct backend URL.
- If you deploy the backend behind a different origin, update `ALLOWED_ORIGINS`.

## 7. Conclusion

If you follow the steps above, a new user can clone the repository, set up the environment, start the app, sign in, generate reports, and download the final PDF or DOCX files without needing to inspect the source code.

For backend-specific notes, see [backend/README.md](backend/README.md).
