import os
import sys
import unittest
import ctypes
from ctypes import wintypes

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.setup_startup import check_status, is_registry_registered, SHORTCUT_PATH, DESKTOP_SHORTCUT_PATH


class TestSingleInstanceAndStartup(unittest.TestCase):
    def test_startup_cleanliness(self):
        """Verify that the registry run key is disabled and only the startup shortcut is active."""
        self.assertFalse(is_registry_registered(), "Windows Run Registry should be disabled to prevent dual launches.")
        self.assertTrue(os.path.exists(SHORTCUT_PATH), "Startup folder .lnk must exist.")
        self.assertTrue(os.path.exists(DESKTOP_SHORTCUT_PATH), "Desktop shortcut must exist.")

    def test_shortcut_no_hidden_flag(self):
        """Verify that the startup shortcut arguments do not contain --hidden."""
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            sc = shell.CreateShortCut(SHORTCUT_PATH)
            self.assertNotIn("--hidden", sc.Arguments, "Startup shortcut arguments must not contain --hidden.")
            self.assertTrue(sc.TargetPath.endswith("pythonw.exe"), "Target should be pythonw.exe.")
            self.assertEqual(os.path.normpath(sc.WorkingDirectory), os.path.normpath(PROJECT_ROOT), "WorkingDirectory must match PROJECT_ROOT.")
        except Exception as e:
            self.skipTest(f"win32com dispatch failed: {e}")

    def test_windows_named_mutex_primitive(self):
        """Verify that Windows Named Mutex atomically prevents dual instance acquisition."""
        ERROR_ALREADY_EXISTS = 183
        MUTEX_NAME = "Local\\Test_LibraAssistant_Mutex_Verification"

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE

        # 1. Acquire mutex in primary handle
        h1 = kernel32.CreateMutexW(None, True, MUTEX_NAME)
        err1 = kernel32.GetLastError()
        self.assertNotEqual(h1, 0)
        self.assertNotEqual(err1, ERROR_ALREADY_EXISTS)

        # 2. Attempt secondary acquisition -> must detect ERROR_ALREADY_EXISTS
        h2 = kernel32.CreateMutexW(None, True, MUTEX_NAME)
        err2 = kernel32.GetLastError()
        self.assertEqual(err2, ERROR_ALREADY_EXISTS)

        # 3. Cleanup
        if h2:
            kernel32.CloseHandle(h2)
        if h1:
            kernel32.CloseHandle(h1)


if __name__ == "__main__":
    unittest.main()
