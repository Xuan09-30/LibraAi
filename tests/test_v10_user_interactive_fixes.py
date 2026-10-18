import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.llm import LocalLLM
from core.orchestrator import SupervisorHub
from core.scheduler import ReminderEngine
from tools.window_context import ActiveWindowEngine
from tools.free_utilities import FreeUtilityBelt
from tools.clipboard_agent import ClipboardAgent
from core.dispatcher import SafeOSDispatcher


class TestV10UserInteractiveFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.llm = LocalLLM()
        cls.hub = SupervisorHub(llm=cls.llm)
        cls.scheduler = ReminderEngine(db_filename=":memory:")
        cls.utilities = FreeUtilityBelt()

    def test_1_window_focus_and_script_explanation(self):
        """Verify window focus does not say 'Python - LIBRA' and script queries resolve properly."""
        engine = ActiveWindowEngine()

        # Simulated Libra window
        engine.set_mock_window({
            "process_name": "python.exe",
            "app_label": "Python",
            "app_category": "general",
            "window_title": "LIBRA // CYBERNETIC NEURAL INTERFACE",
            "memory_mb": 3300.0,
        })
        summary = engine.summarize_active_window(dry_run=True)
        self.assertIn("Libra Neural Terminal", summary["voice_response"])
        self.assertNotIn("Python — LIBRA", summary["voice_response"])

        # Simulated IDE with test.py
        engine.set_mock_window({
            "process_name": "code.exe",
            "app_label": "VS Code",
            "app_category": "ide",
            "window_title": "test.py - Project - Visual Studio Code",
            "active_file": "test.py",
        })
        query_res = engine.handle_contextual_query(
            "explain the script that I have right now and that I'm showing to you, this one, test.py",
            dry_run=True
        )
        self.assertEqual(query_res["action"], "active_window")
        self.assertEqual(query_res["sub_action"], "explain_script")

    def test_2_clipboard_conversational_queries(self):
        """Verify conversational clipboard questions route to clipboard_assist without Ollama hallucination."""
        prompts = [
            "Alright, I have copied the code into the clipboard. Now, can you see and know what I am doing on the clipboard there? I already copied it.",
            "Can you see what is on my clipboard?",
            "What did I just copy to the clipboard?",
            "Explain what I copied",
            "Analyze my clipboard",
            "explain the file",
            "analyze this file",
            "view or analyze the file",
            "I copied this to clipboard can you explain it",
            "what does this file do",
        ]
        for p in prompts:
            plan = self.hub.plan_or_execute(p, dry_run=True)
            # Should be clipboard_assist or subtask in compound
            if plan.get("compound"):
                actions = plan.get("actions", [])
                self.assertIn("clipboard_assist", actions, f"Failed for prompt: {p}")
            else:
                if p == "what does this file do":
                    self.assertIn(plan.get("action"), ["clipboard_assist", "active_window"])
                else:
                    self.assertEqual(plan.get("action"), "clipboard_assist", f"Failed for prompt: {p}")

    def test_3_timer_conversational_phrasing(self):
        """Verify conversational timers ('Okay now I want you to set a timer for 10 seconds') are parsed correctly."""
        # 1. 10-second timer with conversational prefix
        p1 = "Okay now I want you to set a timer for 10 seconds."
        parsed1 = self.scheduler.parse_reminder_request(p1)
        self.assertIsNotNone(parsed1)
        self.assertEqual(parsed1["time"], "in 10 seconds")

        plan1 = self.hub.plan_or_execute(p1, dry_run=True)
        self.assertEqual(plan1.get("action"), "schedule_reminder")
        self.assertIn("10 seconds", plan1.get("voice_response", ""))

        # 2. "Set the timer for 5 seconds."
        p2 = "Set the timer for 5 seconds."
        parsed2 = self.scheduler.parse_reminder_request(p2)
        self.assertIsNotNone(parsed2)
        self.assertEqual(parsed2["time"], "in 5 seconds")

        plan2 = self.hub.plan_or_execute(p2, dry_run=True)
        self.assertEqual(plan2.get("action"), "schedule_reminder")

        # 3. Watchdog toast alert phrasing
        import time
        res = self.scheduler.add_reminder("timer", "in 1 second", show_toast=False, dry_run=False)
        self.assertTrue(res["success"])
        time.sleep(1.2)
        due = self.scheduler.get_due_reminders(trigger_toast=True, dry_run=True)
        self.assertTrue(len(due) >= 1)
        # Toast message should have proactive alert format
        self.assertTrue(any("Hold up, your timer went off" in t.get("message", "") for t in self.scheduler.toast_history))

    def test_4_spotify_intent_and_prefix_cleaning(self):
        """Verify 'open my Spotify and play some music' does not split into broken subtasks or fail on 'my'."""
        # 1. Compound preservation
        p = "Hey Libra, can you open my Spotify and play some music?"
        plan = self.hub.plan_or_execute(p, dry_run=True)
        self.assertEqual(plan.get("action"), "spotify_play")

        # 2. "launch my Spotify right now"
        p2 = "can you please can you launch my Spotify right now?"
        plan2 = self.hub.plan_or_execute(p2, dry_run=True)
        self.assertEqual(plan2.get("action"), "spotify_play")

        # 3. Whisper acoustic slip "place a music"
        p3 = "open my spotify to place a music"
        plan3 = self.hub.plan_or_execute(p3, dry_run=True)
        self.assertEqual(plan3.get("action"), "spotify_play")

    def test_5_pronoun_chaining_for_time(self):
        """Verify 'What's the weather for Tokyo?' followed by 'what's the time there?' resolves Tokyo time."""
        # Step 1: Weather query sets Tokyo in context
        w_plan = self.hub.plan_or_execute("what's the weather for Tokyo?", dry_run=True)
        self.assertEqual(w_plan.get("action"), "weather")
        self.assertEqual(str(self.llm.last_context.get("city")).lower(), "tokyo")

        # Step 2: "what's the time there?" resolves 'there' to Tokyo
        t_plan = self.hub.plan_or_execute("Okay, what's the time there?", dry_run=True)
        self.assertEqual(t_plan.get("action"), "utility")
        self.assertIn(t_plan.get("sub_action"), ["time_date", "world_clock"])
        self.assertIn("Tokyo", t_plan.get("voice_response", ""))
        self.assertNotIn("Worldometer", t_plan.get("voice_response", ""))
        self.assertNotIn("Troye Sivan", t_plan.get("voice_response", ""))

    def test_6_security_scan_targeting_and_pronoun_resolution(self):
        """Verify security scan queries are not intercepted by open_app and resolve pronouns correctly."""
        # Set folder in context
        self.llm.last_context["folder"] = r"C:\Users\chenx\Desktop\libratest"

        # 1. "scan that specific folder for viruses"
        p1 = "Okay, I want you to scan that specific folder for viruses."
        plan1 = self.hub.plan_or_execute(p1, dry_run=True)
        self.assertEqual(plan1.get("action"), "virus_scan")
        self.assertEqual(plan1.get("target"), r"C:\Users\chenx\Desktop\libratest")

        # 2. "Run a security scan on Libra test."
        p2 = "Run a security scan on Libra test."
        plan2 = self.hub.plan_or_execute(p2, dry_run=True)
        self.assertEqual(plan2.get("action"), "virus_scan")
        self.assertNotEqual(plan2.get("action"), "open_app")

        # 3. "run a security test on C"
        p3 = "run a security test on C"
        plan3 = self.hub.plan_or_execute(p3, dry_run=True)
        self.assertEqual(plan3.get("action"), "virus_scan")

        # 4. "run the security test for the test file that I created which is a C"
        p4 = "run the security test for the test file that I created which is a C"
        plan4 = self.hub.plan_or_execute(p4, dry_run=True)
        self.assertEqual(plan4.get("action"), "virus_scan")

    def test_7_discord_termination_and_acoustic_slip(self):
        """Verify 'close this card' (Whisper slip for Discord) and 'I want to close this' work properly."""
        # 1. Whisper acoustic slip "close this card"
        p1 = "Okay now I want you to close this card for me. Thank you."
        plan1 = self.hub.plan_or_execute(p1, dry_run=True)
        self.assertEqual(plan1.get("action"), "close_app")
        self.assertEqual(plan1.get("target"), "discord")

        # 2. "I want to close this"
        p2 = "I want to close this"
        plan2 = self.hub.plan_or_execute(p2, dry_run=True)
        self.assertEqual(plan2.get("action"), "close_app")
        self.assertEqual(plan2.get("target"), "active")

        # 3. Dispatcher close_app for discord
        disp = SafeOSDispatcher()
        ok, msg = disp.close_app("discord", dry_run=True)
        self.assertTrue(ok)
        self.assertIn("discord", msg.lower())


if __name__ == "__main__":
    unittest.main()
