from __future__ import annotations

import sys
from pathlib import Path


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    return application_dir() / "config" / "cameras.json"


def log_path() -> Path:
    return application_dir() / "logs" / "camera-viewer.log"
