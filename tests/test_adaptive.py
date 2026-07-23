from camera_viewer.adaptive import (
    AdaptiveRealtimeController,
    CameraTelemetry,
    SystemTelemetry,
)


def camera_sample(
    *,
    camera_id: str = "camera-01",
    state: str = "online",
    has_substream: bool = True,
    loss_ratio: float = 0.0,
    buffering_events: int = 0,
    discontinuities: int = 0,
    displayed_fps: float = 20.0,
    input_mbps: float = 1.0,
) -> CameraTelemetry:
    return CameraTelemetry(
        camera_id=camera_id,
        camera_name=camera_id,
        state=state,
        stream_kind="main",
        has_substream=has_substream,
        input_mbps=input_mbps,
        displayed_fps=displayed_fps,
        loss_ratio=loss_ratio,
        discontinuities=discontinuities,
        corrupted_packets=0,
        buffering_events=buffering_events,
        sampled_at=0.0,
    )


def system_sample(
    *,
    cpu: float = 20.0,
    memory: float = 30.0,
    rx_mbps: float = 10.0,
    nic_mbps: float = 1000.0,
    logical_cpus: int = 8,
    total_memory_gb: float = 16.0,
) -> SystemTelemetry:
    return SystemTelemetry(
        cpu_percent=cpu,
        memory_percent=memory,
        process_memory_mb=100.0,
        network_rx_mbps=rx_mbps,
        nic_speed_mbps=nic_mbps,
        logical_cpus=logical_cpus,
        total_memory_gb=total_memory_gb,
    )


def test_unstable_camera_switches_to_substream_after_hysteresis():
    controller = AdaptiveRealtimeController(
        min_switch_seconds=0,
        bad_samples_before_switch=2,
        recovery_samples=2,
    )

    controller.update_camera(camera_sample(loss_ratio=0.10))
    decision = controller.evaluate(
        system=system_sample(),
        visible_camera_ids={"camera-01"},
        base_cache_ms=250,
    )
    assert "camera-01" not in decision.force_substream_ids

    controller.update_camera(camera_sample(loss_ratio=0.10))
    decision = controller.evaluate(
        system=system_sample(),
        visible_camera_ids={"camera-01"},
        base_cache_ms=250,
    )
    assert "camera-01" in decision.force_substream_ids
    assert decision.level == "warning"


def test_camera_recovers_to_main_profile_after_stable_samples():
    controller = AdaptiveRealtimeController(
        min_switch_seconds=0,
        bad_samples_before_switch=2,
        recovery_samples=2,
    )

    for _ in range(2):
        controller.update_camera(camera_sample(loss_ratio=0.10))
        controller.evaluate(
            system=system_sample(),
            visible_camera_ids={"camera-01"},
            base_cache_ms=250,
        )

    for _ in range(2):
        controller.update_camera(camera_sample())
        decision = controller.evaluate(
            system=system_sample(),
            visible_camera_ids={"camera-01"},
            base_cache_ms=250,
        )

    assert "camera-01" not in decision.force_substream_ids
    assert decision.level == "healthy"


def test_critical_cpu_forces_realtime_profile_and_low_cache_immediately():
    controller = AdaptiveRealtimeController(
        min_switch_seconds=0,
        bad_samples_before_switch=3,
        recovery_samples=2,
    )

    controller.update_camera(camera_sample())
    decision = controller.evaluate(
        system=system_sample(
            cpu=90.0,
            logical_cpus=4,
            total_memory_gb=8.0,
        ),
        visible_camera_ids={"camera-01"},
        base_cache_ms=250,
    )

    assert "camera-01" in decision.force_substream_ids
    assert decision.cache_ms_by_camera["camera-01"] <= 160
    assert decision.level == "critical"


def test_transient_rebuffer_does_not_restart_cache_profile():
    controller = AdaptiveRealtimeController(
        min_switch_seconds=0,
        bad_samples_before_switch=3,
        recovery_samples=2,
    )

    controller.update_camera(camera_sample(buffering_events=1))
    decision = controller.evaluate(
        system=system_sample(),
        visible_camera_ids={"camera-01"},
        base_cache_ms=200,
    )

    assert decision.cache_ms_by_camera["camera-01"] == 200

    for _ in range(2):
        controller.update_camera(camera_sample(buffering_events=1))
        decision = controller.evaluate(
            system=system_sample(),
            visible_camera_ids={"camera-01"},
            base_cache_ms=200,
        )

    assert decision.cache_ms_by_camera["camera-01"] >= 240


def test_vbr_bitrate_changes_alone_are_not_treated_as_jitter():
    controller = AdaptiveRealtimeController(
        min_switch_seconds=0,
        bad_samples_before_switch=2,
        recovery_samples=2,
    )

    for bitrate in (0.4, 4.0, 0.5, 5.0, 0.6):
        controller.update_camera(camera_sample(input_mbps=bitrate, displayed_fps=20.0))
        decision = controller.evaluate(
            system=system_sample(),
            visible_camera_ids={"camera-01"},
            base_cache_ms=250,
        )

    assert decision.level == "healthy"
    assert "camera-01" not in decision.force_substream_ids


def test_missing_substream_is_reported_in_warning():
    controller = AdaptiveRealtimeController(
        min_switch_seconds=0,
        bad_samples_before_switch=2,
        recovery_samples=2,
    )

    for _ in range(2):
        controller.update_camera(
            camera_sample(has_substream=False, buffering_events=1)
        )
        decision = controller.evaluate(
            system=system_sample(),
            visible_camera_ids={"camera-01"},
            base_cache_ms=250,
        )

    assert "camera-01" not in decision.force_substream_ids
    assert "no substream" in decision.warning
