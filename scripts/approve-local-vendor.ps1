param(
    [Parameter(Mandatory = $true)][string]$Email,
    [switch]$Apply
)

$ErrorActionPreference = "Stop"
$emailNormalized = $Email.Trim().ToLowerInvariant()
if ($emailNormalized.Length -gt 254 -or $emailNormalized -notmatch '^[^\s@]+@[^\s@]+$') {
    throw "A valid registration email is required."
}
if (-not $Apply) {
    Write-Host "Plan only: locally approve the pending vendor registration for $emailNormalized. Use -Apply after review."
    return
}

$rootPath = Split-Path -Parent $PSScriptRoot
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
$uri = $null
if (-not [Uri]::TryCreate($databaseUrl, [UriKind]::Absolute, [ref]$uri) -or
    $uri.Scheme -notin @("postgres", "postgresql") -or
    $uri.Host -notin @("localhost", "127.0.0.1", "::1") -or
    $uri.AbsolutePath.TrimStart('/') -ne "sahulat_ai_dev") {
    throw "Only local sahulat_ai_dev may be used for vendor approval."
}
$credentials = $uri.UserInfo.Split(':', 2)
if ($credentials.Length -ne 2) { throw "The local database URL lacks credentials." }
$psqlPath = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
if (-not (Test-Path -LiteralPath $psqlPath -PathType Leaf)) { throw "PostgreSQL 18 psql.exe was not found." }
$env:PGPASSWORD = [Uri]::UnescapeDataString($credentials[1])
try {
    & $psqlPath -X -w -h $uri.Host -p $uri.Port -U ([Uri]::UnescapeDataString($credentials[0])) `
        -d sahulat_ai_dev -v ON_ERROR_STOP=1 -v "registration_email=$emailNormalized" `
        -f (Join-Path $rootPath "backend/database/operations/approve_local_vendor.sql")
    if ($LASTEXITCODE -ne 0) { throw "Local vendor approval failed; no pending registration was activated." }
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
