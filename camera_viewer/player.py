from __future__ import annotations

import logging
import sys
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget

from .models import CameraConfig, ViewerSettings
from .vlc_runtime import load_vlc

LOGGER = logging.getLogger(__name__)


class VlcEngine:
    def __init__(self):
        self.vlc = load_vlc()
        args = [
            "--no-video-title-show",
            "--no-osd",
            "--no-audio",
            "--avcodec-hw=any",
            "--drop-late-frames",
            "--skip-frames",
            "--quiet",
        ]
        self.instance = self.vlc.Instance(*args)
        if self.instance is None:
            raise RuntimeError("Could not create LibVLC instance")


class CameraPlayer(QObject):
    state_changed = Signal(str)
    error_message = Signal(str)
    _state_event = Signal(str)
    _failure_event = Signal(str)

    def __init__(
        self,
        engine: VlcEngine,
        camera: CameraConfig,
        settings: ViewerSettings,
        video_widget: QWidget,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.engine = engine
        self.camera = camera
        self.settings = settings
        self.video_widget = video_widget
        self.media_player = self.engine.instance.media_player_new()
        self.media_player.video_set_mouse_input(False)
        self.media_player.video_set_key_input(False)
        self._active = False
        self._closing = False
        self._last_state = "offline"

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._reconnect)
        self._state_event.connect(self._set_state)
        self._failure_event.connect(self._handle_failure)

        self._attach_events()

    @property
    def is_active(self) -> bool:
        return self._active

    def _attach_events(self) -> None:
        manager = self.media_player.event_manager()
        event_type = self.engine.vlc.EventType
        manager.event_attach(event_type.MediaPlayerOpening, self._on_opening)
        manager.event_attach(event_type.MediaPlayerBuffering, self._on_buffering)
        manager.event_attach(event_type.MediaPlayerPlaying, self._on_playing)
        manager.event_attach(event_type.MediaPlayerEncounteredError, self._on_error)
        manager.event_attach(event_type.MediaPlayerEndReached, self._on_end)

    def bind_video_output(self) -> None:
        win_id = int(self.video_widget.winId())
        if sys.platform == "win32":
            self.media_player.set_hwnd(win_id)
        elif sys.platform.startswith("linux"):
            self.media_player.set_xwindow(win_id)
        elif sys.platform == "darwin":
            self.media_player.set_nsobject(win_id)

    def set_active(self, active: bool) -> None:
        if self._closing or not self.camera.enabled:
            active = False
        if active == self._active:
            if active:
                self.bind_video_output()
            return

        self._active = active
        if active:
            self.start()
        else:
            self.stop()

    def start(self) -> None:
        if self._closing or not self._active or not self.camera.rtsp_url:
            return

        self._reconnect_timer.stop()
        self.bind_video_output()
        self._set_state("connecting")

        media = self.engine.instance.media_new(self.camera.rtsp_url)
        media.add_option(":no-audio")
        media.add_option(f":network-caching={self.settings.network_caching_ms}")
        media.add_option(f":live-caching={self.settings.network_caching_ms}")
        if self.settings.rtsp_transport == "tcp":
            media.add_option(":rtsp-tcp")

        self.media_player.set_media(media)
        result = self.media_player.play()
        if result == -1:
            self._handle_failure("LibVLC rejected the RTSP stream")

    def stop(self) -> None:
        self._reconnect_timer.stop()
        try:
            self.media_player.stop()
        except Exception:
            LOGGER.exception("Failed to stop camera %s", self.camera.name)
        self._set_state("offline")

    def close(self) -> None:
        self._closing = True
        self._active = False
        self._reconnect_timer.stop()
        try:
            self.media_player.stop()
            self.media_player.release()
        except Exception:
            LOGGER.exception("Failed to release camera %s", self.camera.name)

    def _on_opening(self, _event: Any) -> None:
        self._state_event.emit("connecting")

    def _on_buffering(self, _event: Any) -> None:
        if self._last_state != "online":
            self._state_event.emit("connecting")

    def _on_playing(self, _event: Any) -> None:
        self._state_event.emit("online")

    def _on_error(self, _event: Any) -> None:
        self._failure_event.emit("RTSP connection failed")

    def _on_end(self, _event: Any) -> None:
        self._failure_event.emit("RTSP stream ended")

    def _handle_failure(self, message: str) -> None:
        LOGGER.warning("%s: %s", self.camera.name, message)
        self._set_state("offline")
        self.error_message.emit(message)
        if self._active and self.settings.auto_reconnect and not self._closing:
            self._reconnect_timer.start(self.settings.reconnect_interval_seconds * 1000)

    def _reconnect(self) -> None:
        if not self._active or self._closing:
            return
        try:
            self.media_player.stop()
        except Exception:
            LOGGER.exception("Failed before reconnecting camera %s", self.camera.name)
        self.start()

    def _set_state(self, state: str) -> None:
        if state == self._last_state:
            return
        self._last_state = state
        self.state_changed.emit(state)
