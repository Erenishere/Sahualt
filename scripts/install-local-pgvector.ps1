param(
    [switch]$Install,
    [string]$PostgresRoot = "C:\Program Files\PostgreSQL\18"
)

$ErrorActionPreference = "Stop"

$Version = "0.8.6"
$ArchiveName = "vector.v0.8.6-pg18.zip"
$DownloadUrl = "https://github.com/andreiramani/pgvector_pgsql_windows/releases/download/0.8.6_18/$ArchiveName"
$ExpectedSha256 = "bda17eb97d9e687e3da701adbf4b65a342943b3e0cdc81935ccf0b9833a1ed62"

if (-not $Install) {
    Write-Host "Plan only: install pgvector $Version for PostgreSQL 18 into $PostgresRoot."
    Write-Host "Re-run from an elevated PowerShell session with -Install."
    exit 0
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Administrator privileges are required to install files under $PostgresRoot."
}

$pgConfig = Join-Path $PostgresRoot "bin\pg_config.exe"
if (-not (Test-Path -LiteralPath $pgConfig)) {
    throw "PostgreSQL 18 was not found at $PostgresRoot."
}
$postgresVersion = & $pgConfig --version
if ($LASTEXITCODE -ne 0 -or $postgresVersion -notmatch '^PostgreSQL 18\.') {
    throw "Expected PostgreSQL 18, found: $postgresVersion"
}

$workRoot = Join-Path $env:TEMP "sahulat-pgvector-$Version-pg18"
$archive = Join-Path $workRoot $ArchiveName
$expanded = Join-Path $workRoot "expanded"
New-Item -ItemType Directory -Force -Path $workRoot | Out-Null

Invoke-WebRequest -Headers @{ "User-Agent" = "SahulatAI-Setup" } -Uri $DownloadUrl -OutFile $archive
$actualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
if ($actualSha256 -ne $ExpectedSha256) {
    throw "pgvector archive digest mismatch. Expected $ExpectedSha256, received $actualSha256."
}

if (Test-Path -LiteralPath $expanded) {
    $resolvedExpanded = (Resolve-Path -LiteralPath $expanded).Path
    $resolvedWorkRoot = (Resolve-Path -LiteralPath $workRoot).Path
    if (-not $resolvedExpanded.StartsWith($resolvedWorkRoot + "\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clear an unexpected extraction path: $resolvedExpanded"
    }
    Remove-Item -LiteralPath $resolvedExpanded -Recurse -Force
}
Expand-Archive -LiteralPath $archive -DestinationPath $expanded

$sourceDll = Join-Path $expanded "lib\vector.dll"
$sourceControl = Join-Path $expanded "share\extension\vector.control"
$sourceInstallSql = Join-Path $expanded "share\extension\vector--$Version.sql"
foreach ($requiredFile in @($sourceDll, $sourceControl, $sourceInstallSql)) {
    if (-not (Test-Path -LiteralPath $requiredFile)) {
        throw "The verified archive is missing $requiredFile."
    }
}

$targetLib = Join-Path $PostgresRoot "lib"
$targetShare = Join-Path $PostgresRoot "share\extension"
$targetInclude = Join-Path $PostgresRoot "include\server\extension"
Copy-Item -LiteralPath $sourceDll -Destination (Join-Path $targetLib "vector.dll") -Force
Copy-Item -Path (Join-Path $expanded "share\extension\vector*") -Destination $targetShare -Force
Copy-Item -LiteralPath (Join-Path $expanded "include\server\extension\vector") -Destination $targetInclude -Recurse -Force

Get-ChildItem -Path (Join-Path $targetShare "vector*") -File | Unblock-File
Unblock-File -LiteralPath (Join-Path $targetLib "vector.dll")

$installedControl = Join-Path $targetShare "vector.control"
$installedDll = Join-Path $targetLib "vector.dll"
if (-not (Test-Path -LiteralPath $installedControl) -or -not (Test-Path -LiteralPath $installedDll)) {
    throw "pgvector installation did not produce the expected PostgreSQL files."
}

Write-Host "Installed pgvector $Version for $postgresVersion."
Write-Host "Archive SHA256: $actualSha256"
