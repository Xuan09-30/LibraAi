import os
import sys
import time
import ctypes
from ctypes import wintypes
import requests
import json
from typing import Optional, Dict, Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QRect
from PyQt6.QtGui import QFont, QColor, QGuiApplication, QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QFrame, QApplication
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from skills.clipboard_manager import skill as clipboard_skill

# Win32 Constants
MOD_ALT = 0x0001
MOD_NOREPEAT = 0x4000
VK_SPACE = 0x20
VK_CONTROL = 0x11
VK_C = 0x43
VK_V = 0x56
WM_HOTKEY = 0x0312
HOTKEY_ID_SPOTLIGHT = 9001

KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", INPUT_UNION),
    ]


def _synthesize_key_combo(vk_modifier: int, vk_key: int):
    """Synthesizes modifier + key press (e.g. Ctrl + C or Ctrl + V)."""
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32

    # Modifier Down, Key Down, Key Up, Modifier Up
    inputs = [
        INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=KEYBDINPUT(wVk=vk_modifier, wScan=0, dwFlags=0, time=0, dwExtraInfo=None))),
        INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=KEYBDINPUT(wVk=vk_key, wScan=0, dwFlags=0, time=0, dwExtraInfo=None))),
        INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=KEYBDINPUT(wVk=vk_key, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=None))),
        INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=KEYBDINPUT(wVk=vk_modifier, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=None))),
    ]
    inp_array = (INPUT * 4)(*inputs)
    user32.SendInput(4, ctypes.byref(inp_array), ctypes.sizeof(INPUT))


class GlobalHotkeyThread(QThread):
    """Background QThread hosting low-overhead Win32 message loop for Alt + Space."""
    hotkey_triggered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def run(self):
        if sys.platform != "win32":
            return
        user32 = ctypes.windll.user32
        success = user32.RegisterHotKey(
            None,
            HOTKEY_ID_SPOTLIGHT,
            MOD_ALT | MOD_NOREPEAT,
            VK_SPACE
        )
        if not success:
            print(f"[Spotlight] Failed to register Alt + Space global hotkey (Error {ctypes.GetLastError()}).")
            return

        print("[Spotlight] Global hotkey registered: [Alt + Space] -> Universal Highlight & Ask.")
        msg = wintypes.MSG()
        while self._running:
            res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if not isinstance(res, int) or res <= 0:
                break
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID_SPOTLIGHT:
                self.hotkey_triggered.emit()
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.UnregisterHotKey(None, HOTKEY_ID_SPOTLIGHT)

    def stop(self):
        self._running = False
        if sys.platform == "win32":
            ctypes.windll.user32.PostQuitMessage(0)
        self.wait(500)


class SpotlightBar(QWidget):
    """
    Universal 'Highlight & Ask' Global Hotkey Bar (v11.0 / Phase 11).
    Centered, translucent, frameless HUD appearing on Alt + Space.
    Non-destructively grabs active text selection via Win32 SendInput Ctrl+C,
    preserves previous clipboard state, and performs inline transformations (Ctrl+V)
    or conversational streaming reasoning via Ollama.
    """

    def __init__(self, orchestrator=None, parent=None):
        super().__init__(parent)
        self.orchestrator = orchestrator
        self.prev_hwnd: Optional[int] = None
        self.active_selection: str = ""
        self.ollama_url = "http://localhost:11434"

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(720)

        self.init_ui()

        # Wire global hotkey
        self.hotkey_thread = GlobalHotkeyThread(self)
        self.hotkey_thread.hotkey_triggered.connect(self.trigger_spotlight)
        self.hotkey_thread.start()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(0)

        self.container = QFrame(self)
        self.container.setObjectName("SpotlightContainer")
        self.container.setStyleSheet("""
            QFrame#SpotlightContainer {
                background-color: rgba(4, 9, 18, 0.95);
                border: 1px solid #00ffcc;
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # 1. Top row: Selection Pill (if text captured) + Esc hint
        self.top_row = QHBoxLayout()
        self.top_row.setSpacing(8)

        self.pill_btn = QPushButton("")
        self.pill_btn.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        self.pill_btn.setStyleSheet("""
            QPushButton {
                background: #0f2338; color: #38bdf8;
                border: 1px solid #0284c7; border-radius: 4px;
                padding: 3px 8px; text-align: left;
            }
            QPushButton:hover { background: #163352; color: #f43f5e; border-color: #f43f5e; }
        """)
        self.pill_btn.setToolTip("Click to remove captured selection context")
        self.pill_btn.clicked.connect(self.clear_selection)
        self.pill_btn.hide()
        self.top_row.addWidget(self.pill_btn)

        self.top_row.addStretch()

        esc_hint = QLabel("[ESC] DISMISS | [ENTER] EXECUTE")
        esc_hint.setFont(QFont("Consolas", 7))
        esc_hint.setStyleSheet("color: #64748b;")
        self.top_row.addWidget(esc_hint)

        layout.addLayout(self.top_row)

        # 2. Input Box
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        icon_lbl = QLabel("◈")
        icon_lbl.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        icon_lbl.setStyleSheet("color: #00ffcc;")
        input_row.addWidget(icon_lbl)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask Libra, or enter inline transformation (e.g. fix bug, rewrite, explain)...")
        self.input_field.setFont(QFont("Consolas", 11))
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: transparent; color: #f8fafc;
                border: none; padding: 4px;
            }
        """)
        self.input_field.returnPressed.connect(self.on_submit)
        input_row.addWidget(self.input_field, stretch=1)

        layout.addLayout(input_row)

        # 3. Response / Stream Output Box (collapsed by default)
        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setFont(QFont("Consolas", 9))
        self.output_box.setStyleSheet("""
            QTextEdit {
                background-color: #02050a; color: #cbd5e1;
                border: 1px solid #142845; border-radius: 6px;
                padding: 8px; line-height: 1.4;
            }
        """)
        self.output_box.setFixedHeight(180)
        self.output_box.hide()
        layout.addWidget(self.output_box)

        # 4. Action bar for responses
        self.action_row = QHBoxLayout()
        self.action_row.setSpacing(6)
        self.action_row.addStretch()

        self.replace_btn = QPushButton("INJECT [Ctrl+V]")
        self.replace_btn.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        self.replace_btn.setStyleSheet("background: #047857; color: #a7f3d0; border: 1px solid #10b981; padding: 4px 10px; border-radius: 4px;")
        self.replace_btn.clicked.connect(self.inject_replacement)
        self.replace_btn.hide()
        self.action_row.addWidget(self.replace_btn)

        self.copy_btn = QPushButton("COPY")
        self.copy_btn.setFont(QFont("Consolas", 8))
        self.copy_btn.setStyleSheet("background: #0f1d30; color: #38bdf8; border: 1px solid #1e3a5f; padding: 4px 10px; border-radius: 4px;")
        self.copy_btn.clicked.connect(self.copy_output)
        self.copy_btn.hide()
        self.action_row.addWidget(self.copy_btn)

        layout.addLayout(self.action_row)

        root_layout.addWidget(self.container)

    def trigger_spotlight(self):
        """Called when Alt + Space global hotkey fires."""
        if sys.platform == "win32":
            self.prev_hwnd = ctypes.windll.user32.GetForegroundWindow()

        # Non-destructively capture active selection
        captured = self._capture_active_selection()
        self.active_selection = captured

        # Update UI
        if self.active_selection:
            snippet = self.active_selection.strip().replace("\n", " ")[:30]
            self.pill_btn.setText(f"[Selection: {len(self.active_selection)} chars — \"{snippet}...\"] ✕")
            self.pill_btn.show()
        else:
            self.pill_btn.hide()

        self.input_field.clear()
        self.output_box.clear()
        self.output_box.hide()
        self.replace_btn.hide()
        self.copy_btn.hide()

        # Center in top third of screen
        screen = QGuiApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = max(100, int(screen.height() * 0.18))
        self.move(x, y)

        self.show()
        self.raise_()
        self.activateWindow()
        self.input_field.setFocus()

    def _capture_active_selection(self) -> str:
        """
        Non-destructively captures text selection from the active foreground window:
        1. Backs up user's existing clipboard text into skill ring-buffer.
        2. Synthesizes Ctrl + C via SendInput (waits 35ms).
        3. Reads newly copied selection.
        4. Restores previous clipboard text so user clipboard is 100% unpolluted.
        """
        clipboard = QApplication.clipboard()
        prev_clipboard = clipboard.text()

        # Preserve in clipboard manager ring-buffer
        if prev_clipboard:
            try:
                clipboard_skill.execute({"action": "save", "text": prev_clipboard}, {})
            except Exception:
                pass

        # Clear clipboard temporarily to detect if Ctrl+C copied anything
        clipboard.clear()
        time.sleep(0.01)

        # Synthesize Ctrl + C
        _synthesize_key_combo(VK_CONTROL, VK_C)
        time.sleep(0.035)  # 35ms wait specified in requirements

        captured = clipboard.text()

        # Restore previous clipboard
        if prev_clipboard:
            clipboard.setText(prev_clipboard)

        return captured.strip() if captured else ""

    def clear_selection(self):
        self.active_selection = ""
        self.pill_btn.hide()
        self.input_field.setFocus()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def on_submit(self):
        prompt = self.input_field.text().strip()
        if not prompt:
            return

        # Check if inline transformation / edit was requested
        is_transform = any(k in prompt.lower() for k in [
            "fix", "rewrite", "replace", "refactor", "correct", "translate", "format",
            "clean up", "optimize", "convert", "camel case", "snake case"
        ])

        if is_transform and self.active_selection:
            self._execute_transformation(prompt, self.active_selection)
        else:
            self._execute_explanation(prompt, self.active_selection)

    def _execute_transformation(self, prompt: str, selection: str):
        self.output_box.setText("Processing inline transformation...")
        self.output_box.show()
        self.replace_btn.show()
        self.copy_btn.show()

        def _worker():
            try:
                sys_prompt = (
                    "You are an elite code and text transformation engine. "
                    "Apply the user's requested transformation to the provided selection. "
                    "Return ONLY the replacement text. Do NOT include explanations, apologies, "
                    "or conversational markdown wrappers unless code blocks were originally present."
                )
                user_msg = f"User Request: {prompt}\n\nSelection to transform:\n{selection}"
                resp = requests.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": "qwen3:8b",
                        "messages": [
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": user_msg}
                        ],
                        "stream": False,
                        "options": {"temperature": 0.2}
                    },
                    timeout=20
                )
                if resp.status_code == 200:
                    out = resp.json().get("message", {}).get("content", "").strip()
                    QTimer.singleShot(0, lambda: self._on_transform_complete(out))
                else:
                    QTimer.singleShot(0, lambda: self.output_box.setText(f"Ollama error: {resp.status_code}"))
            except Exception as e:
                QTimer.singleShot(0, lambda: self.output_box.setText(f"Inference error: {e}"))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_transform_complete(self, replacement: str):
        self.output_box.setPlainText(replacement)
        # If user explicitly said "fix this bug" or "rewrite", prompt for immediate inject
        self.replace_btn.setFocus()

    def _execute_explanation(self, prompt: str, selection: str):
        self.output_box.setText("Reasoning...")
        self.output_box.show()
        self.copy_btn.show()

        def _worker():
            try:
                context_part = f"\nContext:\n{selection}\n" if selection else ""
                resp = requests.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": "qwen3:8b",
                        "messages": [
                            {"role": "system", "content": "You are Libra, an elite local desktop AI assistant. Provide concise, direct answers."},
                            {"role": "user", "content": f"{prompt}{context_part}"}
                        ],
                        "stream": False
                    },
                    timeout=20
                )
                if resp.status_code == 200:
                    out = resp.json().get("message", {}).get("content", "").strip()
                    QTimer.singleShot(0, lambda: self.output_box.setPlainText(out))
                else:
                    QTimer.singleShot(0, lambda: self.output_box.setText(f"Inference error {resp.status_code}"))
            except Exception as e:
                QTimer.singleShot(0, lambda: self.output_box.setText(f"Error: {e}"))

        import threading
        threading.Thread(target=_worker, daemon=True).start()

    def inject_replacement(self):
        """Restores foreground focus to target window and injects replacement via Ctrl + V."""
        replacement = self.output_box.toPlainText()
        if not replacement or sys.platform != "win32":
            return

        self.hide()

        # Restore focus to previous target window
        if self.prev_hwnd:
            ctypes.windll.user32.SetForegroundWindow(self.prev_hwnd)
            time.sleep(0.05)

        # Set clipboard to replacement
        clipboard = QApplication.clipboard()
        prev_clip = clipboard.text()
        clipboard.setText(replacement)
        time.sleep(0.02)

        # Synthesize Ctrl + V
        _synthesize_key_combo(VK_CONTROL, VK_V)
        time.sleep(0.05)

        # Restore previous clipboard
        if prev_clip:
            clipboard.setText(prev_clip)

    def copy_output(self):
        text = self.output_box.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.copy_btn.setText("COPIED!")
            QTimer.singleShot(1500, lambda: self.copy_btn.setText("COPY"))
