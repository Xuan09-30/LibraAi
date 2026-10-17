import os
import sys
import ctypes
from typing import Optional, Callable

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QLineEdit, QPushButton, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

MOD_ALT = 0x0001
VK_SPACE = 0x20
HOTKEY_ID_ALT_SPACE = 9001


class MiniOrbIndicator(QWidget):
    """Compact glowing cybernetic orb dot for the Floating HUD Pill."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self.orb_color = QColor("#00f2fe")

    def set_color(self, hex_color: str):
        self.orb_color = QColor(hex_color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.orb_color))
        painter.drawEllipse(3, 3, 16, 16)


class FloatingHUDPill(QWidget):
    """
    Global Floating HUD Pill (v8.0).
    A frameless, draggable, translucent top-level PyQt6 command bar
    (`Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool`)
    positioned at the top center of the screen and toggled via `Alt+Space` (`RegisterHotKey`).
    """

    command_submitted = pyqtSignal(str)

    def __init__(self, on_submit: Optional[Callable[[str], None]] = None, register_hotkey: bool = True):
        super().__init__()
        self.on_submit = on_submit
        self._drag_pos: Optional[QPoint] = None
        self.hotkey_registered = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(520, 48)
        self._init_ui()
        self.center_top_on_screen()

        if register_hotkey:
            self.register_global_hotkey()

    def _init_ui(self):
        container = QWidget(self)
        container.setGeometry(0, 0, 520, 48)
        container.setStyleSheet("""
            QWidget {
                background-color: rgba(8, 13, 25, 230);
                border: 1px solid #00f2fe;
                border-radius: 24px;
            }
        """)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(10)

        self.orb_dot = MiniOrbIndicator(container)
        layout.addWidget(self.orb_dot)

        badge = QLabel("LIBRA")
        badge.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        badge.setStyleSheet("color: #00f2fe; border: none; background: transparent; letter-spacing: 1.5px;")
        layout.addWidget(badge)

        self.input_field = QLineEdit(container)
        self.input_field.setPlaceholderText("Ask Libra or run a command... (Alt+Space)")
        self.input_field.setFont(QFont("Consolas", 10))
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: #f8fafc;
                border: none;
                padding: 4px;
            }
        """)
        self.input_field.returnPressed.connect(self._handle_submit)
        layout.addWidget(self.input_field, stretch=1)

        close_btn = QPushButton("×", container)
        close_btn.setFixedSize(24, 24)
        close_btn.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #64748b;
                border: none;
            }
            QPushButton:hover {
                color: #f43f5e;
            }
        """)
        close_btn.clicked.connect(self.hide)
        layout.addWidget(close_btn)

    def center_top_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.x() + (geom.width() - self.width()) // 2
            y = geom.y() + 28
            self.move(x, y)

    def register_global_hotkey(self) -> bool:
        """Registers Alt+Space via Windows user32.RegisterHotKey."""
        if os.name != "nt":
            return False
        try:
            hwnd = int(self.winId())
            ok = ctypes.windll.user32.RegisterHotKey(hwnd, HOTKEY_ID_ALT_SPACE, MOD_ALT, VK_SPACE)
            self.hotkey_registered = bool(ok)
            return self.hotkey_registered
        except Exception:
            self.hotkey_registered = False
            return False

    def unregister_global_hotkey(self):
        if os.name == "nt" and self.hotkey_registered:
            try:
                hwnd = int(self.winId())
                ctypes.windll.user32.UnregisterHotKey(hwnd, HOTKEY_ID_ALT_SPACE)
            except Exception:
                pass
            self.hotkey_registered = False

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.center_top_on_screen()
            self.show()
            self.raise_()
            self.activateWindow()
            self.input_field.setFocus()

    def _handle_submit(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self.command_submitted.emit(text)
        if callable(self.on_submit):
            self.on_submit(text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        event.accept()
