# Build Windows GUI binary with PyInstaller (onedir).
# Usage: powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$BinFfmpeg = Join-Path $Root "bin\ffmpeg.exe"
$BinFfprobe = Join-Path $Root "bin\ffprobe.exe"
if (-not (Test-Path $BinFfmpeg) -or -not (Test-Path $BinFfprobe)) {
    Write-Host "FFmpeg not in bin/ — fetching..."
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\fetch_ffmpeg.ps1")
}

Write-Host "Syncing project with uv..."
uv sync --extra dev

Write-Host "Building VideoRecovery..."
uv run pyinstaller --noconfirm --clean video_recovery.spec

$Out = Join-Path $Root "dist\VideoRecovery"
Write-Host ""
Write-Host "Build complete: $Out"
Write-Host "Run: $Out\VideoRecovery.exe"
