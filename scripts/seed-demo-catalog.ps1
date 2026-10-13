param(
    [Parameter(Mandatory = $true)]
    [string]$ArchivePath,
    [switch]$Apply,
    [switch]$Purge,
    [switch]$ClientFacing
)

$ErrorActionPreference = "Stop"
$rootPath = Split-Path -Parent $PSScriptRoot
$projectPath = Join-Path $rootPath "backend/tools/SahulatAI.DemoCatalogSeeder/SahulatAI.DemoCatalogSeeder.csproj"
$resolvedArchive = (Resolve-Path -LiteralPath $ArchivePath -ErrorAction Stop).Path

if ($Apply -and $Purge) {
    throw "Choose either -Apply or -Purge."
}
if ($ClientFacing -and (-not $Apply -or $Purge)) {
    throw "-ClientFacing requires -Apply and cannot be combined with -Purge."
}

$arguments = @("--archive", $resolvedArchive)
if (-not $Apply -and -not $Purge) {
    & dotnet run --project $projectPath -- @arguments
    if ($LASTEXITCODE -ne 0) { throw "Demo catalog plan failed." }
    return
}

$envPath = Join-Path $rootPath "ml-pipeline/.env"
if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
    throw "The local ml-pipeline/.env database URL is required."
}

$databaseUrl = $null
foreach ($line in Get-Content -LiteralPath $envPath) {
    if ($line -match '^\s*DATABASE_URL\s*=\s*(.*)\s*$') {
        $databaseUrl = $Matches[1].Trim().Trim('"').Trim("'")
    }
}
if (-not $databaseUrl) { throw "DATABASE_URL is missing from ml-pipeline/.env." }

$env:SAHULAT_ADMIN_DATABASE_URL = $databaseUrl
$env:SAHULAT_ENABLE_DEMO_CATALOG = "1"
$env:SAHULAT_DEMO_MEDIA_ROOT = Join-Path $rootPath "backend/.local-media"
try {
    $arguments += if ($Purge) { "--purge" } else { "--apply" }
    if ($ClientFacing) { $arguments += "--client-facing" }
    & dotnet run --project $projectPath -- @arguments
    if ($LASTEXITCODE -ne 0) { throw "Demo catalog operation failed." }
}
finally {
    Remove-Item Env:SAHULAT_ADMIN_DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:SAHULAT_ENABLE_DEMO_CATALOG -ErrorAction SilentlyContinue
    Remove-Item Env:SAHULAT_DEMO_MEDIA_ROOT -ErrorAction SilentlyContinue
}
