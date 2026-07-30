param(
    [string]$PythonExe = $env:TITAN_PYTHON
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $PythonExe) {
    $PythonExe = "python"
}
$today = Get-Date -Format "yyyy-MM-dd"
$now = Get-Date
if ($now.DayOfWeek -in @("Saturday", "Sunday")) {
    Write-Output "KIS V1.1 pilot skipped: weekend."
    exit 0
}
if ($now.TimeOfDay -lt [TimeSpan]::FromHours(15.6667)) {
    throw "KIS V1.1 pilot must run after 15:40 KST."
}

Push-Location $projectRoot
try {
    & $PythonExe -m app.main kis-pilot `
        --date $today `
        --top-n 5 `
        --active-data output/release/backtest_data.json `
        --output-dir output/kis_v1_1
    $pilotExit = $LASTEXITCODE

    & $PythonExe -m app.main kis-pilot-report `
        --output-dir output/kis_v1_1 `
        --required-days 5
    $reportExit = $LASTEXITCODE

    & $PythonExe -m tools.build_kis_dashboard
    $dashboardExit = $LASTEXITCODE

    if ($pilotExit -notin @(0, 3)) {
        exit $pilotExit
    }
    if ($reportExit -notin @(0, 3)) {
        exit $reportExit
    }
    if ($dashboardExit -ne 0) {
        exit $dashboardExit
    }
    exit 0
}
finally {
    Pop-Location
}
