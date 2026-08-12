# Download Real-ESRGAN ONNX (or ensure smoke model exists)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Missing .venv. Run scripts/bootstrap_venv.ps1 first." }
& $py (Join-Path $Root "scripts\download_models.py")
