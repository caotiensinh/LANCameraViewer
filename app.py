from camera_viewer.realtime_frame_shedding import install_realtime_frame_shedding

# Install the realtime-first decoder policy before MainWindow creates players.
install_realtime_frame_shedding()

from camera_viewer.application import run  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(run())
