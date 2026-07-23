[CmdletBinding()]
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\LANCameraViewer",
    [switch]$NoPause
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$lines = New-Object System.Collections.Generic.List[string]
$failures = 0

function Add-Line([string]$Text = "") {
    $lines.Add($Text)
    Write-Host $Text
}

function Add-Check([string]$Name, [bool]$Passed, [string]$Details) {
    if ($Passed) {
        Add-Line "[OK]   $Name - $Details"
    } else {
        Add-Line "[FAIL] $Name - $Details"
        $script:failures++
    }
}

function Mask-RtspUrl([string]$Url) {
    if ([string]::IsNullOrWhiteSpace($Url)) { return "<empty>" }
    return [regex]::Replace($Url, '(?<=://)[^/@]+@', '***@')
}

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutMs = 2500) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$reportName = "diagnostics-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt"
$logDir = Join-Path $InstallDir "logs"
$reportPath = Join-Path $logDir $reportName
$configPath = Join-Path $InstallDir "config\cameras.json"
$appLogPath = Join-Path $logDir "camera-viewer.log"

New-Item -ItemType Directory -Force $logDir | Out-Null

Add-Line "LAN Camera Viewer diagnostics"
Add-Line "Time: $timestamp"
Add-Line "Computer: $env:COMPUTERNAME"
Add-Line "User: $env:USERNAME"
Add-Line "Install directory: $InstallDir"
Add-Line ""

Add-Line "=== Local IPv4 addresses ==="
try {
    $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.AddressState -eq "Preferred" } |
        Sort-Object InterfaceAlias, IPAddress
    if ($addresses) {
        foreach ($address in $addresses) {
            Add-Line ("{0}: {1}/{2}" -f $address.InterfaceAlias, $address.IPAddress, $address.PrefixLength)
        }
    } else {
        Add-Line "No preferred non-loopback IPv4 address found."
    }
} catch {
    Add-Line "Get-NetIPAddress unavailable; run ipconfig for adapter details."
}
Add-Line ""

Add-Line "=== Route to camera subnet ==="
try {
    $routes = Get-NetRoute -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object { $_.DestinationPrefix -eq "192.168.11.0/24" -or $_.DestinationPrefix -eq "0.0.0.0/0" } |
        Sort-Object RouteMetric
    if ($routes) {
        foreach ($route in $routes) {
            Add-Line ("{0} via {1}, interface {2}, metric {3}" -f $route.DestinationPrefix, $route.NextHop, $route.InterfaceAlias, $route.RouteMetric)
        }
    } else {
        Add-Line "No explicit 192.168.11.0/24 or default IPv4 route found."
    }
} catch {
    Add-Line "Could not read Windows routes: $($_.Exception.Message)"
}
Add-Line ""

$config = $null
$cameras = @()
if (Test-Path $configPath) {
    try {
        $config = Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $cameras = @($config.cameras)
        Add-Check "Camera configuration" $true "$configPath ($($cameras.Count) camera(s))"
    } catch {
        Add-Check "Camera configuration" $false "Invalid JSON: $($_.Exception.Message)"
    }
} else {
    Add-Check "Camera configuration" $false "File not found: $configPath"
}
Add-Line ""

Add-Line "=== RTSP camera checks ==="
if ($cameras.Count -eq 0) {
    Add-Line "No cameras are configured. The installer cannot copy private settings from another PC."
    $failures++
} else {
    foreach ($camera in $cameras) {
        $name = [string]$camera.name
        $urls = @(
            @{ Label = "main"; Value = [string]$camera.rtsp_url },
            @{ Label = "grid"; Value = [string]$camera.grid_rtsp_url }
        )
        foreach ($entry in $urls) {
            $url = $entry.Value
            if ([string]::IsNullOrWhiteSpace($url)) {
                if ($entry.Label -eq "main") {
                    Add-Check "$name main URL" $false "empty"
                }
                continue
            }
            try {
                $uri = [Uri]$url
                if ($uri.Scheme -notin @("rtsp", "rtsps")) {
                    Add-Check "$name $($entry.Label) URL" $false "must start with rtsp:// or rtsps://: $(Mask-RtspUrl $url)"
                    continue
                }
                $port = if ($uri.IsDefaultPort -or $uri.Port -le 0) { 554 } else { $uri.Port }
                $reachable = Test-TcpPort $uri.DnsSafeHost $port
                Add-Check "$name $($entry.Label) $($uri.DnsSafeHost):$port" $reachable (Mask-RtspUrl $url)
            } catch {
                Add-Check "$name $($entry.Label) URL" $false "invalid URL: $(Mask-RtspUrl $url)"
            }
        }
    }
}
Add-Line ""

Add-Line "=== VLC runtime ==="
$vlcCandidates = @(
    $env:VLC_HOME,
    $(if ($env:ProgramFiles) { "$env:ProgramFiles\VideoLAN\VLC" }),
    $(if (${env:ProgramFiles(x86)}) { "${env:ProgramFiles(x86)}\VideoLAN\VLC" }),
    $(if ($env:LOCALAPPDATA) { "$env:LOCALAPPDATA\Programs\VideoLAN\VLC" })
) | Where-Object { $_ } | Select-Object -Unique
$vlcDir = $vlcCandidates | Where-Object { Test-Path (Join-Path $_ "libvlc.dll") } | Select-Object -First 1
Add-Check "64-bit VLC / libvlc.dll" ([bool]$vlcDir) ($(if ($vlcDir) { $vlcDir } else { "not found" }))

$venvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Add-Check "Python environment" $true $venvPython
    try {
        $runtimeOutput = & $venvPython -c "import sys, PySide6, vlc; print(sys.version.split()[0]); print(PySide6.__version__); print(vlc.libvlc_get_version().decode(errors='replace'))" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Add-Check "Python/PySide6/python-vlc" $true (($runtimeOutput | ForEach-Object { [string]$_ }) -join " | ")
        } else {
            Add-Check "Python/PySide6/python-vlc" $false (($runtimeOutput | ForEach-Object { [string]$_ }) -join " | ")
        }
    } catch {
        Add-Check "Python/PySide6/python-vlc" $false $_.Exception.Message
    }
} else {
    Add-Check "Python environment" $false "not found: $venvPython"
}
Add-Line ""

Add-Line "=== Recent application log ==="
if (Test-Path $appLogPath) {
    Get-Content $appLogPath -Tail 80 -ErrorAction SilentlyContinue | ForEach-Object { Add-Line $_ }
} else {
    Add-Line "No application log found at $appLogPath"
}
Add-Line ""
Add-Line "Failures: $failures"

$lines | Set-Content -Path $reportPath -Encoding UTF8
Write-Host ""
Write-Host "Diagnostic report saved to:" -ForegroundColor Cyan
Write-Host $reportPath -ForegroundColor White

if (-not $NoPause) {
    Write-Host ""
    Read-Host "Press Enter to close"
}

if ($failures -gt 0) { exit 1 }
exit 0
