$root = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $root "frontend")
npm run dev
Pop-Location
