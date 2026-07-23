import json
from pathlib import Path


def test_default_camera_addresses():
    path = Path(__file__).resolve().parents[1] / "config" / "cameras.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    urls = [camera["rtsp_url"] for camera in raw["cameras"]]
    assert urls == [
        "rtsp://192.168.11.124:554/stream1",
        "rtsp://192.168.11.125:554/stream1",
        "rtsp://192.168.11.126:554/stream1",
        "rtsp://192.168.11.127:554/stream1",
    ]
    assert raw["settings"]["rtsp_transport"] == "tcp"
    assert raw["settings"]["keep_hidden_streams_alive"] is False
