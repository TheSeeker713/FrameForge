# Build portable FrameForge with PyInstaller
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$py = Join-Path $Root ".venv\Scripts\python.exe"
& $py -m PyInstaller --noconfirm --clean (Join-Path $Root "packaging\frameforge.spec")
$exe = Join-Path $Root "dist\FrameForge\FrameForge.exe"
if (-not (Test-Path $exe)) { throw "Build missing: $exe" }
& $exe --version
Write-Host "BUILD_OK $exe"
