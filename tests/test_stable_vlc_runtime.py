from camera_viewer.stable_vlc_runtime import classify_stall, stable_cache_ms


def test_stable_cache_is_bounded():
    assert stable_cache_ms(10) == 120
    assert stable_cache_ms(180) == 180
    assert stable_cache_ms(3000) == 250


def test_active_stream_with_data_but_no_frames_is_decoder_stall():
    assert classify_stall(state="online", displayed_fps=0.0, input_mbps=2.0) == "decoder"


def test_active_stream_without_data_is_network_stall():
    assert classify_stall(state="online", displayed_fps=0.0, input_mbps=0.0) == "network"


def test_low_but_live_fps_is_not_stalled():
    assert classify_stall(state="online", displayed_fps=0.5, input_mbps=1.0) is None


def test_connecting_stream_is_not_classified_as_stalled():
    assert classify_stall(state="connecting", displayed_fps=0.0, input_mbps=0.0) is None
