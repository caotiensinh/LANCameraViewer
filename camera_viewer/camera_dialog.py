from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import CameraConfig


class CameraEditorDialog(QDialog):
    def __init__(self, camera: CameraConfig | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Camera")
        self.setMinimumWidth(520)
        self._camera = camera

        self.name_edit = QLineEdit(camera.name if camera else "")
        self.url_edit = QLineEdit(camera.rtsp_url if camera else "rtsp://")
        self.url_edit.setPlaceholderText("rtsp://user:password@192.168.11.124:554/stream1")
        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setChecked(camera.enabled if camera else True)

        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("RTSP URL", self.url_edit)
        form.addRow("", self.enabled_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def result_camera(self) -> CameraConfig:
        if self._camera:
            return CameraConfig(
                id=self._camera.id,
                name=self.name_edit.text().strip(),
                rtsp_url=self.url_edit.text().strip(),
                enabled=self.enabled_check.isChecked(),
            )
        return CameraConfig.create(
            name=self.name_edit.text().strip(),
            rtsp_url=self.url_edit.text().strip(),
            enabled=self.enabled_check.isChecked(),
        )

    def _validate_and_accept(self) -> None:
        name = self.name_edit.text().strip()
        url = self.url_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid camera", "Camera name is required.")
            return
        if not url.lower().startswith(("rtsp://", "rtsps://")):
            QMessageBox.warning(
                self,
                "Invalid RTSP URL",
                "The URL must start with rtsp:// or rtsps://, not http://.",
            )
            return
        self.accept()


class CameraSettingsDialog(QDialog):
    def __init__(self, cameras: list[CameraConfig], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Camera Settings")
        self.resize(820, 440)
        self.cameras = deepcopy(cameras)

        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(["Name", "RTSP URL", "Enabled"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(self._edit_camera)

        add_button = QPushButton("Add")
        edit_button = QPushButton("Edit")
        delete_button = QPushButton("Delete")
        add_button.clicked.connect(self._add_camera)
        edit_button.clicked.connect(self._edit_camera)
        delete_button.clicked.connect(self._delete_camera)

        action_layout = QHBoxLayout()
        action_layout.addWidget(add_button)
        action_layout.addWidget(edit_button)
        action_layout.addWidget(delete_button)
        action_layout.addStretch(1)

        hint = QLabel("Camera IP addresses and passwords are stored in config/cameras.json.")
        hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(action_layout)
        layout.addWidget(hint)
        layout.addWidget(buttons)

        self._refresh_table()

    def _selected_row(self) -> int:
        indexes = self.table.selectionModel().selectedRows()
        return indexes[0].row() if indexes else -1

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.cameras))
        for row, camera in enumerate(self.cameras):
            self.table.setItem(row, 0, QTableWidgetItem(camera.name))
            self.table.setItem(row, 1, QTableWidgetItem(camera.rtsp_url))
            self.table.setItem(row, 2, QTableWidgetItem("Yes" if camera.enabled else "No"))

    def _add_camera(self) -> None:
        editor = CameraEditorDialog(parent=self)
        if editor.exec() == QDialog.DialogCode.Accepted:
            camera = editor.result_camera()
            if self._url_exists(camera.rtsp_url):
                QMessageBox.warning(self, "Duplicate camera", "This RTSP URL already exists.")
                return
            self.cameras.append(camera)
            self._refresh_table()
            self.table.selectRow(len(self.cameras) - 1)

    def _edit_camera(self, *_args) -> None:
        row = self._selected_row()
        if row < 0:
            return
        editor = CameraEditorDialog(self.cameras[row], self)
        if editor.exec() == QDialog.DialogCode.Accepted:
            camera = editor.result_camera()
            if self._url_exists(camera.rtsp_url, exclude_id=camera.id):
                QMessageBox.warning(self, "Duplicate camera", "This RTSP URL already exists.")
                return
            self.cameras[row] = camera
            self._refresh_table()
            self.table.selectRow(row)

    def _delete_camera(self) -> None:
        row = self._selected_row()
        if row < 0:
            return
        camera = self.cameras[row]
        answer = QMessageBox.question(
            self,
            "Delete camera",
            f"Delete {camera.name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            del self.cameras[row]
            self._refresh_table()

    def _url_exists(self, url: str, exclude_id: str | None = None) -> bool:
        normalized = url.strip().lower()
        return any(
            camera.id != exclude_id and camera.rtsp_url.strip().lower() == normalized
            for camera in self.cameras
        )
