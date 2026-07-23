[CmdletBinding()]
param(
    [string]$Repository = "caotiensinh/LANCameraViewer"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Ensure-Command([string]$Name, [string]$WingetId) {
    if (Get-Command $Name -ErrorAction SilentlyContinue) { return }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget is required to install $Name automatically."
    }
    & winget install --id $WingetId --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "Could not install $Name." }
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

Ensure-Command "git" "Git.Git"
Ensure-Command "gh" "GitHub.cli"

& gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "GitHub sign-in is required once." -ForegroundColor Yellow
    & gh auth login --web --git-protocol https
    if ($LASTEXITCODE -ne 0) { throw "GitHub authentication failed." }
}

if (-not (Test-Path ".git")) {
    & git init -b main
    & git add .
    & git commit -m "Initial public release"
}

& gh repo view $Repository 2>$null
if ($LASTEXITCODE -eq 0) {
    throw "Repository $Repository already exists. Refusing to overwrite it automatically."
}

& gh repo create $Repository --public --source . --remote origin --push --description "Lightweight native Windows RTSP LAN camera viewer using Python, PySide6, and LibVLC."
if ($LASTEXITCODE -ne 0) { throw "Repository creation or push failed." }

Write-Host "Published: https://github.com/$Repository" -ForegroundColor Green
