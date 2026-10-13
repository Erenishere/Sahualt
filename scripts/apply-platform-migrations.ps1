param(
    [switch]$Apply,
    [switch]$Local,
    [string]$DatabaseName = "sahulat_ai_dev",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 5432,
    [string]$AdminUser = "postgres"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Migrations = @(
    @{ Id = "20260910_001_catalog_core_v1"; RelativePath = "ml-pipeline/database/migrations/20260910_001_catalog_core_v1.sql"; ContainerPath = "/opt/sahulat/migrations/20260910_001_catalog_core_v1.sql" },
    @{ Id = "20260926_002_search_lexical_v1"; RelativePath = "ml-pipeline/database/migrations/20260926_002_search_lexical_v1.sql"; ContainerPath = "/opt/sahulat/migrations/20260926_002_search_lexical_v1.sql" },
    @{ Id = "20260926_003_text_dense_prototype_v1"; RelativePath = "ml-pipeline/database/migrations/20260926_003_text_dense_prototype_v1.sql"; ContainerPath = "/opt/sahulat/migrations/20260926_003_text_dense_prototype_v1.sql" },
    @{ Id = "20261011_004_backend_business_baseline_v1"; RelativePath = "backend/database/migrations/20261011_004_backend_business_baseline_v1.sql"; ContainerPath = "/opt/sahulat/backend-migrations/20261011_004_backend_business_baseline_v1.sql" },
    @{ Id = "20261011_005_commerce_foundation_v1"; RelativePath = "backend/database/migrations/20261011_005_commerce_foundation_v1.sql"; ContainerPath = "/opt/sahulat/backend-migrations/20261011_005_commerce_foundation_v1.sql" }
)

function Get-NormalizedSha256([string]$Path) {
    $sql = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    $normalized = $sql.Replace("`r`n", "`n").Replace("`r", "`n")
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($normalized)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return [System.BitConverter]::ToString($sha.ComputeHash($bytes)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

$plan = foreach ($migration in $Migrations) {
    $path = Join-Path $Root $migration.RelativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Migration file is missing: $path"
    }
    [pscustomobject]@{
        Id = $migration.Id
        RelativePath = $migration.RelativePath
        ContainerPath = $migration.ContainerPath
        Checksum = Get-NormalizedSha256 $path
    }
}

if (-not $Apply) {
    $plan | Format-Table Id, Checksum -AutoSize
    Write-Host "Plan only. Re-run with -Apply for Compose, or -Local -Apply for the local PostgreSQL service."
    return
}

if ($Local -and $HostName -notin @("localhost", "127.0.0.1", "::1")) {
    throw "-Local accepts only a loopback PostgreSQL host."
}

if ($Local -and ($DatabaseName -notmatch '^[a-z][a-z0-9_]{0,62}$' -or
    $DatabaseName -in @("postgres", "template0", "template1"))) {
    throw "-Local requires a non-system database name containing only lowercase letters, digits, and underscores."
}

if ($Local) {
    $psqlCommand = Get-Command psql.exe -ErrorAction SilentlyContinue
    $psqlPath = if ($psqlCommand) { $psqlCommand.Source } else { "C:\Program Files\PostgreSQL\18\bin\psql.exe" }
    if (-not (Test-Path -LiteralPath $psqlPath -PathType Leaf)) {
        throw "PostgreSQL psql.exe was not found."
    }
    $psqlAdmin = @("-X", "-w", "-h", $HostName, "-p", [string]$Port, "-U", $AdminUser, "-d", "postgres")
    $exists = & $psqlPath @psqlAdmin -At -c "SELECT 1 FROM pg_database WHERE datname = '$DatabaseName'"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect local PostgreSQL databases. Configure private authentication first."
    }
    if (-not $exists) {
        Write-Host "Creating local database $DatabaseName"
        & $psqlPath @psqlAdmin -v ON_ERROR_STOP=1 -c "CREATE DATABASE `"$DatabaseName`""
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create local database $DatabaseName."
        }
    }
    $psqlTarget = @("-X", "-w", "-h", $HostName, "-p", [string]$Port, "-U", $AdminUser, "-d", $DatabaseName)
    $platformCheck = & $psqlPath @psqlTarget -At -c "SELECT current_setting('server_version_num')::int / 10000 = 18 AND uuid_extract_version(uuidv7()) = 7 AND EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector')"
    if ($LASTEXITCODE -ne 0 -or $platformCheck.Trim() -ne "t") {
        throw "Expected authenticated PostgreSQL 18 with uuidv7() and pgvector available."
    }
    foreach ($migration in $plan) {
        Write-Host "Applying or verifying $($migration.Id) on local database $DatabaseName"
        $path = Join-Path $Root $migration.RelativePath
        & $psqlPath @psqlTarget -v ON_ERROR_STOP=1 `
            -v "migration_id=$($migration.Id)" `
            -v "migration_checksum=$($migration.Checksum)" `
            -f $path
        if ($LASTEXITCODE -ne 0) {
            throw "Migration failed or checksum mismatch: $($migration.Id)"
        }
    }
    Write-Host "Platform migrations 001 through 005 are current on local database $DatabaseName."
    return
}

Push-Location $Root
try {
    $databaseName = (& docker compose exec -T postgres printenv POSTGRES_DB)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($databaseName)) {
        throw "PostgreSQL Compose service is not running or POSTGRES_DB is unavailable."
    }
    $databaseName = $databaseName.Trim()

    $platformCheck = (& docker compose exec -T postgres psql -X -w -At -U postgres -d $databaseName -c "SELECT current_setting('server_version_num')::int / 10000 = 18 AND uuid_extract_version(uuidv7()) = 7 AND EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector')")
    if ($LASTEXITCODE -ne 0 -or $platformCheck.Trim() -ne "t") {
        throw "Expected PostgreSQL 18 with uuidv7() and the pgvector extension available."
    }

    foreach ($migration in $plan) {
        Write-Host "Applying or verifying $($migration.Id)"
        & docker compose exec -T postgres psql -X -w -U postgres -d $databaseName `
            -v ON_ERROR_STOP=1 `
            -v "migration_id=$($migration.Id)" `
            -v "migration_checksum=$($migration.Checksum)" `
            -f $migration.ContainerPath
        if ($LASTEXITCODE -ne 0) {
            throw "Migration failed or checksum mismatch: $($migration.Id)"
        }
    }
    Write-Host "Platform migrations 001 through 005 are current on $databaseName."
}
finally {
    Pop-Location
}
