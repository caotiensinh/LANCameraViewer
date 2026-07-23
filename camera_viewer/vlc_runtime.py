from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

LOGGER = logging.getLogger(__name__)
_DLL_DIRECTORY_HANDLES: list[Any] = []


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

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate.resolve(strict=False)).lower()
        if normalized not in seen:
            seen.add(normalized)
            unique.append(candidate)
    return unique


def prepare_vlc_environment() -> Path | None:
    if sys.platform != "win32":
        return None

    for directory in _candidate_vlc_directories():
        dll_path = directory / "libvlc.dll"
        plugin_path = directory / "plugins"
        if dll_path.exists():
            os.environ["VLC_PLUGIN_PATH"] = str(plugin_path)
            os.environ["PATH"] = f"{directory}{os.pathsep}{os.environ.get('PATH', '')}"
            if hasattr(os, "add_dll_directory"):
                # Keep the returned handle alive. If it is garbage-collected,
                # Windows closes the DLL search directory and later LibVLC/plugin
                # loads can fail on machines where VLC was not already in PATH.
                handle = os.add_dll_directory(str(directory))
                _DLL_DIRECTORY_HANDLES.append(handle)
                if plugin_path.exists():
                    plugin_handle = os.add_dll_directory(str(plugin_path))
                    _DLL_DIRECTORY_HANDLES.append(plugin_handle)
            LOGGER.info("Using VLC runtime from %s", directory)
            return directory

    LOGGER.error("No VLC runtime directory containing libvlc.dll was found")
    return None


def load_vlc() -> ModuleType:
    detected_path = prepare_vlc_environment()
    try:
        import vlc  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on host installation
        raise VlcRuntimeError(
            "python-vlc is not installed. Run the one-command installer again."
        ) from exc

    try:
        version = vlc.libvlc_get_version()
        LOGGER.info("Loaded LibVLC version %s", version.decode(errors="replace"))
    except Exception as exc:  # pragma: no cover - depends on Windows/VLC
        location = f" Detected VLC path: {detected_path}" if detected_path else ""
        raise VlcRuntimeError(
            "LibVLC could not be loaded. Install 64-bit VLC or set VLC_HOME."
            + location
        ) from exc

    return vlc
