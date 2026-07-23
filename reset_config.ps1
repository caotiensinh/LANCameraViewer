[CmdletBinding()]
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\LANCameraViewer"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$ConfigUrl = "https://raw.githubusercontent.com/caotiensinh/LANCameraViewer/main/config/cameras.json"
$configDir = Join-Path $InstallDir "config"
$configPath = Join-Path $configDir "cameras.json"
$tempPath = Join-Path $env:TEMP ("LANCameraViewer-config-" + [Guid]::NewGuid().ToString("N") + ".json")

New-Item -ItemType Directory -Force $configDir | Out-Null

try {
    Write-Host "Downloading the public sample camera configuration..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $ConfigUrl -OutFile $tempPath -UseBasicParsing -Headers @{ "User-Agent" = "LANCameraViewer-ConfigReset" }

    $downloaded = Get-Content $tempPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $cameraCount = @($downloaded.cameras).Count
    if ($cameraCount -le 0) {
        throw "The downloaded sample configuration contains no cameras."
    }

    if (Test-Path $configPath) {
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $backupPath = "$configPath.$stamp.bak"
        Copy-Item $configPath $backupPath -Force
        Write-Host "Existing configuration backed up to:" -ForegroundColor Yellow
        Write-Host $backupPath
    }

    Copy-Item $tempPath $configPath -Force
    Write-Host ""
    Write-Host "Camera configuration reset successfully." -ForegroundColor Green
    Write-Host "Installed $cameraCount public sample camera(s)."
    Write-Host "Config: $configPath"
    Write-Host ""
    Write-Host "The public samples do not contain usernames or passwords." -ForegroundColor Yellow
    Write-Host "Copy cameras.json from the working PC when the cameras require credentials or custom RTSP paths." -ForegroundColor Yellow
} finally {
    Remove-Item $tempPath -Force -ErrorAction SilentlyContinue
}
