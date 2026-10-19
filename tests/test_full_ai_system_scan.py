import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.orchestrator import SupervisorHub
from core.llm import LocalLLM
from tools.weather import get_weather, geocode_location


class TestFullAISystemScan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("\n" + "=" * 70)
        print("   PROJECT LIBRA v10.0 - COMPREHENSIVE AI SYSTEM SCAN & STRESS TEST")
        print("=" * 70)
        cls.supervisor = SupervisorHub()
        cls.llm = cls.supervisor.llm

    def setUp(self):
        # Reset session context between tests for clean test isolation
        self.llm.last_context.clear()
        self.llm.session_state.clear()

    # -----------------------------------------------------------------
    # SUITE 1: WEATHER & GEOCODING ACCURACY (NO UŞAK / NO TOKYO MIXUP)
    # -----------------------------------------------------------------
    def test_01_weather_usa_phrasing(self):
        """Verify 'what the weather in USA right now' maps to Washington D.C., USA."""
        plan = self.supervisor.plan_or_execute("what the weather in USA right now", dry_run=True)
        self.assertEqual(plan.get("action"), "weather")
        self.assertIn("washington", plan.get("location", "").lower())
        self.assertNotIn("uşak", plan.get("location", "").lower())
        self.assertNotIn("usak", plan.get("location", "").lower())
        self.assertNotIn("tokyo", plan.get("voice_response", "").lower())

    def test_02_weather_country_aliases(self):
        """Test country aliases map cleanly to representative cities."""
        countries = [
            ("what's the weather in Japan", "tokyo"),
            ("how is the weather in UK right now", "london"),
            ("tell me the weather in Australia", "sydney"),
            ("weather in Germany tomorrow", "berlin"),
            ("weather in France this weekend", "paris"),
            ("weather in Canada", "toronto"),
            ("weather in South Korea", "seoul"),
        ]
        for query, expected_city in countries:
            plan = self.supervisor.plan_or_execute(query, dry_run=True)
            self.assertEqual(plan.get("action"), "weather", f"Query '{query}' failed to route to weather")
            self.assertIn(expected_city, plan.get("location", "").lower(), f"Query '{query}' did not map to {expected_city}")

    def test_03_weather_context_chaining(self):
        """Test asking weather for a place, then asking 'what about the weather there'."""
        plan1 = self.supervisor.plan_or_execute("What's the weather in Tokyo?", dry_run=True)
        self.assertEqual(plan1.get("action"), "weather")
        self.assertEqual(self.llm.last_context.get("city"), "Tokyo")

        # Now ask about the weather there
        plan2 = self.supervisor.plan_or_execute("what about the weather there?", dry_run=True)
        self.assertEqual(plan2.get("action"), "weather")
        self.assertIn("tokyo", plan2.get("location", "").lower())

    # -----------------------------------------------------------------
    # SUITE 2: WORLD TIME & NO CONTEXT CROSS-CONTAMINATION
    # -----------------------------------------------------------------
    def test_04_time_in_usa(self):
        """Verify 'what's the time in USA' resolves Eastern Time without crashing."""
        plan = self.supervisor.plan_or_execute("what's the time in USA", dry_run=True)
        self.assertEqual(plan.get("action"), "world_time")
        self.assertIn("United States", plan.get("voice_response", ""))
        self.assertIn("Eastern Time", plan.get("voice_response", ""))

    def test_05_time_right_now_uses_home_city_not_previous_context(self):
        """Verify 'what time is it right now' reports home city (Kuala Lumpur), NOT prior city!"""
        # Step 1: Discuss Tokyo
        self.supervisor.plan_or_execute("what's the weather for Tokyo?", dry_run=True)
        self.assertEqual(self.llm.last_context.get("city"), "Tokyo")

        # Step 2: Ask general time right now -> MUST NOT say Tokyo!
        plan_now = self.supervisor.plan_or_execute("what time is it right now", dry_run=True)
        self.assertEqual(plan_now.get("action"), "world_time")
        self.assertIn("Kuala Lumpur", plan_now.get("voice_response", ""))
        self.assertNotIn("Tokyo", plan_now.get("voice_response", ""))

    def test_06_time_pronoun_chaining_there(self):
        """Verify 'what's the time there' explicitly targets previous city."""
        self.supervisor.plan_or_execute("what's the weather for London?", dry_run=True)
        t_plan = self.supervisor.plan_or_execute("what's the time there?", dry_run=True)
        self.assertEqual(t_plan.get("action"), "world_time")
        self.assertIn("London", t_plan.get("voice_response", ""))

    # -----------------------------------------------------------------
    # SUITE 3: APP LAUNCH & PROCESS MANAGEMENT
    # -----------------------------------------------------------------
    def test_07_app_launch_and_close(self):
        """Test launching and closing desktop applications."""
        l_discord = self.supervisor.plan_or_execute("launch Discord", dry_run=True)
        self.assertIn(l_discord.get("action"), ["launch_app", "universal_app", "open_app"])
        self.assertEqual(l_discord.get("args", {}).get("app_name", "").lower(), "discord")

        c_discord = self.supervisor.plan_or_execute("shut down Discord", dry_run=True)
        self.assertIn(c_discord.get("action"), ["close_app", "kill_process"])
        self.assertEqual(c_discord.get("args", {}).get("app_name", "").lower(), "discord")

        l_spotify = self.supervisor.plan_or_execute("open Spotify to play some music", dry_run=True)
        self.assertIn(l_spotify.get("action"), ["launch_app", "spotify", "spotify_play", "universal_app", "open_app"])

    # -----------------------------------------------------------------
    # SUITE 4: CLIPBOARD COPILOT
    # -----------------------------------------------------------------
    def test_08_clipboard_actions(self):
        """Test clipboard explain, summarize, and save."""
        p_exp = self.supervisor.plan_or_execute("explain what I just copied", dry_run=True)
        self.assertEqual(p_exp.get("action"), "clipboard_assist")

        p_sum = self.supervisor.plan_or_execute("summarize what is on my clipboard", dry_run=True)
        self.assertEqual(p_sum.get("action"), "clipboard_assist")
        self.assertEqual(p_sum.get("sub_action"), "clipboard_summarize")

        p_save = self.supervisor.plan_or_execute("save my clipboard to a note called Meeting Notes", dry_run=True)
        self.assertEqual(p_save.get("action"), "clipboard_save")
        self.assertIn("meeting notes", p_save.get("args", {}).get("title", "").lower())

    # -----------------------------------------------------------------
    # SUITE 5: HERMES SKILL FORGE
    # -----------------------------------------------------------------
    def test_09_skill_forge_creation_and_listing(self):
        """Test dynamic skill learning and listing."""
        p_skill = self.supervisor.plan_or_execute("can you learn how to calculate sales tax?", dry_run=True)
        self.assertEqual(p_skill.get("action"), "create_skill")
        self.assertIn("sales tax", p_skill.get("args", {}).get("task", "").lower())

        p_list = self.supervisor.plan_or_execute("list your learned skills", dry_run=True)
        self.assertEqual(p_list.get("action"), "list_skills")

    # -----------------------------------------------------------------
    # SUITE 6: UI VISIBILITY & STEALTH COMMANDS
    # -----------------------------------------------------------------
    def test_10_ui_visibility_toggles(self):
        """Test voice commands to show or hide the WebGL UI."""
        p_show = self.supervisor.plan_or_execute("Hey Libra, show me your UI", dry_run=True)
        self.assertEqual(p_show.get("action"), "show_ui")

        p_hide = self.supervisor.plan_or_execute("hide your window", dry_run=True)
        self.assertEqual(p_hide.get("action"), "hide_ui")

    # -----------------------------------------------------------------
    # SUITE 7: UTILITY BELT & CONVERSIONS
    # -----------------------------------------------------------------
    def test_11_currency_and_math_utilities(self):
        """Test financial conversion and math queries."""
        p_curr = self.supervisor.plan_or_execute("how much is 100 USD in MYR?", dry_run=True)
        self.assertEqual(p_curr.get("action"), "utility")

        p_math = self.supervisor.plan_or_execute("what is 25 times 40?", dry_run=True)
        self.assertEqual(p_math.get("action"), "utility")

    # -----------------------------------------------------------------
    # SUITE 8: CONVERSATIONAL INTEGRITY
    # -----------------------------------------------------------------
    def test_12_conversational_questions(self):
        """Test conversational and identity questions."""
        p_who = self.supervisor.plan_or_execute("who are you and what can you do?", dry_run=True)
        self.assertEqual(p_who.get("action"), "chat")
        self.assertIsNotNone(p_who.get("voice_response"))

    # -----------------------------------------------------------------
    # SUITE 9: DISAMBIGUATION & SYSTEM STRESS CASES
    # -----------------------------------------------------------------
    def test_13_teach_yourself_skill_not_intercepted_by_kill(self):
        """Verify 'teach yourself a skill' routes to create_skill, NOT close_app (due to 'kill')."""
        p = self.supervisor.plan_or_execute("teach yourself a skill to calculate BMI", dry_run=True)
        self.assertEqual(p.get("action"), "create_skill")
        self.assertIn("calculate bmi", p.get("args", {}).get("task", "").lower())

    def test_14_virus_scan_natural_phrasing(self):
        """Verify compound scan query routes cleanly to virus_scan with accurate target."""
        p = self.supervisor.plan_or_execute("run the security test, the security virus scan for the test file that I created, which is a C", dry_run=True)
        self.assertEqual(p.get("action"), "virus_scan")
        self.assertIn("test", p.get("args", {}).get("target", "").lower())

    def test_15_spotify_place_music(self):
        """Verify 'open my Spotify to place a music' routes to spotify_play."""
        p = self.supervisor.plan_or_execute("open my Spotify to place a music", dry_run=True)
        self.assertEqual(p.get("action"), "spotify_play")


if __name__ == "__main__":
    unittest.main()
