from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from .models import AppConfig

LOGGER = logging.getLogger(__name__)


class ConfigError(RuntimeError):
    pass


class ConfigService:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> AppConfig:
        if not self.path.exists():
            LOGGER.warning("Camera configuration does not exist; creating an empty file at %s", self.path)
            config = AppConfig()
            self.save(config)
            return config

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            config = AppConfig.from_dict(raw)
            LOGGER.info(
                "Loaded camera configuration from %s (%d camera(s))",
                self.path,
                len(config.cameras),
            )
            for camera in config.cameras:
                LOGGER.info(
                    "Configured camera: id=%s name=%s enabled=%s host=%s",
                    camera.id,
                    camera.name,
                    camera.enabled,
                    self._safe_host(camera.rtsp_url),
                )
            return config
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            LOGGER.exception("Cannot read camera configuration at %s", self.path)
            raise ConfigError(f"Cannot read configuration: {self.path}") from exc

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".json.tmp")
        backup_path = self.path.with_suffix(".json.bak")

        try:
            temporary_path.write_text(
                json.dumps(config.to_dict(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            if self.path.exists():
                shutil.copy2(self.path, backup_path)
            temporary_path.replace(self.path)
            LOGGER.info("Saved camera configuration to %s (%d camera(s))", self.path, len(config.cameras))
        except OSError as exc:
            temporary_path.unlink(missing_ok=True)
            LOGGER.exception("Cannot save camera configuration at %s", self.path)
            raise ConfigError(f"Cannot save configuration: {self.path}") from exc

    @staticmethod
    def _safe_host(url: str) -> str:
        try:
            from urllib.parse import urlsplit

            parsed = urlsplit(url)
            return parsed.hostname or "<missing-host>"
        except Exception:
            return "<invalid-url>"
