$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$env:TMP = Join-Path $Root "ml-pipeline\.pytest_tmp"
$env:TEMP = $env:TMP

Write-Host "=== ML engineering gate ==="
Set-Location (Join-Path $Root "ml-pipeline")
& .\.venv\Scripts\python.exe scripts\engineering_text_prototype_status.py --verify-unit
& .\.venv\Scripts\python.exe scripts\text_eval_coordinator_status.py
& .\.venv\Scripts\python.exe -m pytest -m "not model and not slow and not database"

Write-Host "=== Backend ==="
Set-Location (Join-Path $Root "backend")
dotnet test

Write-Host "=== Frontend ==="
Set-Location (Join-Path $Root "frontend")
if (Test-Path "package.json") { npm run lint; npm run build }

Write-Host "verify-all complete"
