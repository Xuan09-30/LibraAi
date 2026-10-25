import os
import sys
import unittest
import json
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.version import LIBRA_VERSION, LIBRA_CODENAME, get_full_version_string


class TestVersionAndReloaderDisplay(unittest.TestCase):
    def test_version_strings(self):
        self.assertEqual(LIBRA_VERSION, "10.2.0")
        self.assertEqual(get_full_version_string(0), "v10.2.0")
        self.assertEqual(get_full_version_string(1), "v10.2.0-r1")
        self.assertEqual(get_full_version_string(5), "v10.2.0-r5")

    def test_gui_version_display_mock(self):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from unittest.mock import patch
        from PyQt6.QtWidgets import QApplication, QWidget
        from ui.gui import FuturisticVoiceAssistantUI

        class MockWebEngineView(QWidget):
            def setUrl(self, url):
                pass

        app = QApplication.instance() or QApplication(["test"])

        # Test initial launch display (reload_count = 0)
        with patch("ui.gui.QWebEngineView", side_effect=MockWebEngineView):
            window = FuturisticVoiceAssistantUI(start_worker=False)
        self.assertEqual(window.reload_count, 0)
        self.assertIsNotNone(window.version_label)
        text_initial = window.version_label.text()
        self.assertIn("LIBRA v10.2.0", text_initial)
        self.assertIn("LIVE RELOAD ACTIVE", text_initial)

        # Test simulated reload state
        window.reload_count = 2
        window.reloaded_from = "core/memory.py"
        window.reloaded_at = "17:55:00"
        window.update_version_display()

        text_reloaded = window.version_label.text()
        self.assertIn("v10.2.0-r2", text_reloaded)
        self.assertIn("RELOADED", text_reloaded)
        self.assertIn("17:55:00", text_reloaded)
        self.assertIn("core/memory.py", text_reloaded)
        self.assertIn("HOT-RELOAD: SYNCD", text_reloaded)

        # Test in-flight status override (when file is touched)
        window.update_version_display(status_override="RELOADING (orchestrator.py)...")
        text_override = window.version_label.text()
        self.assertIn("RELOADING (orchestrator.py)...", text_override)

        window._quit_application()


if __name__ == "__main__":
    unittest.main()
