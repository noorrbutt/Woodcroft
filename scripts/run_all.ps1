<#
.SYNOPSIS
    Runs the API and the storefront together.
#>
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Error "No virtual environment. Run .\scripts\bootstrap.ps1 first."
    exit 1
}

Write-Host "Starting API on http://localhost:8000" -ForegroundColor Cyan
Start-Process -FilePath $venvPython `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000" `
    -WorkingDirectory $backend

Start-Sleep -Seconds 3

Write-Host "Starting storefront on http://localhost:5173" -ForegroundColor Cyan
Push-Location $frontend
npm run dev
Pop-Location
