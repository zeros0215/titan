param(
    [string]$TaskName = "TITAN-Daily",
    [string]$RunAt = "18:30"
)

$runnerPath = Join-Path $PSScriptRoot "run_daily.ps1"
if (-not (Test-Path -LiteralPath $runnerPath)) {
    throw "Daily runner not found: $runnerPath"
}

$parsedTime = [datetime]::ParseExact(
    $RunAt,
    "HH:mm",
    [System.Globalization.CultureInfo]::InvariantCulture
)
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`""
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
    -Description "TITAN daily selection and matured validation" `
    -Force

Write-Host "Registered scheduled task '$TaskName' at $RunAt on weekdays."
