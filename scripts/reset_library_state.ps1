# Reset Library onboarding so first-run can be retested.
# Does NOT delete media files. Alias of reset_library.ps1.
$ErrorActionPreference = "Stop"
& "$PSScriptRoot\reset_library.ps1"
exit $LASTEXITCODE
