from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from time import monotonic
from typing import Iterable

import psutil


@dataclass(slots=True, frozen=True)
class CameraTelemetry:
    camera_id: str
    camera_name: str
    state: str
    stream_kind: str
    has_substream: bool
    input_mbps: float
    displayed_fps: float
    loss_ratio: float
    discontinuities: int
    corrupted_packets: int
    buffering_events: int
    sampled_at: float


@dataclass(slots=True, frozen=True)
class SystemTelemetry:
    cpu_percent: float
    memory_percent: float
    process_memory_mb: float
    network_rx_mbps: float
    nic_speed_mbps: float
    logical_cpus: int
    total_memory_gb: float


@dataclass(slots=True, frozen=True)
class AdaptiveDecision:
    level: str
    force_substream_ids: frozenset[str]
    cache_ms_by_camera: dict[str, int]
    warning: str
    system: SystemTelemetry


class SystemMonitor:
    """Samples local system load without blocking the UI thread."""

    def __init__(self) -> None:
        counters = psutil.net_io_counters(pernic=True)
        self._last_net_bytes = {
            name: int(value.bytes_recv) for name, value in counters.items()
        }
        self._last_net_time = monotonic()
        psutil.cpu_percent(interval=None)
        self._process = psutil.Process()

    @staticmethod
    def _nic_speeds() -> dict[str, float]:
        return {
            name: float(stats.speed)
            for name, stats in psutil.net_if_stats().items()
            if stats.isup and stats.speed and stats.speed > 0
        }

    def sample(self) -> SystemTelemetry:
        now = monotonic()
        elapsed = max(0.2, now - self._last_net_time)
        counters = psutil.net_io_counters(pernic=True)
        speeds = self._nic_speeds()

        busiest_rx_mbps = 0.0
        busiest_speed_mbps = 0.0
        for name, value in counters.items():
            previous = self._last_net_bytes.get(name, int(value.bytes_recv))
            delta = max(0, int(value.bytes_recv) - previous)
            rx_mbps = delta * 8.0 / elapsed / 1_000_000.0
            speed_mbps = speeds.get(name, 0.0)
            if rx_mbps > busiest_rx_mbps:
                busiest_rx_mbps = rx_mbps
                busiest_speed_mbps = speed_mbps

        self._last_net_bytes = {
            name: int(value.bytes_recv) for name, value in counters.items()
        }
        self._last_net_time = now

        memory = psutil.virtual_memory()
        process_memory_mb = self._process.memory_info().rss / (1024.0 * 1024.0)
        return SystemTelemetry(
            cpu_percent=float(psutil.cpu_percent(interval=None)),
            memory_percent=float(memory.percent),
            process_memory_mb=process_memory_mb,
            network_rx_mbps=busiest_rx_mbps,
            nic_speed_mbps=busiest_speed_mbps,
            logical_cpus=int(psutil.cpu_count(logical=True) or 1),
            total_memory_gb=float(memory.total / (1024.0**3)),
        )


class AdaptiveRealtimeController:
    """Keeps playback close to live by sacrificing quality before latency."""

    def __init__(
        self,
        *,
        cpu_high_percent: int = 78,
        cpu_critical_percent: int = 92,
        memory_high_percent: int = 86,
        min_switch_seconds: int = 12,
        recovery_samples: int = 8,
        bad_samples_before_switch: int = 3,
        cache_min_ms: int = 100,
        cache_max_ms: int = 350,
    ) -> None:
        self.cpu_high_percent = cpu_high_percent
        self.cpu_critical_percent = cpu_critical_percent
        self.memory_high_percent = memory_high_percent
        self.min_switch_seconds = min_switch_seconds
        self.recovery_samples = recovery_samples
        self.bad_samples_before_switch = bad_samples_before_switch
        self.cache_min_ms = cache_min_ms
        self.cache_max_ms = cache_max_ms

        self._latest: dict[str, CameraTelemetry] = {}
        self._bitrate_history: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=8)
        )
        self._fps_history: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=8)
        )
        self._bad_streak: dict[str, int] = defaultdict(int)
        self._good_streak: dict[str, int] = defaultdict(int)
        self._forced_ids: set[str] = set()
        self._last_switch_at: dict[str, float] = defaultdict(lambda: 0.0)
        self._cache_ms_by_camera: dict[str, int] = {}
        self._last_cache_change_at: dict[str, float] = defaultdict(lambda: 0.0)
        self._global_bad_streak = 0
        self._global_good_streak = 0
        self._global_pressure = False

    def update_camera(self, sample: CameraTelemetry) -> None:
        self._latest[sample.camera_id] = sample
        if sample.input_mbps > 0:
            self._bitrate_history[sample.camera_id].append(sample.input_mbps)
        if sample.displayed_fps > 0:
            self._fps_history[sample.camera_id].append(sample.displayed_fps)

    @staticmethod
    def _coefficient_of_variation(values: Iterable[float]) -> float:
        data = [float(value) for value in values if value > 0]
        if len(data) < 4:
            return 0.0
        mean = sum(data) / len(data)
        if mean <= 0:
            return 0.0
        variance = sum((value - mean) ** 2 for value in data) / len(data)
        return variance**0.5 / mean

    def _camera_is_unhealthy(
        self,
        sample: CameraTelemetry,
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if sample.state == "offline":
            reasons.append("offline")
        elif sample.state == "connecting":
            reasons.append("buffering")

        if sample.loss_ratio >= 0.04:
            reasons.append("frame loss")
        if sample.discontinuities > 0 or sample.corrupted_packets > 0:
            reasons.append("stream discontinuity")
        if sample.buffering_events > 0:
            reasons.append("rebuffering")

        bitrate_jitter = self._coefficient_of_variation(
            self._bitrate_history[sample.camera_id]
        )
        fps_history = self._fps_history[sample.camera_id]
        fps_jitter = self._coefficient_of_variation(fps_history)
        if bitrate_jitter >= 0.45 or fps_jitter >= 0.35:
            reasons.append("estimated jitter")

        recent_fps = [value for value in fps_history if value > 0]
        if len(recent_fps) >= 4:
            normal_fps = max(recent_fps)
            if normal_fps >= 8.0 and sample.displayed_fps < normal_fps * 0.60:
                reasons.append("display FPS collapse")

        return bool(reasons), reasons

    def _select_cache(
        self,
        *,
        camera_id: str,
        reasons: list[str],
        base_cache_ms: int,
        critical_pressure: bool,
        now: float,
    ) -> int:
        current = self._cache_ms_by_camera.get(camera_id, base_cache_ms)
        desired = base_cache_ms

        if critical_pressure:
            desired = max(self.cache_min_ms, min(160, base_cache_ms))
        elif self._global_pressure:
            desired = max(self.cache_min_ms, min(180, base_cache_ms))
        elif "estimated jitter" in reasons or "rebuffering" in reasons:
            desired = min(self.cache_max_ms, max(240, base_cache_ms))

        can_change = (
            now - self._last_cache_change_at[camera_id] >= self.min_switch_seconds
        )
        sustained_bad = self._bad_streak[camera_id] >= self.bad_samples_before_switch
        sustained_good = self._good_streak[camera_id] >= self.recovery_samples

        should_change = False
        if critical_pressure and desired != current:
            should_change = True
        elif desired != base_cache_ms and sustained_bad and can_change:
            should_change = True
        elif desired == base_cache_ms and current != base_cache_ms and sustained_good and can_change:
            should_change = True

        if should_change:
            current = int(desired)
            self._last_cache_change_at[camera_id] = now

        self._cache_ms_by_camera[camera_id] = int(current)
        return int(current)

    def evaluate(
        self,
        *,
        system: SystemTelemetry,
        visible_camera_ids: set[str],
        base_cache_ms: int,
    ) -> AdaptiveDecision:
        now = monotonic()
        network_utilization = (
            system.network_rx_mbps / system.nic_speed_mbps
            if system.nic_speed_mbps > 0
            else 0.0
        )
        weak_hardware = system.logical_cpus <= 4 or system.total_memory_gb <= 8.5
        cpu_high_threshold = (
            min(self.cpu_high_percent, 72)
            if weak_hardware
            else self.cpu_high_percent
        )
        cpu_critical_threshold = (
            min(self.cpu_critical_percent, 88)
            if weak_hardware
            else self.cpu_critical_percent
        )
        memory_high_threshold = (
            min(self.memory_high_percent, 82)
            if weak_hardware
            else self.memory_high_percent
        )
        process_memory_limit_mb = max(
            1024.0,
            system.total_memory_gb * 1024.0 * 0.30,
        )
        process_memory_pressure = system.process_memory_mb >= process_memory_limit_mb
        resource_pressure = (
            system.cpu_percent >= cpu_high_threshold
            or system.memory_percent >= memory_high_threshold
            or process_memory_pressure
            or network_utilization >= 0.72
        )
        critical_pressure = system.cpu_percent >= cpu_critical_threshold

        if resource_pressure:
            self._global_bad_streak += 1
            self._global_good_streak = 0
        else:
            self._global_bad_streak = 0
            self._global_good_streak += 1

        # Critical CPU pressure is acted on immediately. Normal pressure still
        # requires consecutive samples so short spikes cannot cause flapping.
        if critical_pressure:
            self._global_bad_streak = max(
                self._global_bad_streak,
                self.bad_samples_before_switch,
            )

        if self._global_bad_streak >= self.bad_samples_before_switch:
            self._global_pressure = True
        elif self._global_good_streak >= self.recovery_samples:
            self._global_pressure = False

        reason_by_camera: dict[str, list[str]] = {}
        for camera_id in visible_camera_ids:
            sample = self._latest.get(camera_id)
            if sample is None:
                continue
            unhealthy, reasons = self._camera_is_unhealthy(sample)
            reason_by_camera[camera_id] = reasons
            if unhealthy:
                self._bad_streak[camera_id] += 1
                self._good_streak[camera_id] = 0
            else:
                self._bad_streak[camera_id] = 0
                self._good_streak[camera_id] += 1

            can_switch = now - self._last_switch_at[camera_id] >= self.min_switch_seconds
            if (
                self._bad_streak[camera_id] >= self.bad_samples_before_switch
                and sample.has_substream
                and can_switch
            ):
                self._forced_ids.add(camera_id)
                self._last_switch_at[camera_id] = now
            elif (
                camera_id in self._forced_ids
                and self._good_streak[camera_id] >= self.recovery_samples
                and not self._global_pressure
                and can_switch
            ):
                self._forced_ids.discard(camera_id)
                self._last_switch_at[camera_id] = now

        if self._global_pressure:
            for camera_id in visible_camera_ids:
                sample = self._latest.get(camera_id)
                if sample and sample.has_substream:
                    self._forced_ids.add(camera_id)

        self._forced_ids.intersection_update(visible_camera_ids)
        for camera_id in list(self._cache_ms_by_camera):
            if camera_id not in visible_camera_ids:
                self._cache_ms_by_camera.pop(camera_id, None)

        cache_by_camera = {
            camera_id: self._select_cache(
                camera_id=camera_id,
                reasons=reason_by_camera.get(camera_id, []),
                base_cache_ms=base_cache_ms,
                critical_pressure=critical_pressure,
                now=now,
            )
            for camera_id in visible_camera_ids
        }

        unhealthy_ids = [
            camera_id for camera_id, reasons in reason_by_camera.items() if reasons
        ]
        no_substream = [
            camera_id
            for camera_id in unhealthy_ids
            if self._latest.get(camera_id)
            and not self._latest[camera_id].has_substream
        ]

        if critical_pressure:
            level = "critical"
        elif self._global_pressure or unhealthy_ids or self._forced_ids:
            level = "warning"
        else:
            level = "healthy"

        warning_parts: list[str] = []
        if system.cpu_percent >= cpu_high_threshold:
            warning_parts.append(f"CPU {system.cpu_percent:.0f}%")
        if system.memory_percent >= memory_high_threshold:
            warning_parts.append(f"RAM {system.memory_percent:.0f}%")
        if process_memory_pressure:
            warning_parts.append(f"app RAM {system.process_memory_mb:.0f} MB")
        if network_utilization >= 0.72:
            warning_parts.append(
                f"LAN receive {system.network_rx_mbps:.1f}/"
                f"{system.nic_speed_mbps:.0f} Mbps"
            )
        if unhealthy_ids:
            warning_parts.append(f"{len(unhealthy_ids)} camera stream(s) unstable")
        if self._forced_ids:
            warning_parts.append(
                f"realtime profile on {len(self._forced_ids)} camera(s)"
            )
        if no_substream:
            warning_parts.append(
                f"{len(no_substream)} camera(s) have no substream"
            )

        warning = " · ".join(warning_parts)
        return AdaptiveDecision(
            level=level,
            force_substream_ids=frozenset(self._forced_ids),
            cache_ms_by_camera=cache_by_camera,
            warning=warning,
            system=system,
        )
