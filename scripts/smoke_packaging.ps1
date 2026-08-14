# Smoke the one-folder PyInstaller build (does not start a lasting GUI).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $Root "dist\FrameForge\FrameForge.exe"
if (-not (Test-Path $exe)) { throw "Missing $exe. Run scripts\build_portable.ps1 first." }
$ver = & $exe --version
Write-Host "PACKAGING_VERSION $ver"
if ($ver -notmatch "frameforge ") { throw "Unexpected --version output: $ver" }
$client = Join-Path $Root "dist\FrameForge\_internal\flet-client\flet.exe"
if (-not (Test-Path $client)) {
    Write-Host "WARN missing bundled flet.exe at $client (first --gui may download the client)"
} else {
    Write-Host "FLET_CLIENT $client"
}
Write-Host "SMOKE_OK $exe"
