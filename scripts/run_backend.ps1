$env:PYTHONUTF8 = "1"
$root = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $root "backend")
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000
Pop-Location
