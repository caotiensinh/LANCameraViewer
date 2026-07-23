# LAN Camera Viewer

A lightweight native Windows application for viewing RTSP IP cameras directly over a LAN. It uses Python, PySide6, and LibVLC without recording, transcoding, or copying video frames through OpenCV.

## Features

- Direct RTSP playback through LibVLC.
- One isolated LibVLC instance, media player, and worker thread per camera.
- A slow or reconnecting camera cannot block the playback commands of other cameras.
- Layouts: `1x1`, `1x2`, `2x2`, `3x3`, and `4x4`.
- Double-click a camera for fullscreen; double-click again or press `Esc` to return.
- Minimal status indicator: green when playing, gray when connecting or offline.
- Camera names and controls appear only while the mouse is moving, then automatically hide.
- Add, edit, enable, disable, and delete cameras from the settings dialog.
- Separate optional grid/substream URL for weak PCs.
- External JSON configuration at `config/cameras.json`.
- RTSP over TCP by default, audio disabled, hardware decoding enabled automatically.
- Automatic reconnect after network or camera interruptions.
- Hidden streams are stopped by default to reduce CPU and GPU load.
- Decoder frame skipping is disabled for smoother motion; only frames that are already late may be discarded to stay close to live time.

## One-command Windows installation

Open **PowerShell** and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/caotiensinh/LANCameraViewer/main/install.ps1 | iex"
```

The installer:

1. Installs Python 3.12 and VLC through `winget` when they are missing.
2. Downloads the latest source from GitHub.
3. Installs the app under `%LOCALAPPDATA%\Programs\LANCameraViewer`.
4. Creates an isolated Python virtual environment.
5. Creates Start Menu and Desktop shortcuts.
6. Preserves camera configuration when run again as an update.
7. Creates diagnostic and configuration-reset commands in the Start Menu.
8. Starts the application.

Windows 10/11 with Microsoft **App Installer** (`winget`) is required for fully automatic prerequisite installation.

## Camera configuration

Main-stream example:

```text
rtsp://192.168.11.124:554/stream1
```

With authentication:

```text
rtsp://username:password@192.168.11.124:554/stream1
```

RTSP URLs must use `rtsp://`, not `http://`.

### Main stream and grid stream

Open the camera settings dialog and configure:

- **Main RTSP URL**: used in `1x1` and fullscreen.
- **Grid/substream URL**: optional lower-resolution stream used in `1x2`, `2x2`, `3x3`, and `4x4`.

For a weak PC, configure the camera substream as H.264, about `640x360` or `704x576`, and `15-20 FPS`. The exact RTSP path depends on the camera model. Some cameras use `/stream2`, but this is only an example and must be verified for the actual camera.

When Grid/substream URL is empty, the app falls back to the main stream.

Default camera configuration is stored in:

```text
config/cameras.json
```

## Installing on a second PC

The one-command installer downloads the application, but it does **not** copy private camera settings from another computer. Credentials and custom RTSP paths stored on a laptop remain local to that laptop.

The configuration path on every installed PC is:

```text
%LOCALAPPDATA%\Programs\LANCameraViewer\config\cameras.json
```

To reproduce the same setup on another PC:

1. Close the application on both PCs.
2. Copy `cameras.json` from the working PC.
3. Replace the same file on the new PC.
4. Start LAN Camera Viewer again.

Both PCs must also have network access to the camera subnet. For the repository sample addresses, the PC must be on `192.168.11.0/24` or have a valid route to that subnet.

## Diagnostics

After updating to version `0.1.4`, use:

```text
Start Menu > LAN Camera Viewer > Diagnose LAN Camera Viewer
```

The diagnostic command checks:

- the local IPv4 addresses and routes;
- whether `cameras.json` exists and how many cameras it contains;
- whether every configured RTSP host and port is reachable;
- whether VLC, `libvlc.dll`, Python, PySide6, and python-vlc load correctly;
- the latest application log entries.

The report is saved under:

```text
%LOCALAPPDATA%\Programs\LANCameraViewer\logs\diagnostics-*.txt
```

To reset the local configuration to the four public repository sample cameras:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=[scriptblock]::Create((irm https://raw.githubusercontent.com/caotiensinh/LANCameraViewer/main/install.ps1)); & $s -ResetCameraConfig"
```

This backs up the existing configuration first. The public sample URLs do not include camera usernames or passwords.

## Independent camera pipelines

Version `0.1.3` isolates every camera into its own command worker and its own LibVLC instance. Network connect, stop, stream switching, and reconnect operations are serialized only inside that camera's worker; they are not placed in one global queue.

The default fair decoder allocation is:

```json
"decoder_threads_per_camera": 1
```

Valid values are `1` to `4`. Keep it at `1` on a weak four-camera PC. Increase it only when viewing a single high-resolution main stream that cannot decode fast enough and CPU headroom is available.

The runtime log records a different worker name for every active camera:

```text
logs/camera-viewer.log
```

Expected examples:

```text
Camera 01: isolated LibVLC pipeline ready on rtsp-camera-01_0
Camera 02: isolated LibVLC pipeline ready on rtsp-camera-02_0
```

## Manual development setup

Requirements:

- Windows 10/11
- Python 3.12 x64
- VLC 64-bit

Run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe app.py
```

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Build a standalone Windows application

Run:

```powershell
.\build_windows.bat
```

Output:

```text
dist\LANCameraViewer\LANCameraViewer.exe
```

The build bundles LibVLC and its plugins. PyInstaller must run on Windows to produce a Windows executable.

## Performance recommendations

Keep hidden streams disabled:

```json
"keep_hidden_streams_alive": false
```

Keep grid substreams enabled:

```json
"use_grid_substream": true
```

If motion is still not smooth with four streams, check Windows Task Manager while viewing `2x2`:

- CPU near 90-100% usually means the streams are being software-decoded or are too large.
- GPU Video Decode near 0% may mean the camera codec/profile is unsupported by the PC hardware.
- H.265 on an older PC can be much heavier than H.264.
- Four main streams at 1080p/25-30 FPS may exceed the capability of a weak PC regardless of whether the UI is written in Python or Rust.

## License

MIT

## Repository bootstrap for the owner

The included `publish_to_github.ps1` script can create the public repository and push this source from a Windows machine with one command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\publish_to_github.ps1
```

It installs Git and GitHub CLI through `winget` when needed and opens GitHub's official sign-in flow once if the machine is not authenticated.
