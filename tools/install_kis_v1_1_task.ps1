param(
    [string]$TaskName = "TITAN-KIS-V1.1-Pilot",
    [string]$RunAt = "18:30",
    [string]$PythonExe = ""
)

$runnerPath = Join-Path $PSScriptRoot "run_kis_v1_1.ps1"
if (-not (Test-Path -LiteralPath $runnerPath)) {
    throw "KIS V1.1 runner not found: $runnerPath"
}
if (-not $PythonExe) {
    $PythonExe = (Get-Command python -ErrorAction Stop).Source
}
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}
$parsedTime = [datetime]::ParseExact(
    $RunAt,
    "HH:mm",
    [System.Globalization.CultureInfo]::InvariantCulture
)
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument (
        "-NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`" " +
        "-PythonExe `"$PythonExe`""
    )
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At $parsedTime
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "TITAN V1.1 KIS read-only five-session pilot" `
    -Force

Write-Host "Registered scheduled task '$TaskName' at $RunAt on weekdays."
