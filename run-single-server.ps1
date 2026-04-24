param(
  [int]$Port = 8006,
  [switch]$ForceRestart,
  [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "[1/3] Building frontend..." -ForegroundColor Cyan
Set-Location (Join-Path $repoRoot "frontend")
if (-not (Test-Path (Join-Path (Get-Location) "node_modules"))) {
  npm install
  if ($LASTEXITCODE -ne 0) {
    throw "npm install failed with exit code $LASTEXITCODE"
  }
}
npm run build
if ($LASTEXITCODE -ne 0) {
  throw "npm run build failed with exit code $LASTEXITCODE"
}

Write-Host "[2/3] Preparing Python environment..." -ForegroundColor Cyan
$backendDir = Join-Path $repoRoot "backend"
$backendVenvPython = Join-Path $backendDir "venv\Scripts\python.exe"
$rootVenvPython = Join-Path $repoRoot "venv\Scripts\python.exe"

if (Test-Path $backendVenvPython) {
  $pythonExe = $backendVenvPython
} elseif (Test-Path $rootVenvPython) {
  $pythonExe = $rootVenvPython
} else {
  throw "No Python virtual environment found. Create backend\\venv or venv first."
}

Set-Location $backendDir
if ($InstallDeps) {
  $pyVersion = & $pythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
  $requirementsPath = Join-Path $backendDir "requirements.txt"
  $requirementsForInstall = $requirementsPath

  if ([version]$pyVersion -ge [version]"3.14") {
    # PyMuPDF currently has no stable wheel path for this environment; exclude it for local run.
    $tempReq = Join-Path $env:TEMP "docuforage_requirements_no_pymupdf.txt"
    Get-Content $requirementsPath | Where-Object { $_ -notmatch '^\s*pymupdf==' } | Set-Content $tempReq
    $requirementsForInstall = $tempReq
    Write-Host "Python $pyVersion detected: installing requirements without pymupdf for local runtime." -ForegroundColor Yellow
  }

  & $pythonExe -m pip install -r $requirementsForInstall
  if ($LASTEXITCODE -ne 0) {
    throw "pip install failed with exit code $LASTEXITCODE"
  }
} else {
  Write-Host "Skipping pip install (use -InstallDeps to install requirements)." -ForegroundColor Yellow
}

$portListener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($portListener) {
  if ($portListener.OwningProcess -le 0) {
    throw "Port $Port is already in use by the system (PID 0). Re-run with a different -Port."
  }

  if ($ForceRestart) {
    Write-Host "Port $Port is in use by PID $($portListener.OwningProcess). Stopping process..." -ForegroundColor Yellow
    Stop-Process -Id $portListener.OwningProcess -Force
  } else {
    throw "Port $Port is already in use by PID $($portListener.OwningProcess). Re-run with -ForceRestart or choose another -Port."
  }
}

Write-Host "[3/3] Starting backend + frontend on http://localhost:$Port ..." -ForegroundColor Green
& $pythonExe -m uvicorn main:app --host 0.0.0.0 --port $Port
