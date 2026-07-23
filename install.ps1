[CmdletBinding()]
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\LANCameraViewer",
    [switch]$NoLaunch,
    [switch]$NoDesktopShortcut,
    [switch]$ResetCameraConfig
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$RepoOwner = "caotiensinh"
$RepoName = "LANCameraViewer"
$Branch = "main"
$ArchiveUrl = "https://github.com/$RepoOwner/$RepoName/archive/refs/heads/$Branch.zip"

function Write-Step([string]$Message) {
    Write-Host "[LAN Camera Viewer] $Message" -ForegroundColor Cyan
}

function Refresh-ProcessPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Find-Python312 {
    $candidates = @(
        (Get-Command py -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        $(if ($env:LOCALAPPDATA) { "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" }),
        $(if ($env:ProgramFiles) { "$env:ProgramFiles\Python312\python.exe" }),
        $(if (${env:ProgramFiles(x86)}) { "${env:ProgramFiles(x86)}\Python312\python.exe" })
    ) | Where-Object { $_ -and (Test-Path $_) }

    foreach ($candidate in $candidates) {
        try {
            if ((Split-Path -Leaf $candidate) -ieq "py.exe") {
                & $candidate -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" 2>$null
                if ($LASTEXITCODE -eq 0) { return @{ Path = $candidate; Args = @("-3.12") } }
            } else {
                & $candidate -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" 2>$null
                if ($LASTEXITCODE -eq 0) { return @{ Path = $candidate; Args = @() } }
            }
        } catch { }
    }
    return $null
}

function Find-VlcDirectory {
    $candidates = @(
        $env:VLC_HOME,
        $(if ($env:ProgramFiles) { "$env:ProgramFiles\VideoLAN\VLC" }),
        $(if (${env:ProgramFiles(x86)}) { "${env:ProgramFiles(x86)}\VideoLAN\VLC" }),
        $(if ($env:LOCALAPPDATA) { "$env:LOCALAPPDATA\Programs\VideoLAN\VLC" })
    ) | Where-Object { $_ } | Select-Object -Unique

    foreach ($candidate in $candidates) {
        if (Test-Path (Join-Path $candidate "libvlc.dll")) { return $candidate }
    }
    return $null
}

function Install-WithWinget([string]$Id, [string]$DisplayName) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget is required to install $DisplayName automatically. Install 'App Installer' from Microsoft Store and run this command again."
    }

    Write-Step "Installing $DisplayName..."
    & winget install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) {
        throw "winget could not install $DisplayName (exit code $LASTEXITCODE)."
    }
    Refresh-ProcessPath
}

function Backup-Config([string]$Path) {
    if (-not (Test-Path $Path)) { return }
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backup = "$Path.$stamp.bak"
    Copy-Item $Path $backup -Force
    Write-Step "Existing camera configuration backed up to $backup"
}

Write-Step "Checking prerequisites..."
$python = Find-Python312
if (-not $python) {
    Install-WithWinget "Python.Python.3.12" "Python 3.12 x64"
    $python = Find-Python312
}
if (-not $python) { throw "Python 3.12 was installed but could not be located." }

$vlcDir = Find-VlcDirectory
if (-not $vlcDir) {
    Install-WithWinget "VideoLAN.VLC" "VLC 64-bit"
    $vlcDir = Find-VlcDirectory
}
if (-not $vlcDir) { throw "VLC was installed but libvlc.dll could not be located." }

$tempRoot = Join-Path $env:TEMP ("LANCameraViewer-" + [Guid]::NewGuid().ToString("N"))
$archivePath = Join-Path $tempRoot "source.zip"
$extractPath = Join-Path $tempRoot "source"
New-Item -ItemType Directory -Force $tempRoot, $extractPath | Out-Null

try {
    Write-Step "Downloading the latest source..."
    Invoke-WebRequest -Uri $ArchiveUrl -OutFile $archivePath -UseBasicParsing -Headers @{ "User-Agent" = "LANCameraViewer-Installer" }
    Expand-Archive -Path $archivePath -DestinationPath $extractPath -Force

    $sourceRoot = Get-ChildItem $extractPath -Directory | Select-Object -First 1
    if (-not $sourceRoot) { throw "Downloaded archive has an unexpected structure." }

    New-Item -ItemType Directory -Force $InstallDir | Out-Null

    # Preserve the virtual environment, user configuration, and logs during updates.
    Get-ChildItem $InstallDir -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notin @(".venv", "config", "logs") } |
        Remove-Item -Recurse -Force

    Write-Step "Installing application files to $InstallDir..."
    Get-ChildItem $sourceRoot.FullName -Force |
        Where-Object { $_.Name -notin @(".git", ".venv", "config", "logs") } |
        Copy-Item -Destination $InstallDir -Recurse -Force

    $configDir = Join-Path $InstallDir "config"
    New-Item -ItemType Directory -Force $configDir | Out-Null
    $installedConfig = Join-Path $configDir "cameras.json"
    $sourceConfig = Join-Path $sourceRoot.FullName "config\cameras.json"
    if (-not (Test-Path $sourceConfig)) {
        throw "The downloaded source does not contain config\cameras.json."
    }

    if ($ResetCameraConfig) {
        Backup-Config $installedConfig
        Copy-Item $sourceConfig $installedConfig -Force
        Write-Step "Camera configuration reset to the repository defaults."
    } elseif (-not (Test-Path $installedConfig)) {
        Copy-Item $sourceConfig $installedConfig -Force
        Write-Step "Installed the default camera configuration."
    } else {
        try {
            $existingConfig = Get-Content $installedConfig -Raw -Encoding UTF8 | ConvertFrom-Json
            $cameraCount = @($existingConfig.cameras).Count
            Write-Step "Preserving existing camera configuration ($cameraCount camera(s))."
            if ($cameraCount -eq 0) {
                Write-Warning "The preserved configuration contains zero cameras. Run the reset command shown after installation if this was not intentional."
            }
        } catch {
            Backup-Config $installedConfig
            Copy-Item $sourceConfig $installedConfig -Force
            Write-Warning "The existing camera configuration was invalid JSON and was replaced with the repository defaults."
        }
    }

    New-Item -ItemType Directory -Force (Join-Path $InstallDir "logs") | Out-Null

    $venvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Step "Creating Python environment..."
        $venvArguments = @($python.Args) + @("-m", "venv", (Join-Path $InstallDir ".venv"))
        & $python.Path $venvArguments
        if ($LASTEXITCODE -ne 0) { throw "Could not create the Python virtual environment." }
    }

    Write-Step "Installing Python dependencies..."
    & $venvPython -m pip install --disable-pip-version-check --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
    & $venvPython -m pip install --disable-pip-version-check --upgrade -r (Join-Path $InstallDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }

    [Environment]::SetEnvironmentVariable("VLC_HOME", $vlcDir, "User")
    $env:VLC_HOME = $vlcDir

    $pythonw = Join-Path $InstallDir ".venv\Scripts\pythonw.exe"
    $appPath = Join-Path $InstallDir "app.py"
    $shell = New-Object -ComObject WScript.Shell

    $startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\LAN Camera Viewer"
    New-Item -ItemType Directory -Force $startMenuDir | Out-Null

    $shortcutTargets = @(
        (Join-Path $startMenuDir "LAN Camera Viewer.lnk")
    )
    if (-not $NoDesktopShortcut) {
        $shortcutTargets += (Join-Path ([Environment]::GetFolderPath("Desktop")) "LAN Camera Viewer.lnk")
    }

    foreach ($shortcutPath in $shortcutTargets) {
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $pythonw
        $shortcut.Arguments = "`"$appPath`""
        $shortcut.WorkingDirectory = $InstallDir
        $shortcut.Description = "Lightweight RTSP LAN camera viewer"
        $shortcut.Save()
    }

    $updateCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command `"irm https://raw.githubusercontent.com/$RepoOwner/$RepoName/$Branch/install.ps1 | iex`""
    $diagnoseCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\diagnose.ps1`""
    $resetCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\reset_config.ps1`""

    Set-Content -Path (Join-Path $startMenuDir "Update LAN Camera Viewer.cmd") -Value "@echo off`r`n$updateCommand`r`npause`r`n" -Encoding ASCII
    Set-Content -Path (Join-Path $startMenuDir "Diagnose LAN Camera Viewer.cmd") -Value "@echo off`r`n$diagnoseCommand`r`n" -Encoding ASCII
    Set-Content -Path (Join-Path $startMenuDir "Reset Camera Configuration.cmd") -Value "@echo off`r`n$resetCommand`r`npause`r`n" -Encoding ASCII
    Set-Content -Path (Join-Path $InstallDir "run.cmd") -Value "@echo off`r`nset `"VLC_HOME=$vlcDir`"`r`nstart `"`" `"$pythonw`" `"$appPath`"`r`n" -Encoding ASCII
    Set-Content -Path (Join-Path $InstallDir "run-debug.cmd") -Value "@echo off`r`nset `"VLC_HOME=$vlcDir`"`r`ncd /d `"$InstallDir`"`r`n`"$venvPython`" `"$appPath`"`r`npause`r`n" -Encoding ASCII

    $installedCameraCount = 0
    try {
        $installedCameraCount = @((Get-Content $installedConfig -Raw -Encoding UTF8 | ConvertFrom-Json).cameras).Count
    } catch { }

    Write-Host ""
    Write-Host "LAN Camera Viewer installed successfully." -ForegroundColor Green
    Write-Host "Location: $InstallDir"
    Write-Host "Camera config: $installedConfig"
    Write-Host "Configured cameras: $installedCameraCount"
    Write-Host "Diagnostics: Start Menu > LAN Camera Viewer > Diagnose LAN Camera Viewer"
    Write-Host ""
    Write-Host "Important: this installer does not copy private camera credentials or custom RTSP paths from another PC." -ForegroundColor Yellow
    Write-Host "Both PCs must have equivalent cameras.json settings and network access to the camera subnet." -ForegroundColor Yellow

    if ($installedCameraCount -eq 0) {
        Write-Host ""
        Write-Host "To restore the four repository sample cameras, run:" -ForegroundColor Yellow
        Write-Host "powershell -NoProfile -ExecutionPolicy Bypass -Command `"irm https://raw.githubusercontent.com/$RepoOwner/$RepoName/$Branch/reset_config.ps1 | iex`""
    }

    if (-not $NoLaunch) {
        Write-Step "Starting LAN Camera Viewer..."
        Start-Process -FilePath $pythonw -ArgumentList "`"$appPath`"" -WorkingDirectory $InstallDir
    }
}
finally {
    Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
