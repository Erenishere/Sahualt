$ErrorActionPreference = "Stop"
$rootPath = Split-Path -Parent $PSScriptRoot
$secretPath = Join-Path $rootPath "backend/.local-runtime-secrets.json"
if (-not (Test-Path -LiteralPath $secretPath -PathType Leaf)) {
    throw "Run the local bootstrap before starting the vendor API."
}
$settings = Get-Content -LiteralPath $secretPath -Raw | ConvertFrom-Json
if ($settings.databaseName -ne "sahulat_ai_dev" -or
    $settings.host -notin @("localhost", "127.0.0.1", "::1") -or
    $settings.port -ne 5432 -or
    [string]::IsNullOrWhiteSpace($settings.assistant) -or
    [string]::IsNullOrWhiteSpace($settings.identity) -or
    [string]::IsNullOrWhiteSpace($settings.registration)) {
    throw "Unexpected local runtime target. Run .\scripts\bootstrap-local-vendor.ps1 -Apply if secrets are missing."
}

$base = "Host=$($settings.host);Port=$($settings.port);Database=sahulat_ai_dev"
$env:ConnectionStrings__AssistantReader = "$base;Username=sahulat_api_assistant;Password=$($settings.assistant)"
$env:ConnectionStrings__IdentityReader = "$base;Username=sahulat_api_identity;Password=$($settings.identity)"
$env:ConnectionStrings__RegistrationWriter = "$base;Username=sahulat_api_registration;Password=$($settings.registration)"
if (-not [string]::IsNullOrWhiteSpace($settings.catalogWriter)) {
    $env:ConnectionStrings__CatalogWriter = "$base;Username=sahulat_api_catalog_writer;Password=$($settings.catalogWriter)"
}
if (-not [string]::IsNullOrWhiteSpace($settings.commerce)) {
    $env:ConnectionStrings__CommerceWriter = "$base;Username=sahulat_api_commerce;Password=$($settings.commerce)"
}
if (-not [string]::IsNullOrWhiteSpace($settings.admin)) {
    $env:ConnectionStrings__AdminWriter = "$base;Username=sahulat_api_admin;Password=$($settings.admin)"
}
$env:Frontend__Origin = "http://localhost:3000"
$env:ASPNETCORE_ENVIRONMENT = "Development"
$env:Media__Provider = "Local"
$env:Media__Local__Root = Join-Path $rootPath "backend/.local-media"
try {
    & dotnet run --project (Join-Path $rootPath "backend/src/SahulatAI.Api/SahulatAI.Api.csproj") --no-launch-profile --urls http://localhost:5272
    if ($LASTEXITCODE -ne 0) { throw "Vendor API exited with an error." }
}
finally {
    Remove-Item Env:ConnectionStrings__AssistantReader -ErrorAction SilentlyContinue
    Remove-Item Env:ConnectionStrings__IdentityReader -ErrorAction SilentlyContinue
    Remove-Item Env:ConnectionStrings__CatalogWriter -ErrorAction SilentlyContinue
    Remove-Item Env:ConnectionStrings__RegistrationWriter -ErrorAction SilentlyContinue
    Remove-Item Env:ConnectionStrings__CommerceWriter -ErrorAction SilentlyContinue
    Remove-Item Env:ConnectionStrings__AdminWriter -ErrorAction SilentlyContinue
    Remove-Item Env:Frontend__Origin -ErrorAction SilentlyContinue
    Remove-Item Env:ASPNETCORE_ENVIRONMENT -ErrorAction SilentlyContinue
    Remove-Item Env:Media__Provider -ErrorAction SilentlyContinue
    Remove-Item Env:Media__Local__Root -ErrorAction SilentlyContinue
}
