param(
    [string]$IndexUrl = 'https://pypi.org/simple',
    [switch]$PrepareModel
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    $taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $taskPython)) {
        & py -3.13 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 is required for the verified Windows environment.' }
    }
    & $taskPython -m pip install --disable-pip-version-check --index-url $IndexUrl -r requirements.lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; the system Python environment was not modified.' }
    & $taskPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency consistency check failed.' }
    if ($PrepareModel) { & (Join-Path $PSScriptRoot 'prepare_model.ps1') }
    Write-Output 'Environment prepared. Launch the application from the workspace launcher.'
} finally {
    Pop-Location
}
