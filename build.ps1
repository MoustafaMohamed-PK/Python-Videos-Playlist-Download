# Build the Windows standalone executables natively.
#
#   powershell -ExecutionPolicy Bypass -File build.ps1
#
# Produces dist\windows\media-downloader-cli.exe and
# dist\windows\media-downloader-ui.exe, with FFmpeg bundled in (see
# packaging\media-downloader.spec and app\utils.py:use_bundled_ffmpeg).
#
# The base interpreter defaults to the `py` launcher; set BUILD_PYTHON
# to use a specific one (the GitHub Actions workflow sets it to the
# `python` that actions/setup-python put on PATH).

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

# gyan.dev's "essentials" build (~103 MB) rather than BtbN's (~170 MB):
# FFmpeg dominates the size of the finished .exe, and this one still
# includes libmp3lame, which the audio-only mode needs. Only ffmpeg.exe
# is kept -- see packaging\media-downloader.spec for why ffprobe.exe
# isn't bundled. Keep this in sync with FFMPEG_WINDOWS_URL in build.sh.
$FfmpegReleaseUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

# $ErrorActionPreference doesn't cover native executables, so check
# their exit codes explicitly.
function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "'$Exe $($Arguments -join ' ')' failed with exit code $LASTEXITCODE"
    }
}

Write-Host "==> Setting up build venv"
if (-not (Test-Path ".build-venv")) {
    if ($env:BUILD_PYTHON) {
        Invoke-Checked $env:BUILD_PYTHON @("-m", "venv", ".build-venv")
    } else {
        Invoke-Checked "py" @("-m", "venv", ".build-venv")
    }
}
$Python = Join-Path $RootDir ".build-venv\Scripts\python.exe"
# `python -m pip`, not pip.exe: pip.exe can't replace itself on Windows.
Invoke-Checked $Python @("-m", "pip", "install", "--quiet", "--upgrade", "pip")
Invoke-Checked $Python @("-m", "pip", "install", "--quiet", "-r", "requirements.txt", "-r", "requirements-build.txt")

if (-not (Test-Path "build\ffmpeg-win\ffmpeg.exe")) {
    Write-Host "==> Downloading static FFmpeg (Windows)"
    New-Item -ItemType Directory -Force -Path "build\ffmpeg-win" | Out-Null
    $TmpName = [System.IO.Path]::GetRandomFileName()
    $TmpZip = Join-Path $env:TEMP "$TmpName.zip"
    $UnzipDir = Join-Path $env:TEMP $TmpName
    $ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest is very slow with the progress bar on
    Invoke-WebRequest -Uri $FfmpegReleaseUrl -OutFile $TmpZip
    Expand-Archive -Path $TmpZip -DestinationPath $UnzipDir
    $ExtractedDir = Get-ChildItem -Path $UnzipDir -Directory | Select-Object -First 1
    Copy-Item (Join-Path $ExtractedDir.FullName "bin\ffmpeg.exe") "build\ffmpeg-win\ffmpeg.exe"
    Remove-Item $TmpZip -Force
    Remove-Item $UnzipDir -Recurse -Force
}

Write-Host "==> Running PyInstaller"
Invoke-Checked $Python @(
    "-m", "PyInstaller", "--clean", "--noconfirm",
    "--distpath", "dist\windows", "--workpath", "build\pyinstaller-windows",
    "packaging\media-downloader.spec"
)

Write-Host "==> Smoke test"
Invoke-Checked (Join-Path $RootDir "dist\windows\media-downloader-cli.exe") @("--help") | Out-Null

Write-Host "==> Windows build OK: dist\windows\media-downloader-cli.exe, dist\windows\media-downloader-ui.exe"
