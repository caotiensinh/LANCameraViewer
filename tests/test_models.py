from camera_viewer.models import AppConfig, CameraConfig, LAYOUT_DIMENSIONS, ViewerSettings


def test_layout_capacities():
    assert LAYOUT_DIMENSIONS["1x1"] == (1, 1)
    assert LAYOUT_DIMENSIONS["1x2"] == (1, 2)
    assert LAYOUT_DIMENSIONS["2x2"] == (2, 2)
    assert LAYOUT_DIMENSIONS["3x3"] == (3, 3)
    assert LAYOUT_DIMENSIONS["4x4"] == (4, 4)


def test_invalid_settings_are_normalized():
    settings = ViewerSettings.from_dict(
        {
            "default_layout": "9x9",
            "network_caching_ms": 1,
            "rtsp_transport": "invalid",
            "reconnect_interval_seconds": 0,
            "decoder_threads_per_camera": 99,
            "adaptive_sample_interval_ms": 1,
            "adaptive_cache_min_ms": 10,
            "adaptive_cache_max_ms": 20,
        }
    )
    assert settings.default_layout == "2x2"
    assert settings.network_caching_ms == 100
    assert settings.rtsp_transport == "tcp"
    assert settings.reconnect_interval_seconds == 2
    assert settings.stretch_video_to_tile is True
    assert settings.use_grid_substream is True
    assert settings.decoder_threads_per_camera == 4
    assert settings.adaptive_realtime is True
    assert settings.adaptive_sample_interval_ms == 750
    assert settings.adaptive_cache_min_ms == 80
    assert settings.adaptive_cache_max_ms == 80


def test_decoder_threads_default_to_one_per_camera():
    settings = ViewerSettings.from_dict({})
    assert settings.decoder_threads_per_camera == 1


def test_adaptive_realtime_defaults_prioritize_live_playback():
    settings = ViewerSettings.from_dict({})
    assert settings.adaptive_realtime is True
    assert settings.adaptive_cache_min_ms <= settings.network_caching_ms
    assert settings.adaptive_cache_max_ms <= 350
    assert settings.adaptive_bad_samples_before_switch >= 2


def test_camera_uses_grid_substream_when_configured():
    camera = CameraConfig(
        id="camera-01",
        name="Front",
        rtsp_url="rtsp://192.168.1.10/main",
        grid_rtsp_url="rtsp://192.168.1.10/sub",
    )
    assert camera.stream_url(False) == "rtsp://192.168.1.10/main"
    assert camera.stream_url(True) == "rtsp://192.168.1.10/sub"


def test_camera_falls_back_to_main_stream():
    camera = CameraConfig(
        id="camera-01",
        name="Front",
        rtsp_url="rtsp://192.168.1.10/main",
    )
    assert camera.stream_url(True) == "rtsp://192.168.1.10/main"


def test_app_config_roundtrip():
    raw = {
        "version": 1,
        "settings": {
            "default_layout": "1x2",
            "decoder_threads_per_camera": 2,
            "adaptive_realtime": True,
        },
        "cameras": [
            {
                "id": "camera-01",
                "name": "Front",
                "rtsp_url": "rtsp://192.168.1.10/stream1",
                "grid_rtsp_url": "rtsp://192.168.1.10/stream2",
                "enabled": True,
            }
        ],
    }
    config = AppConfig.from_dict(raw)
    output = config.to_dict()
    assert output["cameras"][0]["name"] == "Front"
    assert output["cameras"][0]["grid_rtsp_url"].endswith("/stream2")
    assert output["settings"]["decoder_threads_per_camera"] == 2
    assert output["settings"]["adaptive_realtime"] is True


def test_video_stretch_can_be_disabled():
    settings = ViewerSettings.from_dict({"stretch_video_to_tile": False})
    assert settings.stretch_video_to_tile is False
