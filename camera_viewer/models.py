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

    @classmethod
    def create(cls, name: str, rtsp_url: str, enabled: bool = True) -> "CameraConfig":
        return cls(
            id=f"camera-{uuid4().hex[:10]}",
            name=name.strip(),
            rtsp_url=rtsp_url.strip(),
            enabled=enabled,
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CameraConfig":
        return cls(
            id=str(raw.get("id") or f"camera-{uuid4().hex[:10]}"),
            name=str(raw.get("name") or "Camera").strip(),
            rtsp_url=str(raw.get("rtsp_url") or "").strip(),
            enabled=bool(raw.get("enabled", True)),
        )

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

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ViewerSettings":
        layout = str(raw.get("default_layout", "2x2"))
        if layout not in VALID_LAYOUTS:
            layout = "2x2"

        transport = str(raw.get("rtsp_transport", "tcp")).lower()
        if transport not in {"tcp", "udp"}:
            transport = "tcp"

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
