import json

from camera_viewer.config_service import ConfigService
from camera_viewer.models import AppConfig, CameraConfig


def test_save_and_load_config(tmp_path):
    path = tmp_path / "config" / "cameras.json"
    service = ConfigService(path)
    config = AppConfig(cameras=[CameraConfig.create("Cam", "rtsp://127.0.0.1/stream")])

    service.save(config)
    loaded = service.load()

    assert loaded.cameras[0].name == "Cam"
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


def test_existing_config_gets_backup(tmp_path):
    path = tmp_path / "cameras.json"
    service = ConfigService(path)
    service.save(AppConfig())
    service.save(AppConfig(cameras=[CameraConfig.create("Cam", "rtsp://camera")]))

    assert path.with_suffix(".json.bak").exists()
