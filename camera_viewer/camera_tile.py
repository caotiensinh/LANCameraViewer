from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from .models import CameraConfig, ViewerSettings
from .player import CameraPlayer, VlcEngine


class CameraTile(QFrame):
    double_clicked = Signal(str)
    selected = Signal(str)
    user_activity = Signal()

    def __init__(
        self,
        engine: VlcEngine,
        camera: CameraConfig,
        settings: ViewerSettings,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.camera = camera
        self.settings = settings
        self._last_error = ""
        self.setObjectName("CameraTile")
        self.setProperty("focused", False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(120, 80)
        self.setMouseTracking(True)

        self.video_surface = QWidget(self)
        self.video_surface.setObjectName("VideoSurface")
        self.video_surface.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.video_surface.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.video_surface.setMouseTracking(True)
        self.video_surface.installEventFilter(self)

        self.overlay = QFrame(self)
        self.overlay.setObjectName("OverlayBar")
        self.overlay.setFixedHeight(34)
        overlay_layout = QHBoxLayout(self.overlay)
        overlay_layout.setContentsMargins(10, 0, 32, 0)
        self.name_label = QLabel(camera.name, self.overlay)
        self.name_label.setObjectName("CameraName")
        overlay_layout.addWidget(self.name_label)
        overlay_layout.addStretch(1)

        self.status_dot = QLabel(self)
        self.status_dot.setObjectName("StatusDot")
        self.status_dot.setToolTip("Offline")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self.video_surface)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.overlay.hide)

        self.player = CameraPlayer(engine, camera, settings, self.video_surface, self)
        self.player.state_changed.connect(self._on_state_changed)
        self.player.error_message.connect(self._on_error_message)

        self.overlay.hide()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.overlay.setGeometry(0, 0, self.width(), 34)
        self.status_dot.move(max(6, self.width() - 18), 13)
        player = getattr(self, "player", None)
        if player is not None:
            player.update_video_geometry()
        self.overlay.raise_()
        self.status_dot.raise_()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.player.bind_video_output()
        self.overlay.raise_()
        self.status_dot.raise_()

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        if watched is self.video_surface:
            if event.type() == QEvent.Type.MouseMove:
                self._show_overlay()
            elif event.type() == QEvent.Type.MouseButtonPress:
                mouse_event = event
                if isinstance(mouse_event, QMouseEvent) and mouse_event.button() == Qt.MouseButton.LeftButton:
                    self.selected.emit(self.camera.id)
                    self._show_overlay()
            elif event.type() == QEvent.Type.MouseButtonDblClick:
                self.double_clicked.emit(self.camera.id)
                return True
        return super().eventFilter(watched, event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._show_overlay()
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.camera.id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def set_grid_stream(self, use_grid_stream: bool) -> None:
        self.player.set_grid_stream(use_grid_stream)

    def set_stream_active(self, active: bool) -> None:
        self.player.set_active(active)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("focused", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def close_player(self) -> None:
        self.player.close()

    def _show_overlay(self) -> None:
        self.user_activity.emit()
        self.overlay.show()
        self.overlay.raise_()
        self.status_dot.raise_()
        self._hide_timer.start(self.settings.overlay_hide_ms)

    def _on_state_changed(self, state: str) -> None:
        if state == "online":
            color = "#43c768"
            tooltip = "Online"
            self._last_error = ""
        elif state == "connecting":
            color = "#747a80"
            tooltip = "Connecting"
        else:
            color = "#747a80"
            tooltip = self._last_error or "Offline"
        self.status_dot.setStyleSheet(
            f"min-width:8px;max-width:8px;min-height:8px;max-height:8px;"
            f"border-radius:4px;background-color:{color};"
        )
        self.status_dot.setToolTip(tooltip)

    def _on_error_message(self, message: str) -> None:
        self._last_error = message.strip() or "RTSP connection failed"
        self.status_dot.setToolTip(self._last_error)


class EmptyTile(QFrame):
    user_activity = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("CameraTile")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(80, 60)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self.user_activity.emit()
        super().mouseMoveEvent(event)
