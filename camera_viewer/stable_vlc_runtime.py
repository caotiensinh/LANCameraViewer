from __future__ import annotations

import logging
import threading
from time import monotonic
from typing import Any

LOGGER = logging.getLogger(__name__)
_INSTALLED = False


def stable_cache_ms(value: int) -> int:
    """Keep LAN RTSP latency bounded without constantly rebuilding players."""
    return max(120, min(int(value), 250))


def classify_stall(*, state: str, displayed_fps: float, input_mbps: float) -> str | None:
    """Return the likely cause only after the player reports no new pictures."""
    if state != "online" or displayed_fps >= 0.15:
        return None
    return "decoder" if input_mbps >= 0.05 else "network"


def install_stable_vlc_runtime() -> None:
    """Install a low-resource, no-flapping LibVLC policy before UI startup."""
    global _INSTALLED
    if _INSTALLED:
        return

    from . import player as player_module

    _patch_engine(player_module)
    _patch_player(player_module)

    # MainWindow must be imported only after VlcEngine/CameraPlayer are patched.
    from . import main_window as main_window_module

    _patch_main_window(main_window_module)
    _INSTALLED = True
    LOGGER.info("Stable shared-LibVLC runtime installed")


def _patch_engine(player_module: Any) -> None:
    def engine_init(self: Any) -> None:
        self.vlc = player_module.load_vlc()
        self._shared_instance = None
        self._shared_instance_lock = threading.Lock()

    def create_instance(self: Any, decoder_threads: int):
        with self._shared_instance_lock:
            if self._shared_instance is None:
                args = [
                    "--no-video-title-show",
                    "--no-osd",
                    "--no-spu",
                    "--no-audio",
                    "--avcodec-hw=any",
                    # Let VLC discard decoder work and pictures that are already late.
                    "--skip-frames",
                    "--drop-late-frames",
                    f"--avcodec-threads={max(1, min(int(decoder_threads), 2))}",
                    "--quiet",
                ]
                instance = self.vlc.Instance(*args)
                if instance is None:
                    raise RuntimeError("Could not create the shared LibVLC instance")
                self._shared_instance = instance
                LOGGER.info(
                    "Created one shared LibVLC runtime for all camera players "
                    "(hardware decode requested)"
                )
            return self._shared_instance

    player_module.VlcEngine.__init__ = engine_init
    player_module.VlcEngine.create_instance = create_instance


def _patch_player(player_module: Any) -> None:
    def ensure_player_blocking(self: Any) -> None:
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
            "%s: independent media player ready on shared LibVLC runtime (%s)",
            self.camera.name,
            threading.current_thread().name,
        )

    def set_runtime_cache(self: Any, _cache_ms: int) -> None:
        # Changing caching while playing requires a player restart. Adaptive cache
        # changes caused the 3-4 second black flashes, so caching is fixed per run.
        return

    def start_blocking(self: Any, stream_url: str, cache_ms: int) -> None:
        if not stream_url or self.media_player is None or self.vlc_instance is None:
            return

        requested_cache_ms = int(cache_ms)
        effective_cache_ms = stable_cache_ms(requested_cache_ms)
        self._state_event.emit("connecting")
        media = self.vlc_instance.media_new(stream_url)
        media.add_option(":no-audio")
        media.add_option(f":network-caching={effective_cache_ms}")
        media.add_option(f":live-caching={effective_cache_ms}")
        media.add_option(f":rtsp-caching={effective_cache_ms}")
        if self.settings.rtsp_transport == "tcp":
            media.add_option(":rtsp-tcp")

        self.media_player.set_media(media)
        if self._media is not None:
            self._media.release()
        self._media = media

        result = self.media_player.play()
        if result == -1:
            self._playing = False
            self._applied_url = ""
            raise RuntimeError("LibVLC rejected the RTSP stream")

        self._playing = True
        self._applied_url = stream_url
        # Store the requested value because the command reconciler compares against
        # _runtime_cache_ms. The effective VLC value is separately bounded above.
        self._applied_cache_ms = requested_cache_ms
        self._reset_stats_baseline()

    def release_blocking(self: Any) -> None:
        if self._released:
            return
        try:
            if self._playing:
                self._stop_blocking()
            elif self._media is not None:
                self._media.release()
                self._media = None
            if self.media_player is not None:
                self.media_player.release()
                self.media_player = None
            # The LibVLC instance is shared by all players. Do not release it here.
            self.vlc_instance = None
        finally:
            self._released = True

    player_module.CameraPlayer._ensure_player_blocking = ensure_player_blocking
    player_module.CameraPlayer.set_runtime_cache = set_runtime_cache
    player_module.CameraPlayer._start_blocking = start_blocking
    player_module.CameraPlayer._release_blocking = release_blocking


def _patch_main_window(main_window_module: Any) -> None:
    cls = main_window_module.MainWindow
    original_init = cls.__init__
    original_on_metrics = cls._on_camera_metrics

    def ensure_state(window: Any) -> None:
        if hasattr(window, "_stable_stall_streak"):
            return
        window._stable_stall_streak = {}
        window._stable_last_restart_at = {}
        window._stable_force_substream_ids = set()

    def show_warning(window: Any, text: str, level: str = "warning") -> None:
        window.realtime_warning.setText(f"REALTIME PROTECTION · {text}")
        window.realtime_warning.setProperty("level", level)
        window.realtime_warning.style().unpolish(window.realtime_warning)
        window.realtime_warning.style().polish(window.realtime_warning)
        window.realtime_warning.show()
        window.realtime_warning.raise_()

    def window_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        ensure_state(self)
        # Metrics every 1.5 seconds were unnecessarily aggressive on an N100.
        if self._adaptive_timer.interval() < 3000:
            self._adaptive_timer.setInterval(3000)
        LOGGER.info(
            "Low-resource policy active: static RTSP cache, shared VLC runtime, "
            "stall restart cooldown 60 seconds"
        )

    def apply_stream_policy(self: Any, tiles: list[Any] | None = None) -> None:
        ensure_state(self)
        target_tiles = tiles if tiles is not None else self._ordered_tiles()
        for tile in target_tiles:
            camera_id = tile.camera.id
            use_grid = (
                self._layout_prefers_grid
                or camera_id in self._adaptive_force_ids
                or camera_id in self._stable_force_substream_ids
            )
            tile.set_grid_stream(use_grid)
            # Do not change cache at runtime; it causes a visible stop/start.

    def apply_adaptive_decision(self: Any, decision: Any) -> None:
        ensure_state(self)
        active_ids = {
            tile.camera.id for tile in self.tiles.values() if tile.player.is_active
        }

        # Degradation is sticky for the current session. This prevents profile
        # oscillation between main/substream and eliminates periodic flashing.
        self._stable_force_substream_ids.update(
            set(decision.force_substream_ids) & active_ids
        )
        new_force = set(self._stable_force_substream_ids) & active_ids
        changed = new_force != self._adaptive_force_ids
        self._adaptive_force_ids = new_force
        self._adaptive_cache_by_id.clear()
        if changed:
            self._apply_stream_policy()

        warning_parts: list[str] = []
        if decision.warning:
            warning_parts.append(str(decision.warning))

        if self._layout_prefers_grid:
            missing_substreams = [
                tile.camera.name
                for tile in self.tiles.values()
                if tile.player.is_active and not tile.camera.grid_rtsp_url
            ]
            if missing_substreams:
                warning_parts.append(
                    f"{len(missing_substreams)} camera(s) have no low-FPS substream"
                )

        if warning_parts:
            show_warning(
                self,
                " · ".join(warning_parts),
                "critical" if decision.level == "critical" else "warning",
            )
        else:
            self.realtime_warning.hide()

    def on_camera_metrics(self: Any, sample: Any) -> None:
        ensure_state(self)
        original_on_metrics(self, sample)

        camera_id = sample.camera_id
        stall = classify_stall(
            state=str(sample.state),
            displayed_fps=float(sample.displayed_fps),
            input_mbps=float(sample.input_mbps),
        )
        if stall is None:
            self._stable_stall_streak[camera_id] = 0
            return

        streak = int(self._stable_stall_streak.get(camera_id, 0)) + 1
        self._stable_stall_streak[camera_id] = streak
        # At the enforced 3-second sample interval this is about 18 seconds.
        if streak < 6:
            return

        now = monotonic()
        if now - float(self._stable_last_restart_at.get(camera_id, 0.0)) < 60.0:
            return

        tile = self.tiles.get(camera_id)
        if tile is None or not tile.player.is_active:
            return

        self._stable_last_restart_at[camera_id] = now
        self._stable_stall_streak[camera_id] = 0

        if stall == "decoder" and tile.camera.grid_rtsp_url and not tile.player.uses_grid_stream:
            self._stable_force_substream_ids.add(camera_id)
            self._adaptive_force_ids.add(camera_id)
            self._apply_stream_policy([tile])
            show_warning(
                self,
                f"{sample.camera_name}: decoder overloaded; switched to substream",
                "critical",
            )
            LOGGER.warning(
                "%s: decoder stalled; switching once to configured substream",
                sample.camera_name,
            )
            return

        # No data, or even the substream is frozen: flush once, then wait at least
        # 60 seconds before another automatic restart.
        tile.player.restart()
        reason = "RTSP data stalled" if stall == "network" else "decoder stalled"
        show_warning(
            self,
            f"{sample.camera_name}: {reason}; reconnecting once",
            "critical",
        )
        LOGGER.warning("%s: %s; controlled restart", sample.camera_name, reason)

    cls.__init__ = window_init
    cls._apply_stream_policy = apply_stream_policy
    cls._apply_adaptive_decision = apply_adaptive_decision
    cls._on_camera_metrics = on_camera_metrics
