from __future__ import annotations

import json
import shutil
from pathlib import Path

from .models import AppConfig


class ConfigError(RuntimeError):
    pass


class ConfigService:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> AppConfig:
        if not self.path.exists():
            config = AppConfig()
            self.save(config)
            return config

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return AppConfig.from_dict(raw)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
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
        except OSError as exc:
            temporary_path.unlink(missing_ok=True)
            raise ConfigError(f"Cannot save configuration: {self.path}") from exc
