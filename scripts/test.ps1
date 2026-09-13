$env:PYTHONUTF8 = "1"
$env:APP_ENV = "test"
$env:ENABLE_BACKGROUND_WORKER = "false"
$root = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $root "backend")
& ".\.venv\Scripts\python.exe" -m pytest @args
Pop-Location
