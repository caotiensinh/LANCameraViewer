APP_STYLE = """
QMainWindow, QWidget {
    background-color: #101214;
    color: #e8e8e8;
    font-family: "Segoe UI";
    font-size: 12px;
}
QLabel#RealtimeWarning {
    min-height: 20px;
    max-height: 20px;
    padding: 0 10px;
    background-color: #5a4612;
    color: #fff0b3;
    border: none;
    font-size: 11px;
    font-weight: 600;
}
QLabel#RealtimeWarning[level="critical"] {
    background-color: #682a2a;
    color: #ffd6d6;
}
QFrame#HeaderBar {
    background-color: #171a1d;
    border-bottom: 1px solid #292d31;
}
QLabel#AppTitle {
    font-size: 14px;
    font-weight: 600;
    color: #f3f3f3;
}
QPushButton, QToolButton {
    min-height: 28px;
    padding: 0 10px;
    border: 1px solid #343a40;
    border-radius: 4px;
    background-color: #22262a;
    color: #dedede;
}
QPushButton:hover, QToolButton:hover {
    background-color: #2b3035;
}
QPushButton:checked, QToolButton:checked {
    background-color: #3b4249;
    border-color: #69737d;
}
QPushButton#IconButton {
    min-width: 30px;
    max-width: 36px;
    padding: 0;
}
QFrame#CameraTile {
    background-color: #050607;
    border: none;
}
QFrame#CameraTile[focused="true"] {
    border: none;
}
QWidget#VideoSurface {
    background-color: #050607;
}
QFrame#OverlayBar {
    background-color: rgba(8, 10, 12, 185);
    border: none;
}
QLabel#CameraName {
    color: white;
    font-size: 12px;
    font-weight: 500;
    background: transparent;
}
QLabel#StatusDot {
    min-width: 8px;
    max-width: 8px;
    min-height: 8px;
    max-height: 8px;
    border-radius: 4px;
    background-color: #747a80;
}
QDialog, QMessageBox {
    background-color: #171a1d;
}
QLineEdit, QTableWidget {
    background-color: #0f1113;
    border: 1px solid #343a40;
    border-radius: 4px;
    padding: 5px;
    selection-background-color: #394149;
}
QHeaderView::section {
    background-color: #252a2f;
    color: #e8e8e8;
    border: none;
    padding: 6px;
}
"""
