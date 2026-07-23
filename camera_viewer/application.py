from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox

from .config_service import ConfigError, ConfigService
from .main_window import MainWindow
from .paths import config_path, log_path
from .styles import APP_STYLE
from .vlc_runtime import VlcRuntimeError


LOGGER = logging.getLogger(__name__)


def configure_logging() -> None:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def run() -> int:
    configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("LAN Camera Viewer")
    app.setStyleSheet(APP_STYLE)

    # Prevent multiple hidden pythonw.exe processes from decoding the same cameras.
    lock = QLockFile(str(log_path().parent / "lan-camera-viewer.lock"))
    lock.setStaleLockTime(15000)
    if not lock.tryLock(0):
        QMessageBox.information(
            None,
            "LAN Camera Viewer",
            "LAN Camera Viewer is already running. Close the existing window or "
            "end its LANCameraViewer/pythonw process before starting another copy.",
        )
        return 0

    try:
        try:
            window = MainWindow(ConfigService(config_path()))
        except (ConfigError, VlcRuntimeError, RuntimeError) as exc:
            QMessageBox.critical(None, "LAN Camera Viewer", str(exc))
            return 1

        window.showMaximized()
        return app.exec()
    finally:
        lock.unlock()
