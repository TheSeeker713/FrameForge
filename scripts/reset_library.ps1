# Reset Library onboarding so first-run can be retested.
# Does NOT delete media files.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}
& $py -m frameforge --reset-library
exit $LASTEXITCODE
