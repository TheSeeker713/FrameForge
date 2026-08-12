# Bootstrap FrameForge Python 3.12 venv and install deps.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Creating .venv with Python 3.12..."
py -3.12 -m venv .venv

$py = Join-Path $Root ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -e ".[dev]"

Write-Host "Bootstrap complete:"
& $py --version
& $py -m pip show yt-dlp onnxruntime-directml customtkinter | Select-String -Pattern "^(Name|Version)"
