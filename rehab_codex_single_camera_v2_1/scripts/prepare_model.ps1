$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskModelDir = Join-Path $taskRoot 'assets\models'
$taskManifest = Get-Content -LiteralPath (Join-Path $taskModelDir 'manifest.json') -Raw -Encoding utf8 | ConvertFrom-Json
$taskModel = Join-Path $taskModelDir $taskManifest.name
if (Test-Path -LiteralPath $taskModel) {
    $taskExistingHash = (Get-FileHash -LiteralPath $taskModel -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($taskExistingHash -eq $taskManifest.sha256) {
        Write-Output 'Trusted local weights already match the recorded SHA256.'
        return
    }
    throw 'An existing model does not match the trusted manifest. It was preserved; inspect it before preparing a new model.'
}
$taskPartial = Join-Path $taskModelDir 'yolo11n-pose.download'
Invoke-WebRequest -Uri $taskManifest.source -OutFile $taskPartial
$taskActualHash = (Get-FileHash -LiteralPath $taskPartial -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskActualHash -ne $taskManifest.sha256) { throw 'Downloaded model hash does not match the frozen manifest; it was not loaded.' }
Rename-Item -LiteralPath $taskPartial -NewName $taskManifest.name
Write-Output 'Official YOLO11n-pose weights verified. Application startup never downloads models.'
