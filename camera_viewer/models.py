from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4


VALID_LAYOUTS = ("1x1", "1x2", "2x2", "3x3", "4x4")
LAYOUT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "1x1": (1, 1),
    "1x2": (1, 2),
    "2x2": (2, 2),
    "3x3": (3, 3),
    "4x4": (4, 4),
}


@dataclass(slots=True)
class CameraConfig:
    id: str
    name: str
    rtsp_url: str
    enabled: bool = True
    grid_rtsp_url: str = ""

    @classmethod
    def create(
        cls,
        name: str,
        rtsp_url: str,
        enabled: bool = True,
        grid_rtsp_url: str = "",
    ) -> "CameraConfig":
        return cls(
            id=f"camera-{uuid4().hex[:10]}",
            name=name.strip(),
            rtsp_url=rtsp_url.strip(),
            enabled=enabled,
            grid_rtsp_url=grid_rtsp_url.strip(),
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CameraConfig":
        return cls(
            id=str(raw.get("id") or f"camera-{uuid4().hex[:10]}"),
            name=str(raw.get("name") or "Camera").strip(),
            rtsp_url=str(raw.get("rtsp_url") or "").strip(),
            enabled=bool(raw.get("enabled", True)),
            grid_rtsp_url=str(raw.get("grid_rtsp_url") or "").strip(),
        )

    def stream_url(self, use_grid_stream: bool) -> str:
        if use_grid_stream and self.grid_rtsp_url:
            return self.grid_rtsp_url
        return self.rtsp_url

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ViewerSettings:
    default_layout: str = "2x2"
    network_caching_ms: int = 250
    rtsp_transport: str = "tcp"
    auto_reconnect: bool = True
    reconnect_interval_seconds: int = 5
    overlay_hide_ms: int = 2200
    keep_hidden_streams_alive: bool = False
    stretch_video_to_tile: bool = True
    use_grid_substream: bool = True
    decoder_threads_per_camera: int = 1

    adaptive_realtime: bool = True
    adaptive_sample_interval_ms: int = 1500
    adaptive_cpu_high_percent: int = 78
    adaptive_cpu_critical_percent: int = 92
    adaptive_memory_high_percent: int = 86
    adaptive_min_switch_seconds: int = 12
    adaptive_recovery_samples: int = 8
    adaptive_bad_samples_before_switch: int = 3
    adaptive_cache_min_ms: int = 100
    adaptive_cache_max_ms: int = 350

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ViewerSettings":
        layout = str(raw.get("default_layout", "2x2"))
        if layout not in VALID_LAYOUTS:
            layout = "2x2"

        transport = str(raw.get("rtsp_transport", "tcp")).lower()
        if transport not in {"tcp", "udp"}:
            transport = "tcp"

        cache_min = max(80, min(int(raw.get("adaptive_cache_min_ms", 100)), 500))
        cache_max = max(
            cache_min,
            min(int(raw.get("adaptive_cache_max_ms", 350)), 1500),
        )

        return cls(
            default_layout=layout,
            network_caching_ms=max(100, min(int(raw.get("network_caching_ms", 250)), 3000)),
            rtsp_transport=transport,
            auto_reconnect=bool(raw.get("auto_reconnect", True)),
            reconnect_interval_seconds=max(
                2, min(int(raw.get("reconnect_interval_seconds", 5)), 60)
            ),
            overlay_hide_ms=max(500, min(int(raw.get("overlay_hide_ms", 2200)), 10000)),
            keep_hidden_streams_alive=bool(raw.get("keep_hidden_streams_alive", False)),
            stretch_video_to_tile=bool(raw.get("stretch_video_to_tile", True)),
            use_grid_substream=bool(raw.get("use_grid_substream", True)),
            decoder_threads_per_camera=max(
                1, min(int(raw.get("decoder_threads_per_camera", 1)), 4)
            ),
            adaptive_realtime=bool(raw.get("adaptive_realtime", True)),
            adaptive_sample_interval_ms=max(
                750, min(int(raw.get("adaptive_sample_interval_ms", 1500)), 5000)
            ),
            adaptive_cpu_high_percent=max(
                50, min(int(raw.get("adaptive_cpu_high_percent", 78)), 95)
            ),
            adaptive_cpu_critical_percent=max(
                60, min(int(raw.get("adaptive_cpu_critical_percent", 92)), 100)
            ),
            adaptive_memory_high_percent=max(
                60, min(int(raw.get("adaptive_memory_high_percent", 86)), 98)
            ),
            adaptive_min_switch_seconds=max(
                5, min(int(raw.get("adaptive_min_switch_seconds", 12)), 120)
            ),
            adaptive_recovery_samples=max(
                3, min(int(raw.get("adaptive_recovery_samples", 8)), 60)
            ),
            adaptive_bad_samples_before_switch=max(
                2, min(int(raw.get("adaptive_bad_samples_before_switch", 3)), 20)
            ),
            adaptive_cache_min_ms=cache_min,
            adaptive_cache_max_ms=cache_max,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AppConfig:
    version: int = 1
    settings: ViewerSettings = field(default_factory=ViewerSettings)
    cameras: list[CameraConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AppConfig":
        settings = ViewerSettings.from_dict(raw.get("settings") or {})
        cameras = [CameraConfig.from_dict(item) for item in (raw.get("cameras") or [])]
        return cls(version=int(raw.get("version", 1)), settings=settings, cameras=cameras)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "settings": self.settings.to_dict(),
            "cameras": [camera.to_dict() for camera in self.cameras],
        }
