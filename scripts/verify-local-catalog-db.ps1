param(
    [switch]$Apply,
    [string]$DatabaseName = "sahulat_ai_dev",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 5432,
    [string]$AdminUser = "postgres"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$roleFiles = @(
    "backend/database/provisioning/vendor_assistant_reader.sql",
    "backend/database/provisioning/vendor_identity_reader.sql",
    "backend/database/provisioning/vendor_catalog_writer.sql",
    "backend/database/provisioning/vendor_registration_writer.sql",
    "backend/database/provisioning/commerce_runtime.sql",
    "backend/database/provisioning/admin_runtime.sql"
)
$smokeFile = Join-Path $root "backend/database/tests/catalog_draft_writer.sql"
$registrationSmokeFile = Join-Path $root "backend/database/tests/vendor_registration_writer.sql"
$commerceSmokeFile = Join-Path $root "backend/database/tests/commerce_runtime.sql"
$adminSmokeFile = Join-Path $root "backend/database/tests/admin_runtime.sql"

if (-not $Apply) {
    Write-Host "Plan only: verify $DatabaseName on local PostgreSQL, apply six capability-role grants, then run rollback-only database smokes."
    return
}
if ($HostName -notin @("localhost", "127.0.0.1", "::1") -or
    $DatabaseName -notmatch '^[a-z][a-z0-9_]{0,62}$' -or
    $DatabaseName -in @("postgres", "template0", "template1")) {
    throw "A local, non-system PostgreSQL database is required."
}

$psqlCommand = Get-Command psql.exe -ErrorAction SilentlyContinue
$psqlPath = if ($psqlCommand) { $psqlCommand.Source } else { "C:\Program Files\PostgreSQL\18\bin\psql.exe" }
if (-not (Test-Path -LiteralPath $psqlPath -PathType Leaf)) {
    throw "PostgreSQL psql.exe was not found."
}
$target = @("-X", "-w", "-h", $HostName, "-p", [string]$Port, "-U", $AdminUser, "-d", $DatabaseName)
$ready = & $psqlPath @target -At -c "SELECT current_setting('server_version_num')::int / 10000 = 18 AND to_regclass('catalog.products') IS NOT NULL"
if ($LASTEXITCODE -ne 0) {
    throw "Could not connect to the local PostgreSQL database for verification."
}
if ($ready.Trim() -ne "t") {
    throw "PostgreSQL 18 catalog migration 001 must be present before role verification."
}

foreach ($roleFile in $roleFiles) {
    $path = Join-Path $root $roleFile
    Write-Host "Applying capability grants: $roleFile"
    & $psqlPath @target -v ON_ERROR_STOP=1 -f $path
    if ($LASTEXITCODE -ne 0) {
        throw "Capability grants failed: $roleFile"
    }
}

Write-Host "Running rollback-only draft writer and reader smoke."
& $psqlPath @target -v ON_ERROR_STOP=1 -f $smokeFile
if ($LASTEXITCODE -ne 0) {
    throw "Catalog database smoke failed."
}

Write-Host "Running rollback-only vendor registration smoke."
& $psqlPath @target -v ON_ERROR_STOP=1 -f $registrationSmokeFile
if ($LASTEXITCODE -ne 0) {
    throw "Vendor registration database smoke failed."
}

Write-Host "Running rollback-only commerce capability smoke."
& $psqlPath @target -v ON_ERROR_STOP=1 -f $commerceSmokeFile
if ($LASTEXITCODE -ne 0) {
    throw "Commerce database smoke failed."
}

Write-Host "Running rollback-only admin capability smoke."
& $psqlPath @target -v ON_ERROR_STOP=1 -f $adminSmokeFile
if ($LASTEXITCODE -ne 0) {
    throw "Admin database smoke failed."
}
