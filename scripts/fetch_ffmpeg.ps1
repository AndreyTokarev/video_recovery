# Download FFmpeg Windows binaries into ./bin for local use and PyInstaller.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/fetch_ffmpeg.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Bin = Join-Path $Root "bin"
$Tmp = Join-Path $Root ".ffmpeg_tmp"
$Url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

New-Item -ItemType Directory -Force -Path $Bin | Out-Null
if (Test-Path $Tmp) { Remove-Item -Recurse -Force $Tmp }
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null

$Zip = Join-Path $Tmp "ffmpeg.zip"
Write-Host "Downloading FFmpeg essentials..."
Invoke-WebRequest -Uri $Url -OutFile $Zip

Write-Host "Extracting..."
Expand-Archive -Path $Zip -DestinationPath $Tmp -Force

$Ffmpeg = Get-ChildItem -Path $Tmp -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
$Ffprobe = Get-ChildItem -Path $Tmp -Recurse -Filter "ffprobe.exe" | Select-Object -First 1
if (-not $Ffmpeg -or -not $Ffprobe) {
    throw "ffmpeg.exe / ffprobe.exe not found in archive"
}

Copy-Item $Ffmpeg.FullName (Join-Path $Bin "ffmpeg.exe") -Force
Copy-Item $Ffprobe.FullName (Join-Path $Bin "ffprobe.exe") -Force
Remove-Item -Recurse -Force $Tmp

Write-Host "Installed:"
Get-ChildItem $Bin | ForEach-Object { Write-Host "  $($_.FullName)" }
