# LAN Camera Viewer

A lightweight native Windows application for viewing RTSP IP cameras directly over a LAN. It uses Python, PySide6, and LibVLC without recording, transcoding, or copying video frames through OpenCV.

## Features

- Direct RTSP playback through LibVLC.
- Layouts: `1x1`, `1x2`, `2x2`, `3x3`, and `4x4`.
- Double-click a camera for fullscreen; double-click again or press `Esc` to return.
- Minimal status indicator: green when playing, gray when connecting or offline.
- Camera names and controls appear only while the mouse is moving, then automatically hide.
- Add, edit, enable, disable, and delete cameras from the settings dialog.
- External JSON configuration at `config/cameras.json`.
- RTSP over TCP by default, audio disabled, hardware decoding enabled automatically.
- Automatic reconnect after network or camera interruptions.
- Hidden streams are stopped by default to reduce CPU and GPU load on weak PCs.

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
7. Starts the application.

Windows 10/11 with Microsoft **App Installer** (`winget`) is required for fully automatic prerequisite installation.

## Camera configuration

Example URL:

```text
rtsp://192.168.11.124:554/stream1
```

With authentication:

```text
rtsp://username:password@192.168.11.124:554/stream1
```

RTSP URLs must use `rtsp://`, not `http://`.

Default camera configuration is stored in:

```text
config/cameras.json
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

For weak PCs, keep this setting disabled:

```json
"keep_hidden_streams_alive": false
```

Use each camera's low-resolution substream in multi-camera layouts when available. Switching the implementation from Python to Rust does not remove the main cost, which is decoding multiple video streams.

## License

MIT

## Repository bootstrap for the owner

The included `publish_to_github.ps1` script can create the public repository and push this source from a Windows machine with one command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\publish_to_github.ps1
```

It installs Git and GitHub CLI through `winget` when needed and opens GitHub's official sign-in flow once if the machine is not authenticated.
