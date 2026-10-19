import ctypes
import os
import sys
import time
from typing import Dict, Any, Optional, Tuple

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
    import pygetwindow as gw
    PYGETWINDOW_AVAILABLE = True
except ImportError:
    PYGETWINDOW_AVAILABLE = False


def _attach_thread_desktop():
    """Attaches the current calling thread to the interactive user input desktop on Windows."""
    if sys.platform == "win32" and hasattr(ctypes, "windll"):
        try:
            user32 = ctypes.windll.user32
            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception:
            pass


class GUIControlAgent:
    """
    Direct Desktop UI Automation Agent for Project Libra.
    Provides safe, programmatic mouse, keyboard, and window interaction:
      - Clicking & double-clicking screen coordinates or active UI elements
      - Keystroke execution, typing, hotkeys, and window focusing
      - Chrome profile selection & application navigation
    """

    def __init__(self):
        _attach_thread_desktop()

    @staticmethod
    def is_available() -> bool:
        return PYAUTOGUI_AVAILABLE

    def get_screen_size(self) -> Tuple[int, int]:
        _attach_thread_desktop()
        if PYAUTOGUI_AVAILABLE:
            sz = pyautogui.size()
            return sz.width, sz.height
        return 1920, 1080

    def get_mouse_position(self) -> Tuple[int, int]:
        _attach_thread_desktop()
        if PYAUTOGUI_AVAILABLE:
            pos = pyautogui.position()
            return pos.x, pos.y
        return 0, 0

    def click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left", clicks: int = 1, dry_run: bool = False) -> Dict[str, Any]:
        """Performs single or multiple mouse clicks at (x, y) or current position."""
        if dry_run:
            return {"status": "success", "action": "click", "dry_run": True, "voice_response": f"Prepared {button} click at {x or 'current'}, {y or 'current'}."}

        if not PYAUTOGUI_AVAILABLE:
            return {"status": "error", "message": "pyautogui not installed", "voice_response": "Desktop automation module is unavailable."}

        _attach_thread_desktop()
        try:
            if x is not None and y is not None:
                pyautogui.click(x=x, y=y, button=button, clicks=clicks)
            else:
                pyautogui.click(button=button, clicks=clicks)
            return {"status": "success", "action": "click", "x": x, "y": y, "button": button, "voice_response": "Clicked."}
        except Exception as e:
            return {"status": "error", "message": str(e), "voice_response": f"Failed to click: {e}"}

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None, dry_run: bool = False) -> Dict[str, Any]:
        return self.click(x=x, y=y, button="left", clicks=2, dry_run=dry_run)

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None, dry_run: bool = False) -> Dict[str, Any]:
        return self.click(x=x, y=y, button="right", clicks=1, dry_run=dry_run)

    def press_key(self, key_name: str, dry_run: bool = False) -> Dict[str, Any]:
        """Presses a single keyboard key (e.g., 'enter', 'esc', 'tab', 'space', 'win')."""
        clean_key = (key_name or "").lower().strip()
        if dry_run:
            return {"status": "success", "action": "press_key", "key": clean_key, "dry_run": True, "voice_response": f"Prepared key press: {clean_key}."}

        if not PYAUTOGUI_AVAILABLE:
            return {"status": "error", "message": "pyautogui not installed", "voice_response": "Desktop automation module is unavailable."}

        _attach_thread_desktop()
        try:
            pyautogui.press(clean_key)
            return {"status": "success", "action": "press_key", "key": clean_key, "voice_response": f"Pressed {clean_key}."}
        except Exception as e:
            return {"status": "error", "message": str(e), "voice_response": f"Failed to press key {clean_key}: {e}"}

    def hotkey(self, *keys, dry_run: bool = False) -> Dict[str, Any]:
        """Executes a key combination (e.g. ['ctrl', 'c'], ['alt', 'tab'], ['win', 'd'])."""
        clean_keys = [str(k).lower().strip() for k in keys if k]
        if dry_run:
            return {"status": "success", "action": "hotkey", "keys": clean_keys, "dry_run": True, "voice_response": f"Prepared hotkey: {'+'.join(clean_keys)}."}

        if not PYAUTOGUI_AVAILABLE:
            return {"status": "error", "message": "pyautogui not installed", "voice_response": "Desktop automation module is unavailable."}

        _attach_thread_desktop()
        try:
            pyautogui.hotkey(*clean_keys)
            return {"status": "success", "action": "hotkey", "keys": clean_keys, "voice_response": f"Executed {'+'.join(clean_keys)}."}
        except Exception as e:
            return {"status": "error", "message": str(e), "voice_response": f"Failed to execute hotkey: {e}"}

    def type_text(self, text: str, interval: float = 0.01, dry_run: bool = False) -> Dict[str, Any]:
        """Types arbitrary text string into the currently focused window."""
        if dry_run:
            return {"status": "success", "action": "type_text", "text": text, "dry_run": True, "voice_response": f"Prepared to type: {text[:20]}."}

        if not PYAUTOGUI_AVAILABLE:
            return {"status": "error", "message": "pyautogui not installed", "voice_response": "Desktop automation module is unavailable."}

        _attach_thread_desktop()
        try:
            pyautogui.write(text, interval=interval)
            return {"status": "success", "action": "type_text", "voice_response": "Typed text."}
        except Exception as e:
            return {"status": "error", "message": str(e), "voice_response": f"Failed to type text: {e}"}

    def focus_window_by_title(self, title_substring: str) -> bool:
        """Finds a window by title substring and restores/activates it."""
        _attach_thread_desktop()
        if not PYGETWINDOW_AVAILABLE:
            return False
        try:
            matches = [w for w in gw.getAllWindows() if title_substring.lower() in (w.title or "").lower()]
            if matches:
                target = matches[0]
                if target.isMinimized:
                    target.restore()
                target.activate()
                time.sleep(0.1)
                return True
        except Exception as e:
            print(f"[GUIControl Focus Warning]: {e}")
        return False

    def select_chrome_profile_ui(self, profile_index: int = 0, dry_run: bool = False) -> Dict[str, Any]:
        """
        Interacts with the Chrome profile selection window:
        Brings Chrome to focus, and if the profile picker is active,
        navigates to the requested profile (0 for first, 1 for second) and selects it.
        """
        if dry_run:
            return {"status": "success", "action": "select_chrome_profile", "index": profile_index, "dry_run": True, "voice_response": f"Selecting account {profile_index + 1} in Chrome."}

        _attach_thread_desktop()
        self.focus_window_by_title("Google Chrome")
        time.sleep(0.15)

        if PYAUTOGUI_AVAILABLE:
            try:
                # If first account: Enter selects default focused account tile immediately
                if profile_index == 0:
                    pyautogui.press("enter")
                else:
                    # Tab to subsequent profile tiles and press enter
                    for _ in range(profile_index):
                        pyautogui.press("tab")
                        time.sleep(0.05)
                    pyautogui.press("enter")
                return {"status": "success", "action": "select_chrome_profile", "index": profile_index, "voice_response": f"Selected account {profile_index + 1} in Chrome."}
            except Exception as e:
                return {"status": "error", "message": str(e), "voice_response": f"Failed to select profile: {e}"}
        return {"status": "error", "voice_response": "Desktop automation module is unavailable."}
