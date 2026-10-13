param([switch]$Apply)

$ErrorActionPreference = "Stop"
$rootPath = Split-Path -Parent $PSScriptRoot
$projectPath = Join-Path $rootPath "backend/tools/SahulatAI.LocalBootstrap/SahulatAI.LocalBootstrap.csproj"
if (-not $Apply) {
    & dotnet run --project $projectPath
    if ($LASTEXITCODE -ne 0) { throw "Local bootstrap plan failed." }
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
try {
    & dotnet run --project $projectPath -- --apply
    if ($LASTEXITCODE -ne 0) { throw "Local bootstrap failed." }
}
finally {
    Remove-Item Env:SAHULAT_ADMIN_DATABASE_URL -ErrorAction SilentlyContinue
}
