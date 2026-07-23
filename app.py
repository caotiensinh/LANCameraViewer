from camera_viewer.stable_vlc_runtime import install_stable_vlc_runtime

# Patch the VLC/player classes before MainWindow creates any camera pipeline.
install_stable_vlc_runtime()

from camera_viewer.application import run  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(run())
