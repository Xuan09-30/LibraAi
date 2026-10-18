import os
import sys
import pytest
import subprocess
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.llm import LocalLLM
from core.orchestrator import SupervisorHub


class TestStealthAndUIControl:
    @pytest.fixture(autouse=True)
    def setup_class(self):
        self.llm = LocalLLM()
        self.supervisor = SupervisorHub(llm=self.llm)

    def test_show_ui_variations(self):
        """Validates that all explicit and conversational 'show UI' requests route to show_ui."""
        phrases = [
            "show me your ui",
            "show your ui",
            "show ui",
            "open your ui",
            "bring up your window",
            "show window",
            "display ui",
            "open your window",
            "hey libra, can you please show your ui",
            "bring up the neural interface",
        ]
        for phrase in phrases:
            plan = self.llm.plan(phrase, dry_run=True)
            assert plan["action"] == "show_ui", f"Failed for phrase: '{phrase}', got action: '{plan.get('action')}'"
            assert "neural interface" in plan["voice_response"].lower() or "interface" in plan["voice_response"].lower() or "ui" in plan["voice_response"].lower()

    def test_hide_ui_variations(self):
        """Validates that all explicit and conversational 'hide UI' requests route to hide_ui."""
        phrases = [
            "hide your ui",
            "hide me your ui",
            "hide ui",
            "close your window",
            "minimize ui",
            "hide window",
            "go to background",
            "send to background",
            "hey libra, please minimize your window",
        ]
        for phrase in phrases:
            plan = self.llm.plan(phrase, dry_run=True)
            assert plan["action"] == "hide_ui", f"Failed for phrase: '{phrase}', got action: '{plan.get('action')}'"
            assert "background" in plan["voice_response"].lower() or "interface" in plan["voice_response"].lower() or "tray" in plan["voice_response"].lower()

    def test_window_closure_separation(self):
        """Ensures 'close your window' routes to hide_ui while 'close the active window' routes to close_app."""
        close_libra = self.llm.plan("close your window", dry_run=True)
        assert close_libra["action"] == "hide_ui"

        close_active = self.llm.plan("close the active window", dry_run=True)
        assert close_active["action"] == "close_app"
        assert close_active["target"] == "active"

        close_discord = self.llm.plan("close discord", dry_run=True)
        assert close_discord["action"] == "close_app"
        assert close_discord["target"] == "discord"

    def test_compound_ui_control(self):
        """Tests compound multi-intent execution containing UI visibility steps."""
        compound_prompt = "hide your ui and check my system status"
        plan = self.supervisor.plan_or_execute(compound_prompt, dry_run=True)
        assert plan.get("compound") is True
        assert "hide_ui" in plan["actions"]
        assert "system_status" in plan["actions"]

    def test_vbs_startup_runner_integrity(self):
        """Validates that Launch_Libra_Background.vbs exists, is well-formed, and specifies stealth execution."""
        vbs_path = os.path.join(PROJECT_ROOT, "scripts", "Launch_Libra_Background.vbs")
        assert os.path.exists(vbs_path), f"Missing VBS launcher at: {vbs_path}"

        with open(vbs_path, "r", encoding="utf-8") as f:
            vbs_content = f.read()

        assert "pythonw.exe" in vbs_content
        assert "--hidden" in vbs_content
        # Window style 0: invisible / no console window
        assert ", 0, False" in vbs_content or ", 0, True" in vbs_content

    def test_setup_startup_cli(self):
        """Validates that setup_startup.py --status executes with return code 0."""
        setup_script = os.path.join(PROJECT_ROOT, "scripts", "setup_startup.py")
        assert os.path.exists(setup_script), f"Missing setup script at: {setup_script}"

        cmd = [sys.executable, setup_script, "--status"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0
        assert "Project Libra Startup Status" in res.stdout

    def test_gui_handle_core_response(self):
        """Validates that FuturisticVoiceAssistantUI.handle_core_response dispatches show/hide properly."""
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt6.QtWidgets import QApplication, QWidget
        from ui.gui import FuturisticVoiceAssistantUI

        class MockWebEngineView(QWidget):
            def setUrl(self, url):
                pass

        app = QApplication.instance() or QApplication(sys.argv)
        with patch("ui.gui.QWebEngineView", side_effect=MockWebEngineView):
            ui = FuturisticVoiceAssistantUI(start_worker=False)

        with patch.object(ui, "show_interface") as mock_show, patch.object(ui, "hide_interface") as mock_hide:
            ui.handle_core_response({"action": "show_ui"})
            mock_show.assert_called_once()

            ui.handle_core_response({"action": "hide_ui"})
            mock_hide.assert_called_once()

        ui._quit_application()
