param(
    [switch]$IncludeLandmarks,
    [string]$IndexUrl = 'https://pypi.org/simple'
)
$ErrorActionPreference = 'Stop'
$taskAppRoot = Join-Path $PSScriptRoot 'rehab_codex_single_camera_v2_1'
& (Join-Path $taskAppRoot 'scripts\setup.ps1') -IndexUrl $IndexUrl -PrepareModel
if ($IncludeLandmarks) {
    & (Join-Path $taskAppRoot 'scripts\setup_landmarks.ps1') -IndexUrl $IndexUrl
}
Write-Output 'Setup completed. Use the workspace launcher to open Home Rehab.'
