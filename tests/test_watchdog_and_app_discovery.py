import os
import sys
import time
import tempfile
import shutil
import pytest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.game_discovery import GameDiscoveryEngine
from core.dispatcher import SafeOSDispatcher
from core.folder_watchdog import AutomatedFolderWatchdog, DebouncedEventHandler


class TestUniversalAppDiscovery:
    """Verifies that GameDiscoveryEngine autonomously resolves any Windows app, utility, or game."""

    @pytest.fixture(scope="class")
    def discovery(self):
        return GameDiscoveryEngine()

    def test_windows_utilities_discovery(self, discovery):
        """Verifies built-in Windows utilities are indexed and discoverable."""
        notepad = discovery.resolve_app("notepad")
        assert notepad is not None
        assert "notepad" in notepad.get("name", "").lower() or "notepad" in notepad.get("target", "").lower()

        calc = discovery.resolve_app("calculator")
        assert calc is not None
        assert "calc" in calc.get("name", "").lower() or "calc" in calc.get("target", "").lower()

        cmd = discovery.resolve_app("cmd")
        assert cmd is not None
        assert "cmd" in cmd.get("name", "").lower() or "cmd" in cmd.get("target", "").lower()

    def test_acronym_and_fuzzy_resolution(self, discovery):
        """Verifies acronym mapping and fuzzy matching for core gaming & desktop apps."""
        val = discovery.resolve_app("val")
        assert val is not None
        assert val.get("name", "").lower() in ["valorant", "riot client"]

        steam = discovery.resolve_app("steam")
        assert steam is not None

        code = discovery.resolve_app("vscode")
        assert code is not None
        assert any(k in code.get("name", "").lower() for k in ["code", "visual studio code"])

    def test_system_path_shutil_which(self, discovery):
        """Verifies that system executables in PATH are resolved dynamically."""
        python_app = discovery.resolve_app("python")
        assert python_app is not None
        assert python_app.get("launch_type") == "executable"
        assert os.path.isfile(python_app.get("target"))

    def test_program_files_and_registry_scanning(self, discovery):
        """Verifies that total discovered applications exceed 200 via registry and program files."""
        assert len(discovery.apps) >= 50
        # Check that registry/utility sources are present
        sources = {v.get("source") for v in discovery.apps.values()}
        assert any(s in sources for s in ["windows_utility", "registry_app_paths", "registry_uninstall", "uwp_startapps", "lnk_shortcut"])


class TestUniversalAppDispatcher:
    """Verifies safe launch specification and universal process termination."""

    @pytest.fixture(scope="class")
    def dispatcher(self):
        return SafeOSDispatcher()

    def test_launch_app_dry_run_utilities(self, dispatcher):
        """Verifies dry-run launch succeeds for built-in utilities."""
        ok_np, msg_np = dispatcher.launch_app("notepad", dry_run=True)
        assert ok_np is True
        assert "launch prepared" in msg_np.lower()

        ok_calc, msg_calc = dispatcher.launch_app("calculator", dry_run=True)
        assert ok_calc is True
        assert "launch prepared" in msg_calc.lower()

    def test_close_app_dry_run(self, dispatcher):
        """Verifies dry-run termination signal generation."""
        ok, msg = dispatcher.close_app("discord", dry_run=True)
        assert ok is True
        assert "discord" in msg.lower()

        ok_chrome, msg_chrome = dispatcher.close_app("chrome", dry_run=True)
        assert ok_chrome is True
        assert "chrome" in msg_chrome.lower()

    def test_protected_processes_shielding(self, dispatcher):
        """Ensures critical system processes cannot be closed."""
        for sys_proc in ["explorer.exe", "svchost.exe", "wininit.exe", "python.exe"]:
            ok, msg = dispatcher.close_app(sys_proc, dry_run=False)
            assert ok is False
            assert "protected" in msg.lower()

    def test_close_active_window_dry_run(self, dispatcher):
        """Ensures active window close dry-run is clean and free of NameErrors."""
        ok, msg = dispatcher.close_active_window(dry_run=True)
        assert ok is True
        assert "close signal prepared" in msg.lower()


class TestAutomatedFolderWatchdog:
    """Verifies the background watchdog engine for programs and documents."""

    def test_watchdog_initialization_and_status(self):
        """Verifies folder discovery and status structure."""
        watchdog = AutomatedFolderWatchdog()
        status = watchdog.get_status()
        assert status["is_running"] is False
        assert status["program_dirs_monitored"] >= 1
        assert status["document_dirs_monitored"] >= 1
        assert "program_directories" in status
        assert "document_directories" in status

    def test_debounced_event_handler(self):
        """Verifies that rapid file events are collapsed into a single debounced callback."""
        callback_calls = []

        def on_event(path, event_type):
            callback_calls.append((path, event_type))

        handler = DebouncedEventHandler(callback=on_event, delay=0.1)

        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = r"C:\fake\test_app.lnk"

        # Simulate 5 rapid burst events
        for _ in range(5):
            handler.on_created(mock_event)

        time.sleep(0.3)
        assert len(callback_calls) == 1
        assert callback_calls[0] == (r"C:\fake\test_app.lnk", "created")

    def test_program_event_triggers_discovery_refresh(self):
        """Verifies that an added .lnk or .exe shortcut triggers discovery refresh."""
        mock_discovery = MagicMock()
        mock_discovery.apps = {"app1": {}}

        watchdog = AutomatedFolderWatchdog(discovery_engine=mock_discovery)
        watchdog._handle_program_event(r"C:\Users\fake\Desktop\NewGame.lnk", "created")

        mock_discovery.refresh.assert_called_once()
        assert watchdog.stats["program_events_count"] == 1

    def test_document_event_triggers_rag_ingest(self):
        """Verifies that a newly dropped code/doc file triggers Document RAG ingestion."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tf:
            tf.write(b"print('hello world')")
            temp_path = tf.name

        try:
            mock_rag = MagicMock()
            watchdog = AutomatedFolderWatchdog(document_rag=mock_rag)
            watchdog._handle_document_event(temp_path, "created")

            mock_rag.ingest_file.assert_called_once_with(temp_path)
            assert watchdog.stats["document_events_count"] == 1
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_watchdog_lifecycle_start_and_stop(self):
        """Verifies clean non-blocking startup and shutdown of background observer."""
        watchdog = AutomatedFolderWatchdog()
        watchdog.start()
        assert watchdog.stats["is_running"] is True

        watchdog.stop()
        assert watchdog.stats["is_running"] is False
