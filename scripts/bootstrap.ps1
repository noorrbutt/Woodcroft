<#
.SYNOPSIS
    Takes a fresh clone to a running, seeded Woodcroft.
.DESCRIPTION
    Creates the database, builds the Python venv, installs both dependency
    sets, applies migrations and seeds. Safe to re-run.
.NOTES
    PowerShell 5.1 compatible: no '&&', no ternary, no '??'.
#>
[CmdletBinding()]
param(
    [switch]$NoImages,
    [int]$Orders = 260
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

function Step([string]$message) {
    Write-Host ""
    Write-Host "== $message" -ForegroundColor Cyan
}

Step "Database"
& (Join-Path $PSScriptRoot "db_create.ps1")

Step "Python environment"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Push-Location $backend
    python -m venv .venv
    Pop-Location
    Write-Host "  created .venv" -ForegroundColor Green
} else {
    Write-Host "  .venv already exists" -ForegroundColor DarkGray
}

Step "Backend dependencies"
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -r (Join-Path $backend "requirements-dev.txt")
if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed"; exit 1 }
Write-Host "  installed" -ForegroundColor Green

Step "Environment file"
$envFile = Join-Path $backend ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $root ".env.example") $envFile
    Write-Host "  created backend\.env from .env.example" -ForegroundColor Green
} else {
    Write-Host "  backend\.env already exists" -ForegroundColor DarkGray
}

Step "Migrations"
Push-Location $backend
& $venvPython -m alembic upgrade head
Pop-Location

Step "Seed data"
$seedArgs = @("-m", "app.seed", "--fresh", "--orders", $Orders)
if ($NoImages) { $seedArgs += "--no-images" }
Push-Location $backend
& $venvPython @seedArgs
Pop-Location

Step "Frontend dependencies"
Push-Location $frontend
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    npm install --no-fund --no-audit
} else {
    Write-Host "  node_modules already present" -ForegroundColor DarkGray
}
Pop-Location

Write-Host ""
Write-Host "Ready. Start it with:" -ForegroundColor Cyan
Write-Host "  .\scripts\run_all.ps1"
Write-Host ""
