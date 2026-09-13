<#
.SYNOPSIS
    Reseeds the database. Use -NoImages while iterating on data.
#>
param([switch]$NoImages, [switch]$Append, [int]$Orders = 260)

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$root = Split-Path -Parent $PSScriptRoot

$seedArgs = @("-m", "app.seed", "--orders", $Orders)
if ($Append) { $seedArgs += "--append" } else { $seedArgs += "--fresh" }
if ($NoImages) { $seedArgs += "--no-images" }

Push-Location (Join-Path $root "backend")
& ".\.venv\Scripts\python.exe" @seedArgs
Pop-Location
