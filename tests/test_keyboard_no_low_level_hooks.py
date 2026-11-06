import sys
import ctypes
import pytest
from unittest.mock import MagicMock, patch

def test_no_keyboard_low_level_hooks_installed_at_runtime(monkeypatch):
    """
    Verify that Project Libra uses native Win32 RegisterHotKey / GetAsyncKeyState
    and never installs low-level Windows keyboard hooks (WH_KEYBOARD_LL via the keyboard package),
    which cause severe system-wide keyboard delays and input lag during startup and heavy tasks.
    """
    import keyboard

    mock_user32 = MagicMock()
    mock_user32.RegisterHotKey.return_value = True
    mock_user32.UnregisterHotKey.return_value = True
    mock_user32.GetMessageW.return_value = 0
    mock_user32.GetAsyncKeyState.return_value = 0
    monkeypatch.setattr(ctypes.windll, "user32", mock_user32, raising=False)

    with patch.object(keyboard, "add_hotkey", side_effect=AssertionError("keyboard.add_hotkey must never be called! Use Win32 RegisterHotKey or GetAsyncKeyState.")) as mock_add_hk:
        from ui.spotlight_bar import GlobalHotkeyThread
        from ui.gui import MainWindowHotkeyThread
        from core.dictation import WhisperDictationController

        # 1. Test SpotlightBar GlobalHotkeyThread
        spotlight_thread = GlobalHotkeyThread()
        spotlight_thread.run()
        spotlight_thread.stop()

        # 2. Test MainWindowHotkeyThread
        main_thread = MainWindowHotkeyThread()
        main_thread.run()
        main_thread.stop()

        # 3. Test WhisperDictationController
        dictation = WhisperDictationController()
        dictation.start()
        dictation.pause()
        dictation.resume()
        dictation.stop()

        assert mock_add_hk.call_count == 0
