# Clear the download queue for a first-run test.
# Does NOT delete videos, cookies, or the FrameForge home.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}
& $py -m frameforge --reset-queue
exit $LASTEXITCODE
