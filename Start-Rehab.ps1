$ErrorActionPreference = 'Stop'
$taskRoot = Join-Path $PSScriptRoot 'rehab_codex_single_camera_v2_1'
$taskPython = Join-Path $taskRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Project environment is missing. Run Setup-Rehab.ps1 first; add -IncludeLandmarks for wrist, ankle and finger tasks.'
}
$taskRuntimeDir = Join-Path $taskRoot '.runtime'
New-Item -ItemType Directory -Path $taskRuntimeDir -Force | Out-Null
Start-Process -FilePath $taskPython -ArgumentList @('-m','app.main') -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRuntimeDir 'app-stdout.log') -RedirectStandardError (Join-Path $taskRuntimeDir 'app-stderr.log')
