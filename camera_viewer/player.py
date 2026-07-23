from __future__ import annotations

import logging
import sys
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from math import gcd
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget

from .models import CameraConfig, ViewerSettings
from .vlc_runtime import load_vlc

LOGGER = logging.getLogger(__name__)


class VlcEngine:
    """Factory for isolated per-camera LibVLC instances."""

    def __init__(self):
        self.vlc = load_vlc()

    def create_instance(self, decoder_threads: int):
        args = [
            "--no-video-title-show",
            "--no-osd",
            "--no-spu",
            "--no-audio",
            "--avcodec-hw=any",
            "--no-skip-frames",
            "--drop-late-frames",
            f"--avcodec-threads={decoder_threads}",
            "--quiet",
        ]
        instance = self.vlc.Instance(*args)
        if instance is None:
            raise RuntimeError("Could not create LibVLC instance")
        return instance


class CameraPlayer(QObject):
    """Independent RTSP pipeline with its own LibVLC instance and worker thread."""

    state_changed = Signal(str)
    error_message = Signal(str)
    _state_event = Signal(str)
    _failure_event = Signal(str)
    _worker_done = Signal(object)

    def __init__(
        self,
        engine: VlcEngine,
        camera: CameraConfig,
        settings: ViewerSettings,
        video_widget: QWidget,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.engine_factory = engine
        self.camera = camera
        self.settings = settings
        self.video_widget = video_widget

        self.vlc_instance: Any | None = None
        self.media_player: Any | None = None

        self._active = False
        self._closing = False
        self._released = False
        self._last_state = "offline"
        self._use_grid_stream = False
        self._stream_url = self.camera.stream_url(False)

        self._window_id: int | None = None
        self._aspect_ratio: str | None = None
        self._playing = False
        self._applied_url = ""
        self._restart_serial = 0
        self._applied_restart_serial = -1

        self._command_lock = threading.Lock()
        self._command_generation = 0
        self._applied_generation = -1
        self._worker_scheduled = False
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"rtsp-{camera.id}",
        )

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self.restart)
        self._state_event.connect(self._set_state)
        self._failure_event.connect(self._handle_failure)
        self._worker_done.connect(self._on_worker_done)

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def stream_url(self) -> str:
        return self._stream_url

    def bind_video_output(self) -> None:
        window_id = int(self.video_widget.winId())
        with self._command_lock:
            if self._window_id == window_id:
                return
            self._window_id = window_id
            self._command_generation += 1
        self._schedule_reconcile()

    def update_video_geometry(self) -> None:
        if not self.settings.stretch_video_to_tile:
            aspect_ratio = None
        else:
            width = max(1, self.video_widget.width())
            height = max(1, self.video_widget.height())
            divisor = gcd(width, height)
            aspect_ratio = f"{width // divisor}:{height // divisor}"

        with self._command_lock:
            if self._aspect_ratio == aspect_ratio:
                return
            self._aspect_ratio = aspect_ratio
            self._command_generation += 1
        self._schedule_reconcile()

    def set_grid_stream(self, use_grid_stream: bool) -> None:
        use_grid_stream = bool(use_grid_stream and self.settings.use_grid_substream)
        target_url = self.camera.stream_url(use_grid_stream)
        with self._command_lock:
            if target_url == self._stream_url:
                self._use_grid_stream = use_grid_stream
                return
            self._use_grid_stream = use_grid_stream
            self._stream_url = target_url
            self._command_generation += 1
        LOGGER.info(
            "%s: switching to %s stream",
            self.camera.name,
            "grid/sub" if use_grid_stream and self.camera.grid_rtsp_url else "main",
        )
        self._schedule_reconcile()

    def set_active(self, active: bool) -> None:
        if self._closing or not self.camera.enabled:
            active = False
        with self._command_lock:
            if self._active == active:
                return
            self._active = active
            self._command_generation += 1
        if not active:
            self._reconnect_timer.stop()
        self._schedule_reconcile()

    def start(self) -> None:
        self.set_active(True)

    def stop(self) -> None:
        self.restart()

    def restart(self) -> None:
        if self._closing or not self._active:
            return
        with self._command_lock:
            self._restart_serial += 1
            self._command_generation += 1
        self._schedule_reconcile()

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._reconnect_timer.stop()
        with self._command_lock:
            self._active = False
            self._command_generation += 1
        self._schedule_reconcile()
        self._executor.shutdown(wait=False, cancel_futures=False)

    def _schedule_reconcile(self) -> None:
        with self._command_lock:
            if self._released or self._worker_scheduled:
                return
            self._worker_scheduled = True
        try:
            future = self._executor.submit(self._reconcile_blocking)
        except RuntimeError:
            with self._command_lock:
                self._worker_scheduled = False
            return
        future.add_done_callback(self._emit_worker_done)

    def _emit_worker_done(self, future: Future[None]) -> None:
        error = future.exception()
        if self._closing:
            with self._command_lock:
                self._worker_scheduled = False
            return
        self._worker_done.emit(error)

    def _on_worker_done(self, error: object) -> None:
        if error is not None:
            LOGGER.error("Camera worker failed for %s: %s", self.camera.name, error)
            if not self._closing:
                self._failure_event.emit(str(error))

        with self._command_lock:
            self._worker_scheduled = False
            needs_more_work = (
                not self._released
                and self._command_generation != self._applied_generation
            )
        if needs_more_work:
            self._schedule_reconcile()

    def _snapshot_command(self) -> tuple[int, bool, bool, str, int | None, str | None, int]:
        with self._command_lock:
            return (
                self._command_generation,
                self._closing,
                self._active,
                self._stream_url,
                self._window_id,
                self._aspect_ratio,
                self._restart_serial,
            )

    def _mark_applied(self, generation: int) -> bool:
        with self._command_lock:
            self._applied_generation = generation
            return self._command_generation == generation

    def _reconcile_blocking(self) -> None:
        while True:
            (
                generation,
                closing,
                desired_active,
                desired_url,
                window_id,
                aspect_ratio,
                restart_serial,
            ) = self._snapshot_command()

            try:
                if closing:
                    self._release_blocking()
                    self._mark_applied(generation)
                    return

                if desired_active:
                    self._ensure_player_blocking()
                    self._apply_video_output_blocking(window_id, aspect_ratio)
                    needs_restart = (
                        not self._playing
                        or self._applied_url != desired_url
                        or self._applied_restart_serial != restart_serial
                    )
                    if needs_restart:
                        if self._playing:
                            self._stop_blocking()
                        self._start_blocking(desired_url)
                        self._applied_restart_serial = restart_serial
                elif self._playing:
                    self._stop_blocking()
            except Exception as exc:
                LOGGER.exception("Camera pipeline failed for %s", self.camera.name)
                self._playing = False
                self._applied_url = ""
                self._mark_applied(generation)
                self._failure_event.emit(str(exc))
                return

            if self._mark_applied(generation):
                return

    def _ensure_player_blocking(self) -> None:
        if self.media_player is not None:
            return
        self.vlc_instance = self.engine_factory.create_instance(
            self.settings.decoder_threads_per_camera
        )
        self.media_player = self.vlc_instance.media_player_new()
        if self.media_player is None:
            raise RuntimeError("Could not create LibVLC media player")
        self.media_player.video_set_mouse_input(False)
        self.media_player.video_set_key_input(False)
        self._attach_events_blocking()
        LOGGER.info(
            "%s: isolated LibVLC pipeline ready on %s (%d decoder thread(s))",
            self.camera.name,
            threading.current_thread().name,
            self.settings.decoder_threads_per_camera,
        )

    def _attach_events_blocking(self) -> None:
        manager = self.media_player.event_manager()
        event_type = self.engine_factory.vlc.EventType
        manager.event_attach(event_type.MediaPlayerOpening, self._on_opening)
        manager.event_attach(event_type.MediaPlayerBuffering, self._on_buffering)
        manager.event_attach(event_type.MediaPlayerPlaying, self._on_playing)
        manager.event_attach(event_type.MediaPlayerEncounteredError, self._on_error)
        manager.event_attach(event_type.MediaPlayerEndReached, self._on_end)

    def _apply_video_output_blocking(
        self,
        window_id: int | None,
        aspect_ratio: str | None,
    ) -> None:
        if self.media_player is None:
            return
        if window_id is not None:
            if sys.platform == "win32":
                self.media_player.set_hwnd(window_id)
            elif sys.platform.startswith("linux"):
                self.media_player.set_xwindow(window_id)
            elif sys.platform == "darwin":
                self.media_player.set_nsobject(window_id)
        self.media_player.video_set_aspect_ratio(aspect_ratio)

    def _start_blocking(self, stream_url: str) -> None:
        if not stream_url or self.media_player is None or self.vlc_instance is None:
            return
        self._state_event.emit("connecting")
        media = self.vlc_instance.media_new(stream_url)
        media.add_option(":no-audio")
        media.add_option(f":network-caching={self.settings.network_caching_ms}")
        media.add_option(f":live-caching={self.settings.network_caching_ms}")
        media.add_option(f":rtsp-caching={self.settings.network_caching_ms}")
        if self.settings.rtsp_transport == "tcp":
            media.add_option(":rtsp-tcp")
        self.media_player.set_media(media)
        media.release()
        result = self.media_player.play()
        if result == -1:
            self._playing = False
            self._applied_url = ""
            raise RuntimeError("LibVLC rejected the RTSP stream")
        self._playing = True
        self._applied_url = stream_url

    def _stop_blocking(self) -> None:
        if self.media_player is None:
            self._playing = False
            self._applied_url = ""
            return
        try:
            self.media_player.stop()
        finally:
            self._playing = False
            self._applied_url = ""
            if not self._closing:
                self._state_event.emit("offline")

    def _release_blocking(self) -> None:
        if self._released:
            return
        try:
            if self._playing:
                self._stop_blocking()
            if self.media_player is not None:
                self.media_player.release()
                self.media_player = None
            if self.vlc_instance is not None:
                self.vlc_instance.release()
                self.vlc_instance = None
        finally:
            self._released = True

    def _on_opening(self, _event: Any) -> None:
        if not self._closing:
            self._state_event.emit("connecting")

    def _on_buffering(self, _event: Any) -> None:
        if not self._closing and self._last_state != "online":
            self._state_event.emit("connecting")

    def _on_playing(self, _event: Any) -> None:
        if not self._closing:
            self._state_event.emit("online")

    def _on_error(self, _event: Any) -> None:
        if not self._closing:
            self._failure_event.emit("RTSP connection failed")

    def _on_end(self, _event: Any) -> None:
        if not self._closing:
            self._failure_event.emit("RTSP stream ended")

    def _handle_failure(self, message: str) -> None:
        LOGGER.warning("%s: %s", self.camera.name, message)
        self._set_state("offline")
        self.error_message.emit(message)
        if self._active and self.settings.auto_reconnect and not self._closing:
            self._reconnect_timer.start(self.settings.reconnect_interval_seconds * 1000)

    def _set_state(self, state: str) -> None:
        if state == self._last_state:
            return
        self._last_state = state
        self.state_changed.emit(state)
