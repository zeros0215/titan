$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
& python -m tools.daily_kis_morning_collection
exit $LASTEXITCODE
