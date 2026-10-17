import os
import sys
import time
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.orchestrator import SupervisorHub
from core.scheduler import ReminderEngine
from core.skill_forge import SkillForge
from core.persona import PersonaEngine


class TestV10ContextRemindersSkills(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("\n=================================================================")
        print("   PROJECT LIBRA v10.0 - CONTEXT, REMINDERS, SPOTIFY & SKILLS")
        print("=================================================================")
        cls.supervisor = SupervisorHub()
        cls.llm = cls.supervisor.llm

    def tearDown(self):
        self.llm.window_engine.set_mock_window(None)

    def test_1_active_window_context_awareness(self):
        """Test 1: Active-Window Context Awareness across VS Code and Chrome."""
        # 1A. Simulate VS Code editing llm.py in LibraAi
        self.llm.window_engine.set_mock_window({
            "hwnd": 1001,
            "pid": 4321,
            "process_name": "Code.exe",
            "app_label": "VS Code",
            "app_category": "ide",
            "window_title": "● llm.py - LibraAi - Visual Studio Code",
            "memory_mb": 340.0,
        })

        r_work = self.supervisor.plan_or_execute("What am I working on?", dry_run=True)
        self.assertEqual(r_work.get("action"), "active_window")
        self.assertIn("VS Code", r_work.get("voice_response", ""))
        self.assertIn("llm.py", r_work.get("voice_response", ""))

        # Test acoustic Whisper mishearing ("what a man walking on right now")
        r_mishear = self.supervisor.plan_or_execute("Hey Libra, what a man walking on right now.", dry_run=True)
        self.assertEqual(r_mishear.get("action"), "active_window")
        self.assertEqual(r_mishear.get("sentiment", {}).get("urgency"), "normal")
        self.assertIn("VS Code", r_mishear.get("voice_response", ""))

        r_script = self.supervisor.plan_or_execute("Explain what this script does", dry_run=True)
        self.assertEqual(r_script.get("action"), "active_window")
        self.assertEqual(r_script.get("sub_action"), "explain_script")
        self.assertIn("llm.py", r_script.get("voice_response", ""))

        # Put a Python error in clipboard and ask "What does this error mean?"
        self.llm.clipboard_agent.set_clipboard("ZeroDivisionError: division by zero at line 42")
        r_err = self.supervisor.plan_or_execute("What does this error mean?", dry_run=True)
        self.assertEqual(r_err.get("action"), "active_window")
        self.assertEqual(r_err.get("sub_action"), "explain_error")
        self.assertIn("ZeroDivisionError", r_err.get("voice_response", ""))

        # 1B. Simulate Google Chrome on a GitHub Pull Request
        self.llm.window_engine.set_mock_window({
            "hwnd": 1002,
            "pid": 8765,
            "process_name": "chrome.exe",
            "app_label": "Google Chrome",
            "app_category": "browser",
            "window_title": "Pull Request #42 · GitHub - Google Chrome",
            "memory_mb": 512.0,
        })

        r_page = self.supervisor.plan_or_execute("Summarize what's on this page", dry_run=True)
        self.assertEqual(r_page.get("action"), "active_window")
        self.assertEqual(r_page.get("sub_action"), "summarize_page")
        self.assertIn("Pull Request", r_page.get("voice_response", ""))
        self.assertIn("42", r_page.get("voice_response", ""))

        r_reply = self.supervisor.plan_or_execute("Can you write a reply to this thread?", dry_run=True)
        self.assertEqual(r_reply.get("action"), "active_window")
        self.assertEqual(r_reply.get("sub_action"), "draft_reply")
        self.assertTrue(bool(r_reply.get("draft")))

    def test_2_smart_windows_reminders_and_toasts(self):
        """Test 2: Smart Windows 11 Reminders, Timers, Alarms & Action Center Toasts."""
        # 2A. Natural phrasing: "Remind me to take a break in 45 minutes"
        r1 = self.supervisor.plan_or_execute("Remind me to take a break in 45 minutes", dry_run=True)
        self.assertEqual(r1.get("action"), "schedule_reminder")
        self.assertEqual(r1.get("task"), "take a break")
        self.assertEqual(r1.get("time"), "in 45 minutes")
        self.assertTrue(r1.get("toast_dispatched"))

        # 2B. Timer phrasing: "Set a timer for 15 minutes"
        r2 = self.supervisor.plan_or_execute("Set a timer for 15 minutes", dry_run=True)
        self.assertEqual(r2.get("action"), "schedule_reminder")
        self.assertEqual(r2.get("time"), "in 15 minutes")

        # 2C. Specific time phrasing: "Remind me at 5 PM to check the build"
        r3 = self.supervisor.plan_or_execute("Remind me at 5 PM to check the build", dry_run=True)
        self.assertEqual(r3.get("action"), "schedule_reminder")
        self.assertEqual(r3.get("task"), "check the build")

        # 2D. List and Cancel reminders
        r_list = self.supervisor.plan_or_execute("What reminders do I have?", dry_run=True)
        self.assertEqual(r_list.get("action"), "list_reminders")

        r_cancel = self.supervisor.plan_or_execute("Cancel my reminders", dry_run=True)
        self.assertEqual(r_cancel.get("action"), "cancel_reminders")

        # 2E. Verify in-memory SQLite ReminderEngine + Toast Dispatch on due reminder
        mem_sched = ReminderEngine(db_filename=":memory:")
        added = mem_sched.add_reminder("stretch your legs", "in 1 second", show_toast=False, dry_run=False)
        self.assertTrue(added.get("success"))
        self.assertEqual(len(mem_sched.list_pending_reminders()), 1)
        time.sleep(1.2)
        due = mem_sched.get_due_reminders(trigger_toast=True, dry_run=True)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["task"], "stretch your legs")
        self.assertTrue(len(mem_sched.toast_history) >= 1)

    def test_3_spotify_now_playing_and_controls(self):
        """Test 3: Spotify Now-Playing Inspector and Casual Playback Routing."""
        r_np = self.supervisor.plan_or_execute("What song is playing?", dry_run=True)
        self.assertEqual(r_np.get("action"), "spotify_now_playing")
        self.assertIn("Spotify", r_np.get("voice_response", ""))

        r_np2 = self.supervisor.plan_or_execute("What's playing on Spotify?", dry_run=True)
        self.assertEqual(r_np2.get("action"), "spotify_now_playing")

        r_play = self.supervisor.plan_or_execute("Put on some synthwave on Spotify", dry_run=True)
        self.assertEqual(r_play.get("action"), "spotify_play")
        self.assertIn("synthwave", r_play.get("query", "").lower())

    def test_4_modular_skills_library(self):
        """Test 4: Pre-Built Modular Hermes Skills Library discovery and execution."""
        forge = SkillForge()
        skills = forge.list_skills()
        slugs = {s["slug"] for s in skills}
        expected = {
            "hardware_vitals",
            "desktop_janitor",
            "active_window",
            "smart_reminders",
            "spotify_controller",
        }
        self.assertTrue(expected.issubset(slugs), f"Missing skills: {expected - slugs}")

        # Trigger hardware_vitals via natural prompt
        r_ram = self.supervisor.plan_or_execute("What is eating my RAM?", dry_run=False)
        self.assertEqual(r_ram.get("action"), "run_learned_skill")
        self.assertEqual(r_ram.get("slug"), "hardware_vitals")
        self.assertIn("CPU", r_ram.get("voice_response", ""))

        # Trigger desktop_janitor via natural prompt
        r_dl = self.supervisor.plan_or_execute("Analyze my downloads", dry_run=False)
        self.assertEqual(r_dl.get("action"), "run_learned_skill")
        self.assertEqual(r_dl.get("slug"), "desktop_janitor")
        self.assertIn("Downloads", r_dl.get("voice_response", ""))

    def test_5_humanlike_anti_robotic_persona(self):
        """Test 5: PersonaEngine strips robotic AI boilerplate and keeps replies natural."""
        raw = "Certainly! As an AI language model, I'd be happy to help you with that. The capital of Japan is Tokyo. Let me know if you need anything else!"
        clean = PersonaEngine.strip_robotic_filler(raw)
        self.assertEqual(clean, "The capital of Japan is Tokyo.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
