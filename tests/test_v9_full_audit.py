import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.llm import LocalLLM
from core.dispatcher import SafeOSDispatcher
from tools.weather import geocode_location, get_weather
from tools.free_utilities import FreeUtilityBelt


class TestV9FullAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.llm = LocalLLM()
        cls.dispatcher = SafeOSDispatcher()
        cls.utility = FreeUtilityBelt()

    def test_1_global_and_malaysian_weather_completeness(self):
        """Test 1: Global & Malaysian Weather Completeness (including casual Layer 2 phrasing)."""
        prompts = [
            ("What's the weather for Kuantan?", "kuantan"),
            ("Is it going to rain in Penang?", "penang"),
            ("How hot is it in Tokyo?", "tokyo"),
            ("yo could you check how hot it is in Kuantan", "kuantan"),
            ("do I need an umbrella in Johor Bahru", "johor bahru"),
        ]
        for q, expected_city in prompts:
            res = self.llm.plan(q, dry_run=True)
            self.assertEqual(res.get("action"), "weather", f"Failed weather action for: {q} -> {res}")
            loc_str = (res.get("args", {}).get("location", "") + " " + res.get("voice_response", "")).lower()
            self.assertIn(expected_city, loc_str, f"Expected '{expected_city}' in weather response for: {q}")
            self.assertNotIn("search online", loc_str)
            self.assertNotIn("search it yourself", loc_str)

    def test_2_roblox_uwp_and_named_app_lifecycle(self):
        """Test 2: Roblox, UWP, & Named App Lifecycle without Microsoft Store popups."""
        spec = self.dispatcher.get_launch_spec("roblox")
        self.assertIsNotNone(spec)
        self.assertNotIn("ms-windows-store", str(spec).lower())
        self.assertNotIn("roblox://", str(spec).lower())

        clean_env = self.dispatcher._get_clean_env()
        self.assertNotIn("VIRTUAL_ENV", clean_env)

        open_prompts = [
            ("Open Roblox", "roblox"),
            ("Launch Overwatch", "overwatch"),
            ("fire up Roblox", "roblox"),
        ]
        for q, app_expected in open_prompts:
            res = self.llm.plan(q, dry_run=True)
            self.assertEqual(res.get("action"), "open_app", f"Expected open_app for '{q}', got {res}")
            app_id = (res.get("args", {}).get("app_id") or res.get("app_id") or "").lower()
            self.assertIn(app_expected, app_id)

        close_prompts = [
            ("Close Roblox", "roblox"),
            ("Close Discord", "discord"),
        ]
        for q, target_expected in close_prompts:
            res = self.llm.plan(q, dry_run=True)
            self.assertEqual(res.get("action"), "close_app", f"Expected close_app for '{q}', got {res}")
            t_name = (res.get("args", {}).get("target") or res.get("target") or "").lower()
            self.assertIn(target_expected, t_name)

        # Protected system process guard
        ok_sys, msg_sys = self.dispatcher.close_app("explorer.exe", dry_run=True)
        self.assertFalse(ok_sys)
        self.assertIn("protected", msg_sys.lower())

    def test_3_zero_refusal_autonomous_interceptor(self):
        """Test 3: Zero-Refusal Autonomous Interceptor catches lazy LLM refusals."""
        refusal_weather = self.llm._intercept_lazy_refusal(
            "What is the weather in Kuching?",
            "I don't have real-time data, please check a website yourself.",
            dry_run=True,
        )
        self.assertIsNotNone(refusal_weather)
        self.assertEqual(refusal_weather.get("action"), "weather")
        self.assertIn("kuching", refusal_weather.get("voice_response", "").lower())

        refusal_general = self.llm._intercept_lazy_refusal(
            "Who won the latest Formula 1 Grand Prix?",
            "I don't have real-time data, please check a website yourself.",
            dry_run=True,
        )
        self.assertIsNotNone(refusal_general)
        self.assertEqual(refusal_general.get("action"), "web_search")
        self.assertNotIn("check a website yourself", refusal_general.get("voice_response", "").lower())

    def test_4_free_utility_belt(self):
        """Test 4: Free Utility Belt — Currency, Math/Percentages, World Clock, and Ping."""
        # 1. Currency conversion
        res_curr = self.llm.plan("How much is 100 USD in MYR?", dry_run=True)
        self.assertEqual(res_curr.get("action"), "utility")
        self.assertEqual(res_curr.get("sub_action"), "currency")
        self.assertIn("myr", res_curr.get("voice_response", "").lower())

        res_sgd = self.llm.plan("Convert 50 Singapore dollars to ringgit", dry_run=True)
        self.assertEqual(res_sgd.get("action"), "utility")
        self.assertEqual(res_sgd.get("sub_action"), "currency")

        # 2. Math & Percentage
        res_pct = self.llm.plan("What is 25 percent of 1400?", dry_run=True)
        self.assertEqual(res_pct.get("action"), "utility")
        self.assertIn("350", res_pct.get("voice_response", ""))

        res_math = self.llm.plan("What is 185 times 42?", dry_run=True)
        self.assertEqual(res_math.get("action"), "utility")
        self.assertIn("7770", res_math.get("voice_response", ""))

        # 3. World Clock
        res_time = self.llm.plan("What time is it in London?", dry_run=True)
        self.assertEqual(res_time.get("action"), "utility")
        self.assertEqual(res_time.get("sub_action"), "time_date")
        self.assertIn("london", res_time.get("voice_response", "").lower())

        # 4. Network & Ping Check
        res_ping = self.llm.plan("Check my ping", dry_run=True)
        self.assertEqual(res_ping.get("action"), "utility")
        self.assertEqual(res_ping.get("sub_action"), "network_ping")
        self.assertIn("ping", res_ping.get("voice_response", "").lower())

    def test_5_cross_module_pronoun_chaining(self):
        """Test 5: Cross-Module Pronoun Chaining (Weather -> Distance & Folder -> Virus Scan)."""
        # Chain A: Weather in Kuantan -> "How far is it from home?"
        r1 = self.llm.plan("What's the weather for Kuantan?", dry_run=True)
        self.assertEqual(r1.get("action"), "weather")
        self.assertEqual(self.llm.last_context.get("city"), "Kuantan")

        r2 = self.llm.plan("How far is it from home?", dry_run=True)
        self.assertEqual(r2.get("action"), "spatial_distance")
        self.assertIn("kuantan", r2.get("voice_response", "").lower())
        self.assertGreater(r2.get("distance_km", 0), 100.0)

        # Chain B: Create folder AuditTest -> "Scan that folder for viruses"
        f1 = self.llm.plan("Create a folder called AuditTest on my desktop", dry_run=True)
        self.assertEqual(f1.get("action"), "create_folder")

        f2 = self.llm.plan("Scan that folder for viruses", dry_run=True)
        self.assertEqual(f2.get("action"), "virus_scan")
        self.assertIn("audittest", str(f2.get("target", "")).lower())

    def test_6_twenty_five_prompt_chaos_stress_matrix(self):
        """Test 6: 25-Prompt Chaos & Completeness Stress Matrix across all domains."""
        chaos_matrix = [
            ("What's the weather for Kuantan?", "weather"),
            ("Is it going to rain in Penang?", "weather"),
            ("How hot is it in Tokyo?", "weather"),
            ("yo could you check how hot it is in Kuantan", "weather"),
            ("How far is it from home?", "spatial_distance"),
            ("Open Roblox", "open_app"),
            ("Launch Overwatch", "open_app"),
            ("fire up Valorant", "open_app"),
            ("Close Roblox", "close_app"),
            ("Close Discord", "close_app"),
            ("How much is 100 USD in MYR?", "utility"),
            ("Convert 50 Singapore dollars to ringgit", "utility"),
            ("What is 25 percent of 1400?", "utility"),
            ("What is 185 times 42?", "utility"),
            ("What is the square root of 144?", "utility"),
            ("What time is it in London?", "utility"),
            ("What's today's date?", "utility"),
            ("Check my ping", "utility"),
            ("Create a folder called ChaosFolder on my desktop", "create_folder"),
            ("Scan that folder for viruses", "virus_scan"),
            ("Open that folder for me", "open_folder"),
            ("Check my system status and CPU usage", "system_status"),
            ("Pause the music", "media_control"),
            ("Set a timer for 10 minutes", "schedule_reminder"),
            ("Give me my morning briefing", "daily_briefing"),
        ]
        passed = 0
        for prompt, expected_action in chaos_matrix:
            res = self.llm.plan(prompt, dry_run=True)
            actual = res.get("action")
            self.assertEqual(
                actual,
                expected_action,
                f"Chaos Matrix mismatch on '{prompt}': expected '{expected_action}', got '{actual}' ({res})",
            )
            passed += 1

        self.assertEqual(passed, 25)


if __name__ == "__main__":
    print("=================================================================")
    print("   PROJECT LIBRA v9.0 - FULL AUTONOMOUS AUDIT & CHAOS SUITE")
    print("=================================================================")
    unittest.main(verbosity=2)
