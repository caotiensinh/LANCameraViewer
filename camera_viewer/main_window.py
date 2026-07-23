from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .camera_dialog import CameraSettingsDialog
from .camera_tile import CameraTile, EmptyTile
from .config_service import ConfigError, ConfigService
from .models import AppConfig, LAYOUT_DIMENSIONS, VALID_LAYOUTS
from .player import VlcEngine

LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, config_service: ConfigService):
        super().__init__()
        self.config_service = config_service
        self.config = self.config_service.load()
        self.engine = VlcEngine()

        self.current_layout = self.config.settings.default_layout
        self.previous_layout = self.current_layout
        self.selected_camera_id: str | None = None
        self.focus_camera_id: str | None = None
        self._was_maximized = False

        self._chrome_hide_timer = QTimer(self)
        self._chrome_hide_timer.setSingleShot(True)
        self._chrome_hide_timer.timeout.connect(self._hide_header_if_allowed)

        self.tiles: dict[str, CameraTile] = {}
        self.empty_tiles: list[EmptyTile] = []

        self.setWindowTitle("LAN Camera Viewer")
        self.resize(1280, 760)
        self.setMinimumSize(720, 420)

        self.central = QWidget(self)
        self.setCentralWidget(self.central)
        self.root_layout = QVBoxLayout(self.central)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self.header = self._build_header()
        self.grid_host = QWidget(self.central)
        self.grid_layout = QGridLayout(self.grid_host)
        # The video wall must touch the application edges. Individual tiles
        # provide their own overlays, so the grid itself needs no padding.
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setHorizontalSpacing(0)
        self.grid_layout.setVerticalSpacing(0)

        self.root_layout.addWidget(self.header)
        self.root_layout.addWidget(self.grid_host, 1)

        self._rebuild_tiles()
        self._apply_layout(self.current_layout)
        self._show_header_temporarily()

    def _build_header(self) -> QFrame:
        header = QFrame(self.central)
        header.setObjectName("HeaderBar")
        header.setFixedHeight(44)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(12, 7, 10, 7)
        layout.setSpacing(6)

        title = QLabel("LAN Camera Viewer", header)
        title.setObjectName("AppTitle")
        layout.addWidget(title)
        layout.addSpacing(12)

        self.layout_actions: dict[str, QAction] = {}
        action_group = QActionGroup(self)
        action_group.setExclusive(True)
        for layout_name in VALID_LAYOUTS:
            action = QAction(layout_name, self)
            action.setCheckable(True)
            action.setChecked(layout_name == self.current_layout)
            action.triggered.connect(
                lambda checked=False, name=layout_name: self._apply_layout(name)
            )
            action_group.addAction(action)
            self.layout_actions[layout_name] = action
            button = QToolButton(header)
            button.setDefaultAction(action)
            button.setFixedWidth(48)
            button.setFixedHeight(28)
            layout.addWidget(button)

        layout.addStretch(1)

        reconnect_button = QPushButton("↻", header)
        reconnect_button.setObjectName("IconButton")
        reconnect_button.setToolTip("Reconnect visible cameras")
        reconnect_button.clicked.connect(self._reconnect_visible)
        layout.addWidget(reconnect_button)

        settings_button = QPushButton("⚙", header)
        settings_button.setObjectName("IconButton")
        settings_button.setToolTip("Camera settings")
        settings_button.clicked.connect(self._open_camera_settings)
        layout.addWidget(settings_button)

        header.setMouseTracking(True)
        header.installEventFilter(self)
        for child in header.findChildren(QWidget):
            child.setMouseTracking(True)
            child.installEventFilter(self)

        return header

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        header = getattr(self, "header", None)
        if header is not None and (watched is header or header.isAncestorOf(watched)):
            if event.type() in {
                QEvent.Type.Enter,
                QEvent.Type.MouseMove,
                QEvent.Type.MouseButtonPress,
            }:
                self._show_header_temporarily()
        return super().eventFilter(watched, event)

    def _show_header_temporarily(self) -> None:
        if self.focus_camera_id:
            return
        self.header.show()
        self._chrome_hide_timer.start(self.config.settings.overlay_hide_ms)

    def _hide_header_if_allowed(self) -> None:
        if not self.focus_camera_id:
            self.header.hide()

    def _rebuild_tiles(self) -> None:
        for tile in self.tiles.values():
            tile.close_player()
            tile.setParent(None)
            tile.deleteLater()
        self.tiles.clear()

        enabled = [camera for camera in self.config.cameras if camera.enabled]
        for camera in enabled:
            tile = CameraTile(self.engine, camera, self.config.settings, self.grid_host)
            tile.double_clicked.connect(self._toggle_focus)
            tile.selected.connect(self._select_camera)
            tile.user_activity.connect(self._show_header_temporarily)
            self.tiles[camera.id] = tile

        if enabled and self.selected_camera_id not in self.tiles:
            self.selected_camera_id = enabled[0].id
        elif not enabled:
            self.selected_camera_id = None

    def _clear_grid(self) -> None:
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()

        for empty in self.empty_tiles:
            empty.setParent(None)
            empty.deleteLater()
        self.empty_tiles.clear()

    def _ordered_tiles(self) -> list[CameraTile]:
        order = {camera.id: index for index, camera in enumerate(self.config.cameras)}
        return sorted(self.tiles.values(), key=lambda tile: order.get(tile.camera.id, 9999))

    def _reset_grid_tracks(self) -> None:
        """Remove row/column sizing left behind by a larger layout.

        QGridLayout keeps stretch factors even after widgets are removed. Without
        resetting them, switching from 4x4 to 1x1 leaves sixteen equally sized
        logical cells and the single camera remains stuck in the top-left cell.
        """
        max_rows = max(rows for rows, _columns in LAYOUT_DIMENSIONS.values())
        max_columns = max(columns for _rows, columns in LAYOUT_DIMENSIONS.values())

        for row in range(max_rows):
            self.grid_layout.setRowStretch(row, 0)
            self.grid_layout.setRowMinimumHeight(row, 0)
        for column in range(max_columns):
            self.grid_layout.setColumnStretch(column, 0)
            self.grid_layout.setColumnMinimumWidth(column, 0)

    def _apply_layout(self, layout_name: str) -> None:
        if layout_name not in LAYOUT_DIMENSIONS:
            return

        self.current_layout = layout_name
        self.layout_actions[layout_name].setChecked(True)
        rows, columns = LAYOUT_DIMENSIONS[layout_name]
        capacity = rows * columns

        self._clear_grid()
        self._reset_grid_tracks()
        ordered = self._ordered_tiles()

        if layout_name == "1x1" and ordered:
            selected = self.tiles.get(self.selected_camera_id or "") or ordered[0]
            visible_tiles = [selected]
        else:
            visible_tiles = ordered[:capacity]

        visible_ids = {tile.camera.id for tile in visible_tiles}
        for index in range(capacity):
            row, column = divmod(index, columns)
            if index < len(visible_tiles):
                tile = visible_tiles[index]
                self.grid_layout.addWidget(tile, row, column)
                tile.show()
                tile.player.bind_video_output()
            else:
                empty = EmptyTile(self.grid_host)
                self.empty_tiles.append(empty)
                empty.user_activity.connect(self._show_header_temporarily)
                self.grid_layout.addWidget(empty, row, column)
                empty.show()

        for tile in ordered:
            should_stream = (
                tile.camera.id in visible_ids or self.config.settings.keep_hidden_streams_alive
            )
            tile.set_stream_active(should_stream)
            tile.set_selected(tile.camera.id == self.selected_camera_id)

        for row in range(rows):
            self.grid_layout.setRowStretch(row, 1)
        for column in range(columns):
            self.grid_layout.setColumnStretch(column, 1)

        # Force Qt to discard the previous geometry immediately. This makes
        # 1x1 fill the complete video area, 1x2 split it in half, and 2x2 use
        # four equal quadrants even after visiting 3x3 or 4x4.
        self.grid_layout.invalidate()
        self.grid_host.updateGeometry()

    def _select_camera(self, camera_id: str) -> None:
        self.selected_camera_id = camera_id
        for tile in self.tiles.values():
            tile.set_selected(tile.camera.id == camera_id)
        if self.current_layout == "1x1" and not self.focus_camera_id:
            self._apply_layout("1x1")

    def _toggle_focus(self, camera_id: str) -> None:
        if self.focus_camera_id:
            self._exit_focus()
        else:
            self._enter_focus(camera_id)

    def _enter_focus(self, camera_id: str) -> None:
        tile = self.tiles.get(camera_id)
        if not tile:
            return
        self.previous_layout = self.current_layout
        self.focus_camera_id = camera_id
        self.selected_camera_id = camera_id
        self._was_maximized = self.isMaximized()
        self._chrome_hide_timer.stop()
        self.header.hide()
        self._clear_grid()
        self._reset_grid_tracks()
        self.grid_layout.addWidget(tile, 0, 0)
        self.grid_layout.setRowStretch(0, 1)
        self.grid_layout.setColumnStretch(0, 1)
        tile.show()
        tile.player.bind_video_output()
        self.grid_layout.invalidate()
        self.grid_host.updateGeometry()

        for camera_tile in self.tiles.values():
            active = camera_tile.camera.id == camera_id or self.config.settings.keep_hidden_streams_alive
            camera_tile.set_stream_active(active)

        self.showFullScreen()

    def _exit_focus(self, restore_window: bool = True) -> None:
        if not self.focus_camera_id:
            return
        self.focus_camera_id = None
        self.header.show()
        self._show_header_temporarily()
        if restore_window:
            self.showNormal()
            if self._was_maximized:
                self.showMaximized()
        self._apply_layout(self.previous_layout)

    def _reconnect_visible(self) -> None:
        for tile in self.tiles.values():
            if tile.player.is_active:
                tile.player.stop()
                tile.player.set_active(False)
                tile.player.set_active(True)

    def _open_camera_settings(self) -> None:
        dialog = CameraSettingsDialog(self.config.cameras, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self.config.cameras = dialog.cameras
        try:
            self.config_service.save(self.config)
        except ConfigError as exc:
            QMessageBox.critical(self, "Configuration error", str(exc))
            return
        self._rebuild_tiles()
        self._apply_layout(self.current_layout)
        self._show_header_temporarily()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self.focus_camera_id:
            self._exit_focus()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F11:
            if self.isFullScreen() and not self.focus_camera_id:
                self.showNormal()
            elif not self.focus_camera_id:
                self.showFullScreen()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        for tile in self.tiles.values():
            tile.close_player()
        try:
            self.config.settings.default_layout = self.current_layout
            self.config_service.save(self.config)
        except Exception:
            LOGGER.exception("Could not save settings during shutdown")
        event.accept()
