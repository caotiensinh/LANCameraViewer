from types import SimpleNamespace

from camera_viewer.realtime_frame_shedding import (
    SKIP_BIDIR,
    SKIP_NONKEY,
    SKIP_NONREF,
    SKIP_NONE,
    choose_skip_level,
    stalled_stream_kind,
)


def test_main_stream_keeps_full_decode_when_healthy():
    assert (
        choose_skip_level(
            active=True,
            uses_grid_stream=False,
            adaptively_forced=False,
            critical_pressure=False,
            emergency_rescue=False,
        )
        == SKIP_NONE
    )


def test_grid_stream_drops_non_reference_frames():
    assert (
        choose_skip_level(
            active=True,
            uses_grid_stream=True,
            adaptively_forced=False,
            critical_pressure=False,
            emergency_rescue=False,
        )
        == SKIP_NONREF
    )


def test_critical_pressure_drops_bidirectional_frames():
    assert (
        choose_skip_level(
            active=True,
            uses_grid_stream=False,
            adaptively_forced=False,
            critical_pressure=True,
            emergency_rescue=False,
        )
        == SKIP_BIDIR
    )


def test_emergency_rescue_keeps_only_keyframes():
    assert (
        choose_skip_level(
            active=True,
            uses_grid_stream=False,
            adaptively_forced=False,
            critical_pressure=True,
            emergency_rescue=True,
        )
        == SKIP_NONKEY
    )


def test_inactive_camera_never_requests_decoder_work():
    assert (
        choose_skip_level(
            active=False,
            uses_grid_stream=True,
            adaptively_forced=True,
            critical_pressure=True,
            emergency_rescue=True,
        )
        == SKIP_NONE
    )


def test_online_data_without_displayed_frames_is_decoder_stall():
    sample = SimpleNamespace(
        state="online",
        input_mbps=1.4,
        displayed_fps=0.0,
    )
    assert stalled_stream_kind(sample) == "decoder"


def test_online_stream_without_data_is_network_stall():
    sample = SimpleNamespace(
        state="online",
        input_mbps=0.0,
        displayed_fps=0.0,
    )
    assert stalled_stream_kind(sample) == "network"


def test_low_but_live_keyframe_rate_is_not_classified_as_frozen():
    sample = SimpleNamespace(
        state="online",
        input_mbps=0.8,
        displayed_fps=0.5,
    )
    assert stalled_stream_kind(sample) is None
