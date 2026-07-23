from __future__ import annotations

import logging
from time import monotonic
from typing import Any

LOGGER = logging.getLogger(__name__)

_INSTALLED = False

SKIP_NONE = 0
SKIP_NONREF = 1
SKIP_BIDIR = 2
SKIP_NONKEY = 3


def choose_skip_level(
    *,
    active: bool,
    uses_grid_stream: bool,
    adaptively_forced: bool,
    critical_pressure: bool,
    emergency_rescue: bool,
) -> int:
    """Choose VLC/FFmpeg decoder discard level.

    VLC maps avcodec-skip-frame values as:
    0=default, 1=non-reference, 2=bidirectional, 3=non-key frames.
    """
    if not active:
        return SKIP_NONE
    if emergency_rescue:
        return SKIP_NONKEY
    if critical_pressure:
        return SKIP_BIDIR
    if uses_grid_stream or adaptively_forced:
        return SKIP_NONREF
    return SKIP_NONE


def stalled_stream_kind(sample: Any) -> str | None:
    """Classify a stream that receives no newly displayed frame."""
    if getattr(sample, "state", "") != "online":
        return None
    if float(getattr(sample, "displayed_fps", 0.0) or 0.0) >= 0.15:
        return None
    if float(getattr(sample, "input_mbps", 0.0) or 0.0) >= 0.02:
        return "decoder"
    return "network"


def install_realtime_frame_shedding() -> None:
    """Install the realtime-first frame shedding policy before app startup."""
    global _INSTALLED
    if _INSTALLED:
        return

    from . import adaptive as adaptive_module
    from . import player as player_module

    _patch_player(player_module)
    _patch_adaptive_controller(adaptive_module)

    # Import after patching player so MainWindow receives the patched classes.
    from . import main_window as main_window_module

    _patch_main_window(main_window_module)
    _INSTALLED = True
    LOGGER.info("Realtime frame shedding policy installed")


def _patch_player(player_module: Any) -> None:
    def create_instance(self: Any, decoder_threads: int):
        args = [
            "--no-video-title-show",
            "--no-osd",
            "--no-spu",
            "--no-audio",
            "--avcodec-hw=any",
            # Realtime-first: let VLC discard decoder work when frames are late.
            "--skip-frames",
            "--drop-late-frames",
            f"--avcodec-threads={decoder_threads}",
            "--quiet",
        ]
        instance = self.vlc.Instance(*args)
        if instance is None:
            raise RuntimeError("Could not create LibVLC instance")
        return instance

    def set_frame_shedding(self: Any, level: int) -> None:
        level = max(SKIP_NONE, min(int(level), SKIP_NONKEY))
        with self._command_lock:
            current = int(getattr(self, "_runtime_skip_level", SKIP_NONE))
            if current == level:
                return
            self._runtime_skip_level = level
            self._restart_serial += 1
            self._command_generation += 1
        LOGGER.warning(
            "%s: decoder frame shedding level %d",
            self.camera.name,
            level,
        )
        self._schedule_reconcile()

    @property
    def frame_shedding_level(self: Any) -> int:
        return int(getattr(self, "_runtime_skip_level", SKIP_NONE))

    def start_blocking(self: Any, stream_url: str, cache_ms: int) -> None:
        if not stream_url or self.media_player is None or self.vlc_instance is None:
            return

        self._state_event.emit("connecting")
        media = self.vlc_instance.media_new(stream_url)
        media.add_option(":no-audio")
        media.add_option(f":network-caching={cache_ms}")
        media.add_option(f":live-caching={cache_ms}")
        media.add_option(f":rtsp-caching={cache_ms}")

        skip_level = int(getattr(self, "_runtime_skip_level", SKIP_NONE))
        media.add_option(f":avcodec-skip-frame={skip_level}")
        if skip_level > SKIP_NONE:
            # Skipping loop filtering saves decoder time without adding latency.
            media.add_option(
                f":avcodec-skiploopfilter={min(skip_level, SKIP_BIDIR)}"
            )

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
        self._applied_cache_ms = cache_ms
        self._reset_stats_baseline()

    player_module.VlcEngine.create_instance = create_instance
    player_module.CameraPlayer.set_frame_shedding = set_frame_shedding
    player_module.CameraPlayer.frame_shedding_level = frame_shedding_level
    player_module.CameraPlayer._start_blocking = start_blocking


def _patch_adaptive_controller(adaptive_module: Any) -> None:
    original = adaptive_module.AdaptiveRealtimeController._camera_is_unhealthy

    def camera_is_unhealthy(self: Any, sample: Any):
        _unhealthy, reasons = original(self, sample)
        stall = stalled_stream_kind(sample)
        if stall == "decoder" and "decoder freeze" not in reasons:
            reasons.append("decoder freeze")
        elif stall == "network" and "stream stalled" not in reasons:
            reasons.append("stream stalled")
        return bool(reasons), reasons

    adaptive_module.AdaptiveRealtimeController._camera_is_unhealthy = (
        camera_is_unhealthy
    )


def _patch_main_window(main_window_module: Any) -> None:
    cls = main_window_module.MainWindow
    original_apply_stream_policy = cls._apply_stream_policy
    original_apply_decision = cls._apply_adaptive_decision
    original_on_metrics = cls._on_camera_metrics

    def ensure_state(window: Any) -> None:
        if not hasattr(window, "_frame_stall_streak"):
            window._frame_stall_streak = {}
            window._frame_restart_at = {}
            window._frame_emergency_until = {}
            window._frame_shedding_critical = False

    def apply_stream_policy(self: Any, tiles: list[Any] | None = None) -> None:
        ensure_state(self)
        original_apply_stream_policy(self, tiles)

        now = monotonic()
        target_tiles = tiles if tiles is not None else self._ordered_tiles()
        for camera_id, expires_at in list(self._frame_emergency_until.items()):
            if expires_at <= now:
                self._frame_emergency_until.pop(camera_id, None)

        for tile in target_tiles:
            camera_id = tile.camera.id
            level = choose_skip_level(
                active=tile.player.is_active,
                uses_grid_stream=tile.player.uses_grid_stream,
                adaptively_forced=camera_id in self._adaptive_force_ids,
                critical_pressure=bool(self._frame_shedding_critical),
                emergency_rescue=(
                    self._frame_emergency_until.get(camera_id, 0.0) > now
                ),
            )
            tile.player.set_frame_shedding(level)

    def apply_adaptive_decision(self: Any, decision: Any) -> None:
        ensure_state(self)
        self._frame_shedding_critical = decision.level == "critical"
        original_apply_decision(self, decision)
        self._apply_stream_policy()

        now = monotonic()
        emergency_count = sum(
            1
            for camera_id, expires_at in self._frame_emergency_until.items()
            if expires_at > now
            and camera_id in self.tiles
            and self.tiles[camera_id].player.is_active
        )
        if emergency_count:
            prefix = self.realtime_warning.text().strip()
            rescue = f"keyframe rescue on {emergency_count} camera(s)"
            if prefix:
                if rescue not in prefix:
                    self.realtime_warning.setText(f"{prefix} · {rescue}")
            else:
                self.realtime_warning.setText(
                    f"REALTIME PROTECTION · {rescue}"
                )
            self.realtime_warning.setProperty("level", "critical")
            self.realtime_warning.style().unpolish(self.realtime_warning)
            self.realtime_warning.style().polish(self.realtime_warning)
            self.realtime_warning.show()
            self.realtime_warning.raise_()

    def on_camera_metrics(self: Any, sample: Any) -> None:
        ensure_state(self)
        original_on_metrics(self, sample)

        camera_id = sample.camera_id
        stall = stalled_stream_kind(sample)
        if stall is None:
            self._frame_stall_streak[camera_id] = 0
            return

        streak = int(self._frame_stall_streak.get(camera_id, 0)) + 1
        self._frame_stall_streak[camera_id] = streak
        if streak < 3:
            return

        now = monotonic()
        if now - float(self._frame_restart_at.get(camera_id, 0.0)) < 15.0:
            return

        tile = self.tiles.get(camera_id)
        if tile is None or not tile.player.is_active:
            return

        self._frame_restart_at[camera_id] = now
        self._frame_stall_streak[camera_id] = 0

        if stall == "decoder":
            # Decode only keyframes for 45 seconds, then retry normal policy.
            self._frame_emergency_until[camera_id] = now + 45.0
            LOGGER.warning(
                "%s: no displayed frames while data arrives; "
                "activating keyframe-only rescue",
                sample.camera_name,
            )
        else:
            LOGGER.warning(
                "%s: no RTSP data/frames; flushing the stale pipeline",
                sample.camera_name,
            )

        self._apply_stream_policy([tile])
        tile.player.restart()

        mode_text = (
            "decoder overloaded; keyframe rescue enabled"
            if stall == "decoder"
            else "RTSP stream stalled; reconnecting"
        )
        self.realtime_warning.setText(
            f"REALTIME PROTECTION · {sample.camera_name}: {mode_text}"
        )
        self.realtime_warning.setProperty("level", "critical")
        self.realtime_warning.style().unpolish(self.realtime_warning)
        self.realtime_warning.style().polish(self.realtime_warning)
        self.realtime_warning.show()
        self.realtime_warning.raise_()

    cls._apply_stream_policy = apply_stream_policy
    cls._apply_adaptive_decision = apply_adaptive_decision
    cls._on_camera_metrics = on_camera_metrics
