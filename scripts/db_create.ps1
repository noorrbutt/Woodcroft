<#
.SYNOPSIS
    Creates the Woodcroft role, databases and extensions. Idempotent - safe to re-run.
.NOTES
    PowerShell 5.1 compatible: no '&&', no ternary, no '??'.
#>
[CmdletBinding()]
param(
    [string]$SuperUser     = "postgres",
    [string]$SuperPassword = "postgres",
    [string]$DbHost        = "localhost",
    [int]   $Port          = 5432,
    [string]$AppUser       = "woodcroft",
    [string]$AppPassword   = "woodcroft",
    [string]$DevDb         = "woodcroft_dev",
    [string]$TestDb        = "woodcroft_test"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# psql is not on PATH in a default Windows install - resolve it explicitly.
$psql = $null
$candidates = @(
    "C:\Program Files\PostgreSQL\18\bin\psql.exe",
    "C:\Program Files\PostgreSQL\17\bin\psql.exe",
    "C:\Program Files\PostgreSQL\16\bin\psql.exe"
)
foreach ($c in $candidates) {
    if (Test-Path $c) { $psql = $c; break }
}
if (-not $psql) {
    $onPath = Get-Command psql -ErrorAction SilentlyContinue
    if ($onPath) { $psql = $onPath.Source }
}
if (-not $psql) {
    Write-Error "psql.exe not found. Install PostgreSQL 18 or add its bin directory to PATH."
    exit 1
}
Write-Host "Using psql: $psql" -ForegroundColor DarkGray

$env:PGPASSWORD = $SuperPassword

function Invoke-Sql {
    param([string]$Database, [string]$Sql)
    $out = & $psql -U $SuperUser -h $DbHost -p $Port -d $Database -v ON_ERROR_STOP=1 -tAc $Sql 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "SQL failed against '$Database': $out"
        exit 1
    }
    return $out
}

Write-Host "`n== Woodcroft database provisioning ==" -ForegroundColor Cyan

# --- Role -------------------------------------------------------------------
$roleExists = Invoke-Sql -Database "postgres" -Sql "SELECT 1 FROM pg_roles WHERE rolname = '$AppUser';"
if ($roleExists -eq "1") {
    Write-Host "  role '$AppUser' already exists" -ForegroundColor DarkGray
    Invoke-Sql -Database "postgres" -Sql "ALTER ROLE $AppUser WITH LOGIN PASSWORD '$AppPassword' CREATEDB;" | Out-Null
} else {
    Invoke-Sql -Database "postgres" -Sql "CREATE ROLE $AppUser WITH LOGIN PASSWORD '$AppPassword' CREATEDB;" | Out-Null
    Write-Host "  created role '$AppUser'" -ForegroundColor Green
}

# --- Databases --------------------------------------------------------------
foreach ($db in @($DevDb, $TestDb)) {
    $dbExists = Invoke-Sql -Database "postgres" -Sql "SELECT 1 FROM pg_database WHERE datname = '$db';"
    if ($dbExists -eq "1") {
        Write-Host "  database '$db' already exists" -ForegroundColor DarkGray
    } else {
        # CREATE DATABASE cannot run inside a transaction block, so it goes on its own.
        Invoke-Sql -Database "postgres" -Sql "CREATE DATABASE $db OWNER $AppUser ENCODING 'UTF8';"  | Out-Null
        Write-Host "  created database '$db'" -ForegroundColor Green
    }

    # --- Extensions ---------------------------------------------------------
    # NOTE: uuidv7() is a native PostgreSQL 18 builtin - no extension required.
    $exts = @("pg_trgm", "citext", "unaccent", "btree_gin")
    foreach ($ext in $exts) {
        Invoke-Sql -Database $db -Sql "CREATE EXTENSION IF NOT EXISTS $ext;" | Out-Null
    }
    Invoke-Sql -Database $db -Sql "GRANT ALL ON SCHEMA public TO $AppUser;" | Out-Null
    Write-Host "    extensions ready: $($exts -join ', ')" -ForegroundColor DarkGray
}

# --- Verify pg18 uuidv7() ---------------------------------------------------
$uuidCheck = Invoke-Sql -Database $DevDb -Sql "SELECT uuidv7() IS NOT NULL;"
if ($uuidCheck -ne "t") {
    Write-Error "uuidv7() unavailable - PostgreSQL 18 or newer is required."
    exit 1
}
Write-Host "  uuidv7() verified" -ForegroundColor Green

Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
Write-Host "`nDone. DATABASE_URL=postgresql+psycopg://${AppUser}:${AppPassword}@${DbHost}:${Port}/${DevDb}`n" -ForegroundColor Cyan
