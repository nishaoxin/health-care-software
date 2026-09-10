param(
    [switch]$VerifyOnly,
    [string]$IndexUrl = 'https://pypi.org/simple'
)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$taskPython = Join-Path $taskRoot '.venv-landmarks\Scripts\python.exe'
$taskBasePython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskModelDirectory = Join-Path $taskRoot 'assets\models'
$taskManifest = Get-Content -LiteralPath (Join-Path $taskModelDirectory 'landmarks-manifest.json') -Raw | ConvertFrom-Json
$taskOldMpl = $env:MPLCONFIGDIR
$taskCache = Join-Path $taskRoot '.runtime\landmarks-mpl'
New-Item -ItemType Directory -Path $taskCache -Force | Out-Null
$env:MPLCONFIGDIR = $taskCache
Push-Location -LiteralPath $taskRoot
try {
    if (-not (Test-Path -LiteralPath $taskPython)) {
        if ($VerifyOnly) { throw 'Optional landmark environment is missing.' }
        if (-not (Test-Path -LiteralPath $taskBasePython)) { throw 'Prepare the main project environment first.' }
        & $taskBasePython -m venv (Join-Path $taskRoot '.venv-landmarks')
        if ($LASTEXITCODE -ne 0) { throw 'Cannot create isolated landmark environment.' }
    }
    if (-not $VerifyOnly) {
        $taskWheels = Join-Path $taskRoot '.runtime\landmark-wheels'
        New-Item -ItemType Directory -Path $taskWheels -Force | Out-Null
        & $taskPython -m pip download --disable-pip-version-check --only-binary=:all: --no-deps --index-url $IndexUrl --dest $taskWheels -r (Join-Path $taskRoot 'requirements.landmarks.lock.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Optional dependency download failed.' }
        & $taskBasePython (Join-Path $PSScriptRoot 'verify_wheels.py') --wheel-dir $taskWheels --output (Join-Path $taskRoot '.runtime\landmark-dependency-manifest.json') --transport $IndexUrl
        if ($LASTEXITCODE -ne 0) { throw 'Optional dependency official SHA256 verification failed.' }
        & $taskPython -m pip install --disable-pip-version-check --only-binary=:all: --no-index --find-links $taskWheels -r (Join-Path $taskRoot 'requirements.landmarks.lock.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Optional dependencies could not be installed; main environment is unchanged.' }
    }
    & $taskPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Optional dependency check failed.' }
    & $taskPython -c "import mediapipe; assert mediapipe.__version__ == '1.0.1', 'Unexpected MediaPipe version'"
    if ($LASTEXITCODE -ne 0) { throw 'Optional runtime version is not the verified version.' }
    foreach ($taskBackend in @('mediapipe_pose', 'mediapipe_hands')) {
        $taskEntry = $taskManifest.models.$taskBackend
        if ($taskEntry.filename -notin @('pose_landmarker_full.task', 'hand_landmarker.task')) { throw 'Unexpected model filename.' }
        $taskDestination = [IO.Path]::GetFullPath((Join-Path $taskModelDirectory $taskEntry.filename))
        if (-not $taskDestination.StartsWith($taskModelDirectory + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Model path escapes project model directory.' }
        if (-not (Test-Path -LiteralPath $taskDestination)) {
            if ($VerifyOnly) { throw "Missing model: $($taskEntry.filename)" }
            $taskUri = [Uri]$taskEntry.url
            if ($taskUri.Scheme -ne 'https' -or $taskUri.Host -ne 'storage.googleapis.com' -or -not $taskUri.AbsolutePath.StartsWith('/mediapipe-models/')) { throw 'Non-official model URL rejected.' }
            $taskDownload = [IO.Path]::GetFullPath((Join-Path $taskModelDirectory ($taskEntry.filename + '.' + [Guid]::NewGuid().ToString('N') + '.download')))
            if (-not $taskDownload.StartsWith($taskModelDirectory + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Download path escapes project model directory.' }
            Invoke-WebRequest -Uri $taskEntry.url -OutFile $taskDownload -UseBasicParsing -TimeoutSec 180
            if ((Get-FileHash -LiteralPath $taskDownload -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskEntry.sha256) { throw "Downloaded file hash mismatch; retained for inspection: $taskDownload" }
            # Exact source/destination are validated above; never replace an existing model.
            if (Test-Path -LiteralPath $taskDestination) { throw 'Destination appeared during download; nothing overwritten.' }
            Move-Item -LiteralPath $taskDownload -Destination $taskDestination
        }
        if ((Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskEntry.sha256) { throw "Existing model hash mismatch; not overwritten: $taskDestination" }
        Write-Output "Verified local model: $($taskEntry.filename)"
    }
    Write-Output 'Optional landmarks are ready. The application never downloads models at startup.'
} finally {
    [Environment]::SetEnvironmentVariable('MPLCONFIGDIR', $taskOldMpl, 'Process')
    Pop-Location
}
