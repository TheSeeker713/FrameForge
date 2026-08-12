# Final verification wrapper
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$py = Join-Path $Root ".venv\Scripts\python.exe"
& $py -m frameforge --version
& $py -m frameforge --check-env
& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$exe = Join-Path $Root "dist\FrameForge\FrameForge.exe"
if (Test-Path $exe) {
  & $exe --version
} else {
  Write-Host "WARNING: portable exe not built yet"
}
Write-Host "PHASE5_VERIFY_OK"
