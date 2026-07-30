param(
    [string]$OperationDate = (Get-Date -Format "yyyy-MM-dd")
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExecutable = if ($env:TITAN_PYTHON) {
    $env:TITAN_PYTHON
} else {
    "python"
}

Push-Location -LiteralPath $projectRoot
try {
    & $pythonExecutable -m app.main daily --date $OperationDate
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
