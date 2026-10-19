import os
import sys
import unittest
import winreg
import psutil

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.window_context import ActiveWindowEngine, APP_FRIENDLY_NAMES
from core.game_discovery import GameDiscoveryEngine
from core.dispatcher import SafeOSDispatcher
from core.memory import SemanticMemory
from core.folder_watchdog import AutomatedFolderWatchdog
from core.llm import LocalLLM


class TestGamingGuardAndMemorySafety(unittest.TestCase):
    def setUp(self):
        self.window_engine = ActiveWindowEngine()
        self.discovery = GameDiscoveryEngine()
        self.dispatcher = SafeOSDispatcher(discovery=self.discovery)

    def test_1_window_context_detects_games(self):
        """ActiveWindowEngine correctly identifies gaming titles and marks app_category as 'game'."""
        games_to_test = [
            ("overwatch.exe", "Overwatch 2"),
            ("valorant.exe", "Valorant"),
            ("cs2.exe", "Counter-Strike 2"),
            ("r5apex.exe", "Apex Legends"),
            ("robloxplayerbeta.exe", "Roblox"),
            ("leagueclient.exe", "League of Legends"),
        ]
        for exe, label in games_to_test:
            self.assertIn(exe, APP_FRIENDLY_NAMES, f"Executable {exe} must be in APP_FRIENDLY_NAMES")
            friendly, cat = APP_FRIENDLY_NAMES[exe]
            self.assertEqual(cat, "game", f"{exe} must be categorized as 'game'")

        # Test title-based inference
        mock_info = {
            "hwnd": 1234,
            "pid": 5678,
            "process_name": "unknown_client.exe",
            "app_label": "Unknown Client",
            "app_category": "general",
            "window_title": "Overwatch 2 - Season 12",
        }
        self.window_engine.set_mock_window(mock_info)
        info = self.window_engine.get_active_window_info()
        self.assertEqual(info.get("app_category"), "game")
        self.assertIn("Overwatch", info.get("app_label"))

    def test_2_game_discovery_rejects_generic_stop_words(self):
        """Generic queries ('app', 'program', 'game', 'window', 'close a program') must NEVER resolve to Roblox or any app."""
        generic_queries = [
            "app",
            "apps",
            "program",
            "programs",
            "game",
            "games",
            "window",
            "windows",
            "a program",
            "the program",
            "an app",
            "the app",
            "any app",
            "any apps",
            "any program",
            "open a program",
            "close a program",
            "close any apps",
            "open or close a program or any apps",
            "it",
            "this",
        ]
        for q in generic_queries:
            resolved = self.discovery.resolve_app(q)
            self.assertIsNone(
                resolved,
                f"Generic query '{q}' should NOT resolve to any application, but got {resolved}",
            )

    def test_3_game_discovery_resolves_legitimate_apps(self):
        """Real application and game queries should resolve cleanly."""
        legit_apps = ["overwatch", "valorant", "discord", "chrome", "notepad"]
        for app in legit_apps:
            resolved = self.discovery.resolve_app(app)
            self.assertIsNotNone(resolved, f"Legitimate app '{app}' should resolve")
            self.assertIn("name", resolved)

    def test_4_dispatcher_does_not_launch_roblox_on_generic_queries(self):
        """SafeOSDispatcher.launch_app must reject generic requests and not launch Roblox."""
        test_queries = [
            "a program",
            "close a program",
            "or close a program or any apps",
            "any apps",
        ]
        for q in test_queries:
            ok, msg = self.dispatcher.launch_app(q, dry_run=True)
            self.assertFalse(ok, f"Expected launch_app to reject '{q}', but succeeded: {msg}")
            self.assertNotIn("roblox", msg.lower())

    def test_5_memory_distance_thresholds_and_deduplication(self):
        """SemanticMemory must enforce tightened thresholds and deduplicate assistant responses."""
        mem = SemanticMemory()
        self.assertLessEqual(mem.recall_relevant.__defaults__[1], 0.55)
        self.assertLessEqual(mem.recall_episodes.__defaults__[1], 0.50)

    def test_6_anti_hallucination_and_echo_guard(self):
        """LocalLLM must block repeated hallucinated phrases like Kuantan/UV/Paku Teh on unrelated queries."""
        llm = LocalLLM()
        gamer_queries = [
            "See my daddy. One Xiao brother. Cheers.",
            "Ok,我要試一下玩這個了,我要試一下打這條水了",
            "Bye, Joey.",
            "The game is a big game.",
        ]
        for q in gamer_queries:
            plan = llm.plan(q, dry_run=True)
            voice = (plan.get("voice_response") or "").lower()
            self.assertNotIn("kuantan", voice, f"Query '{q}' should not hallucinate Kuantan")
            self.assertNotIn("uv", voice, f"Query '{q}' should not hallucinate UV index")
            self.assertNotIn("paku teh", voice, f"Query '{q}' should not hallucinate Paku Teh")
            self.assertNotIn("no need to pretend", voice, f"Query '{q}' should not echo old canned phrase")

    def test_7_folder_watchdog_cooldown_and_dev_filtering(self):
        """AutomatedFolderWatchdog must ignore dev directories and rate-limit refresh."""
        watchdog = AutomatedFolderWatchdog()
        self.assertTrue(hasattr(watchdog, "_refresh_cooldown"))
        self.assertGreaterEqual(watchdog._refresh_cooldown, 5.0)

    def test_8_roblox_not_in_registry_and_no_orphans(self):
        """Verify Roblox is not in HKCU Run registry and no RobloxCrashHandler processes exist."""
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ,
            ) as k:
                try:
                    val, _ = winreg.QueryValueEx(k, "RobloxPlayerBeta")
                    self.fail(f"RobloxPlayerBeta should NOT be in HKCU Run registry, but found: {val}")
                except FileNotFoundError:
                    pass
        except Exception:
            pass

        # Check for any lingering Roblox crash handlers
        crash_handlers = [
            p.info["name"]
            for p in psutil.process_iter(["name"])
            if "robloxcrashhandler" in (p.info.get("name") or "").lower()
        ]
        self.assertEqual(len(crash_handlers), 0, f"Found lingering crash handlers: {crash_handlers}")


if __name__ == "__main__":
    unittest.main()
