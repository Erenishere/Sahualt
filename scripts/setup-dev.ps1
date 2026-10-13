# REPO-STRUCTURE-V1 — bootstrap local dependencies (adjust paths for your machine).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "ML pipeline: editable install"
Set-Location (Join-Path $Root "ml-pipeline")
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -e ".[dev,api,api-test]"

Write-Host "Backend: restore"
Set-Location (Join-Path $Root "backend")
dotnet restore

Write-Host "Frontend: install (when package.json present)"
Set-Location (Join-Path $Root "frontend")
if (Test-Path "package.json") { npm install }

Write-Host "Done. Copy .env.example to .env and configure Postgres."
