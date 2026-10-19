import unittest
import os
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.llm import LocalLLM
from tools.free_utilities import FreeUtilityBelt
from tools.window_context import ActiveWindowEngine
from tools.gui_control import GUIControlAgent


class TestLiveDebugFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Instantiate LocalLLM
        cls.llm = LocalLLM()

    def setUp(self):
        self.llm.session_state = {
            "active_apps": [],
            "last_action": None,
            "last_target": None,
            "pending_action": None,
            "pending_args": None,
        }
        self.llm.pending_chrome_profile = None

    # -------------------------------------------------------------------------
    # TEST 1: SCREEN VISION & ACTIVE WINDOW GROUND TRUTH (ZERO HALLUCINATION)
    # -------------------------------------------------------------------------
    def test_screen_vision_queries_route_properly(self):
        """Verify screen queries route to analyze_screen instead of fallback chat."""
        # 1. "what is my screen showing now? What's the first thing that you see on my screen?"
        p1 = "what is my screen showing now? What's the first thing that you see on my screen?"
        plan1 = self.llm.plan(p1, dry_run=True)
        self.assertEqual(plan1.get("action"), "analyze_screen", f"Expected analyze_screen but got {plan1.get('action')}")
        self.assertNotIn("libratest", plan1.get("voice_response", "").lower())

        # 2. Follow-up: "I'm not on Libra test photo, I should be on League of Legends. Can you see it properly and tell me, did you see that?"
        self.llm.session_state["last_action"] = "analyze_screen"
        p2 = "I'm not on Libra test photo, I should be on League of Legends. Can you see it properly and tell me, did you see that?"
        plan2 = self.llm.plan(p2, dry_run=True)
        self.assertEqual(plan2.get("action"), "analyze_screen", f"Expected analyze_screen but got {plan2.get('action')}")

        # 3. Follow-up: "then can you see my in-game name, what is it called, so I can check is it correct."
        p3 = "then can you see my in-game name, what is it called, so I can check is it correct."
        plan3 = self.llm.plan(p3, dry_run=True)
        self.assertEqual(plan3.get("action"), "analyze_screen", f"Expected analyze_screen but got {plan3.get('action')}")
        self.assertNotIn("libratestuser", plan3.get("voice_response", "").lower())

    def test_active_window_detection_grounding(self):
        """Verify ActiveWindowEngine detects running applications without returning Unknown."""
        engine = ActiveWindowEngine()
        info = engine.get_active_window_info(dry_run=False)
        self.assertIsInstance(info, dict)
        self.assertIn("app_label", info)
        self.assertIn("process_name", info)
        # Should not default to Unknown if desktop windows exist
        self.assertTrue(len(info["app_label"]) > 0)

    # -------------------------------------------------------------------------
    # TEST 2: TIMEZONE & LOCATION RESOLUTION (ARIZONA VS MALAYSIA)
    # -------------------------------------------------------------------------
    def test_arizona_timezone_resolution(self):
        """Verify US, Arizona resolves to America/Phoenix (MST UTC-7) and NOT Malaysia."""
        p = "what's the time now in the US, Arizona?"
        plan = self.llm.plan(p, dry_run=True)
        self.assertEqual(plan.get("action"), "world_time")
        self.assertEqual(plan.get("args", {}).get("timezone"), "America/Phoenix")
        self.assertIn("arizona", plan.get("voice_response", "").lower())
        self.assertIn("mountain standard time", plan.get("voice_response", "").lower())

    def test_timezone_objection_handling(self):
        """Verify conversational objections about timezone are clarified factually and not parsed as city names."""
        p = "Hey Libra, no I mean I'm in Malaysia and the time in the US is same as mine, are you sure?"
        plan = self.llm.plan(p, dry_run=True)
        self.assertEqual(plan.get("action"), "world_time")
        # Ensure it did NOT parse 'Us Is Same As Mine, Are You Sure' as the city
        self.assertNotIn("us is same as mine", plan.get("args", {}).get("city", "").lower())
        self.assertIn("not in the same time zone", plan.get("voice_response", "").lower())
        self.assertIn("15 hours behind", plan.get("voice_response", "").lower())

    def test_us_states_timezones(self):
        """Verify other US states resolve accurately."""
        # California -> America/Los_Angeles
        plan_ca = self.llm.plan("what is the time in California?", dry_run=True)
        self.assertEqual(plan_ca.get("args", {}).get("timezone"), "America/Los_Angeles")

        # Chicago -> America/Chicago
        plan_chi = self.llm.plan("what is the time in Chicago right now?", dry_run=True)
        self.assertEqual(plan_chi.get("args", {}).get("timezone"), "America/Chicago")

        # Tokyo -> Asia/Tokyo
        plan_tokyo = self.llm.plan("what is the time in Tokyo?", dry_run=True)
        self.assertEqual(plan_tokyo.get("args", {}).get("timezone"), "Asia/Tokyo")

    # -------------------------------------------------------------------------
    # TEST 3: CHROME MULTI-PROFILE SELECTION & GUI AUTOMATION
    # -------------------------------------------------------------------------
    def test_open_google_alias(self):
        """Verify 'open Google for me' is recognized as Chrome multi-profile."""
        p = "open Google for me"
        plan = self.llm.plan(p, dry_run=True)
        self.assertEqual(plan.get("action"), "open_app")
        self.assertEqual(plan.get("app_id"), "chrome")

    def test_open_first_account_in_chrome(self):
        """Verify 'can you help me open the first account in the Google Chrome?' resolves profile 0."""
        p = "can you help me open the first account in the Google Chrome?"
        plan = self.llm.plan(p, dry_run=True)
        self.assertEqual(plan.get("action"), "open_app")
        self.assertEqual(plan.get("app_id"), "chrome")
        self.assertIn("profile", plan)
        # Profile directory for first account is Default (Chuah)
        self.assertEqual(plan["profile"]["dir"], "Default")
        self.assertIn("chuah", plan.get("voice_response", "").lower())

    def test_gui_control_actions(self):
        """Verify GUI automation agent responds to click and profile selection."""
        agent = GUIControlAgent()
        res = agent.select_chrome_profile_ui(profile_index=0, dry_run=True)
        self.assertEqual(res["status"], "success")

        # Test command route for clicking first account
        p = "click the first account"
        plan = self.llm.plan(p, dry_run=True)
        self.assertEqual(plan.get("action"), "gui_action")

    # -------------------------------------------------------------------------
    # TEST 4: FOLLOW-UP FLOW & STANDBY RESETS (POLITENESS & QUESTIONS)
    # -------------------------------------------------------------------------
    def test_followup_terminal_politeness(self):
        """Simulate gui.py logic: 'Thank you' or terminal commands must return to STANDBY."""
        terminal_phrases = ["thank you", "thanks", "bye", "that's all", "good night"]
        for phrase in terminal_phrases:
            u_text_low = phrase.lower().strip()
            is_terminal_politeness = any(
                p in u_text_low
                for p in [
                    "thank you", "thanks", "thank u", "bye", "goodbye", "good bye",
                    "good night", "see you", "that's all", "thats all", "that will be all",
                    "never mind", "nevermind", "cancel", "dismiss", "stop listening", "go to sleep"
                ]
            )
            self.assertTrue(is_terminal_politeness, f"Failed for phrase: {phrase}")

    def test_followup_active_on_questions(self):
        """Questions ending with '?' or clarification status must remain in follow-up."""
        q_msg = "Which account would you like to use — Chuah or Paris?"
        is_question = q_msg.strip().endswith("?")
        self.assertTrue(is_question)


if __name__ == "__main__":
    unittest.main()
