<#
  Arranque local (desarrollo) sin Docker: API + workers con SQLite en una carpeta de datos fuera del repositorio.
  Uso: .\scripts\windows\run-local.ps1 -DataDir C:\dev\radar-data
#>
param([string]$DataDir = "C:\dev\radar-data", [string]$Venv = "C:\dev\venvs\radar")
$root = Resolve-Path "$PSScriptRoot\..\.."
New-Item -ItemType Directory -Force $DataDir | Out-Null
if (-not (Test-Path $Venv)) { python -m venv $Venv; & "$Venv\Scripts\pip" install -r "$root\backend\requirements-dev.txt" }
$env:DATA_DIR = $DataDir; $env:DATABASE_URL = "sqlite:///$($DataDir -replace '\\','/')/radar.db"
if (-not (Test-Path "$root\frontend\dist")) { Push-Location "$root\frontend"; npm ci; npx vite build; Pop-Location }
Push-Location "$root\backend"
Start-Process "$Venv\Scripts\python" "-m app.workers market" -WindowStyle Hidden
Start-Process "$Venv\Scripts\python" "-m app.workers research" -WindowStyle Hidden
Write-Host "Primer uso: python scripts\create_admin.py admin   (te pedirá la contraseña)"
& "$Venv\Scripts\python" -m uvicorn app.main:app --port 8000
