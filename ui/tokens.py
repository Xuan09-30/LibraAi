"""
Project Libra - Cybernetic Design Tokens & QSS Theme Engine
Shared design tokens mapped to PyQt6 desktop stylesheet (QSS)
"""
import os
import json
from typing import Dict, Any

_TOKENS_PATH = os.path.join(os.path.dirname(__file__), "tokens.json")

def load_tokens() -> Dict[str, Any]:
    """Loads tokens from tokens.json with cybernetic dark fallback."""
    if os.path.isfile(_TOKENS_PATH):
        try:
            with open(_TOKENS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "colors": {
            "dark": {
                "bg_app": "#09090b",
                "bg_surface": "#121215",
                "bg_card": "#18181b",
                "bg_card_hover": "#222226",
                "border_subtle": "rgba(255, 255, 255, 0.08)",
                "border_medium": "rgba(255, 255, 255, 0.14)",
                "accent_cyan": "#38bdf8",
                "accent_emerald": "#34d399",
                "accent_amber": "#fbbf24",
                "accent_purple": "#c084fc",
                "accent_rose": "#fb7185",
                "text_primary": "#f8fafc",
                "text_secondary": "#cbd5e1",
                "text_dim": "#64748b"
            }
        }
    }

# Status banner harmonized tokens
STATUS_THEMES = {
    "IDLE": {
        "text": "Standby // Ready (Alt+Space)",
        "color": "#94a3b8",
        "bg": "#121215",
        "border": "rgba(255, 255, 255, 0.1)"
    },
    "LISTENING": {
        "text": "Listening // Neural Audio Stream...",
        "color": "#38bdf8",
        "bg": "rgba(56, 189, 248, 0.12)",
        "border": "rgba(56, 189, 248, 0.35)"
    },
    "THINKING": {
        "text": "Cognitive Reasoning // Qwen3 Engine...",
        "color": "#c084fc",
        "bg": "rgba(192, 132, 252, 0.12)",
        "border": "rgba(192, 132, 252, 0.35)"
    },
    "SPEAKING": {
        "text": "Vocal Synthesis // Kokoro-82M TTS...",
        "color": "#34d399",
        "bg": "rgba(52, 211, 153, 0.12)",
        "border": "rgba(52, 211, 153, 0.35)"
    }
}

def get_shared_qss() -> str:
    """Returns the unified cybernetic stylesheet for PyQt6 windows."""
    return """
    /* Universal Cybernetic Design Tokens */
    QWidget {
        background-color: #09090b;
        color: #f8fafc;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", sans-serif;
        font-size: 13px;
        selection-background-color: #0284c7;
        selection-color: #f8fafc;
    }

    QMainWindow, QDialog {
        background-color: #09090b;
    }

    /* Input Fields */
    QLineEdit, QTextEdit, QPlainTextEdit {
        background-color: #121215;
        color: #f8fafc;
        border: 1px solid rgba(255, 255, 255, 0.14);
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 13px;
    }

    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
        border: 1px solid #38bdf8;
        background-color: #151519;
    }

    /* Buttons */
    QPushButton {
        background-color: #18181b;
        color: #cbd5e1;
        border: 1px solid rgba(255, 255, 255, 0.14);
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: 600;
        font-size: 13px;
        min-height: 36px;
    }

    QPushButton:hover {
        background-color: #222226;
        color: #f8fafc;
        border-color: rgba(56, 189, 248, 0.45);
    }

    QPushButton:pressed {
        background-color: #121215;
    }

    QPushButton#primary, QPushButton[accent="true"] {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #38bdf8, stop:1 #0284c7);
        color: #09090b;
        font-weight: 700;
        border: none;
    }

    QPushButton#primary:hover, QPushButton[accent="true"]:hover {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7dd3fc, stop:1 #38bdf8);
    }

    /* Scrollbars */
    QScrollBar:vertical {
        background: #09090b;
        width: 8px;
        margin: 0px;
        border-radius: 4px;
    }

    QScrollBar::handle:vertical {
        background: rgba(255, 255, 255, 0.16);
        min-height: 24px;
        border-radius: 4px;
    }

    QScrollBar::handle:vertical:hover {
        background: #38bdf8;
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }

    /* Tooltips */
    QToolTip {
        background-color: #18181b;
        color: #f8fafc;
        border: 1px solid rgba(255, 255, 255, 0.18);
        border-radius: 6px;
        padding: 5px 9px;
        font-size: 12px;
    }
    """
