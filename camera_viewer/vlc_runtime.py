from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType


class VlcRuntimeError(RuntimeError):
    pass


def _candidate_vlc_directories() -> list[Path]:
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidates.append(bundle_root / "vlc")
        candidates.append(Path(sys.executable).resolve().parent / "vlc")

    vlc_home = os.getenv("VLC_HOME")
    if vlc_home:
        candidates.append(Path(vlc_home))

    for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        root = os.getenv(env_name)
        if root:
            candidates.append(Path(root) / "VideoLAN" / "VLC")

    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Programs" / "VideoLAN" / "VLC")

    return candidates


def prepare_vlc_environment() -> Path | None:
    if sys.platform != "win32":
        return None

    for directory in _candidate_vlc_directories():
        if (directory / "libvlc.dll").exists():
            os.environ.setdefault("VLC_PLUGIN_PATH", str(directory / "plugins"))
            os.environ["PATH"] = f"{directory}{os.pathsep}{os.environ.get('PATH', '')}"
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(directory))
            return directory
    return None


def load_vlc() -> ModuleType:
    detected_path = prepare_vlc_environment()
    try:
        import vlc  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on host installation
        raise VlcRuntimeError(
            "python-vlc is not installed. Run install_and_run.bat first."
        ) from exc

    try:
        vlc.libvlc_get_version()
    except Exception as exc:  # pragma: no cover - depends on Windows/VLC
        location = f" Detected VLC path: {detected_path}" if detected_path else ""
        raise VlcRuntimeError(
            "LibVLC could not be loaded. Install 64-bit VLC or set VLC_HOME."
            + location
        ) from exc

    return vlc
