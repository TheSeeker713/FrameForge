# Phase 0 verification wrapper
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Missing .venv" }

& $py -m frameforge --version
& $py -m frameforge --check-env
& $py -m pytest -q tests/test_phase0_foundation.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "PHASE0_VERIFY_OK"
