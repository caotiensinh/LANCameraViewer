$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Host "Python launcher 'py' was not found. Run the one-command installer from README.md." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path ".venv")) {
    py -3.12 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

$vlcCandidates = @(
    $(if ($env:ProgramFiles) { Join-Path $env:ProgramFiles "VideoLAN\VLC" }),
    $(if (${env:ProgramFiles(x86)}) { Join-Path ${env:ProgramFiles(x86)} "VideoLAN\VLC" }),
    $(if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA "Programs\VideoLAN\VLC" }),
    $env:VLC_HOME
) | Where-Object { $_ }
$vlcDir = $vlcCandidates | Where-Object { Test-Path (Join-Path $_ "libvlc.dll") } | Select-Object -First 1
if (-not $vlcDir) {
    Write-Host "64-bit VLC is not installed. Run the one-command installer from README.md." -ForegroundColor Yellow
    exit 1
}

$env:VLC_HOME = $vlcDir
& .\.venv\Scripts\python.exe app.py
