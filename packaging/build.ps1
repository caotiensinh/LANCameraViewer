$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Run install_and_run.bat once before building." -ForegroundColor Red
    exit 1
}

$VlcCandidates = @(
    (Join-Path $env:ProgramFiles "VideoLAN\VLC"),
    (Join-Path ${env:ProgramFiles(x86)} "VideoLAN\VLC"),
    (Join-Path $env:LOCALAPPDATA "Programs\VideoLAN\VLC"),
    $env:VLC_HOME
) | Where-Object { $_ }

$VlcDir = $VlcCandidates | Where-Object { Test-Path (Join-Path $_ "libvlc.dll") } | Select-Object -First 1
if (-not $VlcDir) {
    Write-Host "64-bit VLC was not found." -ForegroundColor Red
    exit 1
}

& .\.venv\Scripts\python.exe -m pip install --upgrade -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

& .\.venv\Scripts\python.exe -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "LANCameraViewer" `
    --add-binary "$VlcDir\*.dll;vlc" `
    --add-data "$VlcDir\plugins;vlc\plugins" `
    --add-data "config;config" `
    app.py

$ExternalConfig = "$ProjectRoot\dist\LANCameraViewer\config"
New-Item -ItemType Directory -Force $ExternalConfig | Out-Null
Copy-Item -Force "$ProjectRoot\config\cameras.json" "$ExternalConfig\cameras.json"

Write-Host "Build complete: dist\LANCameraViewer\LANCameraViewer.exe" -ForegroundColor Green
