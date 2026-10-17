import os
import sys
import unittest
import shutil

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.data_scientist import DataScienceAgent
from core.idle_daemon import IdleTaskDaemon
from core.skill_forge import SkillForge
from core.llm import LocalLLM


class TestV7DataScienceAndHUD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.llm = LocalLLM()
        cls.ds_agent = DataScienceAgent(file_mgr=cls.llm.file_mgr)
        cls.idle_daemon = IdleTaskDaemon(
            memory=cls.llm.memory,
            distiller=cls.llm.distiller,
            monitor=cls.llm.monitor,
            discovery=getattr(cls.llm.dispatcher, "discovery", None)
        )
        cls.skill_forge = SkillForge(skills_dir="skills_test_v7")

    @classmethod
    def tearDownClass(cls):
        test_skills_dir = os.path.join(PROJECT_ROOT, "skills_test_v7")
        if os.path.exists(test_skills_dir):
            shutil.rmtree(test_skills_dir, ignore_errors=True)

    def test_1_autonomous_data_science_and_visualization(self):
        """
        Test 1 (Data Science & Visualization):
        Call DataScienceAgent.run_analysis("Find me valid data on global EV sales and make it into a visualization and explain it", dry_run=True),
        verify a non-empty pandas.DataFrame is analyzed, verify a valid PNG image is written to assets/plots/latest_analysis.png,
        and verify voice_response contains statistical insights.
        """
        prompt = "Find me valid data on global EV sales and make it into a visualization and explain it"
        df = self.ds_agent.fetch_or_load_data(prompt, dry_run=True)
        self.assertFalse(df.empty, "Fetched DataFrame must not be empty")
        self.assertGreaterEqual(len(df), 3, "DataFrame should contain at least 3 rows")

        res = self.ds_agent.run_analysis(prompt, dry_run=True)
        self.assertEqual(res.get("status"), "success")

        plot_path = res.get("plot_path")
        self.assertIsNotNone(plot_path)
        self.assertTrue(os.path.isfile(plot_path), f"Plot file does not exist at {plot_path}")
        self.assertGreater(os.path.getsize(plot_path), 1000, "Generated PNG should be a non-empty image")

        stats = res.get("stats", {})
        self.assertGreater(stats.get("rows", 0), 0)

        voice = res.get("voice_response", "")
        self.assertTrue(len(voice) > 20)
        # Ensure statistical breakdown is spoken
        self.assertTrue(
            any(k in voice.lower() for k in ["mean", "max", "min", "growth", "change", "analyzed", "peak"]),
            f"Voice response should include statistical insights: {voice}"
        )

        # Also verify end-to-end routing via LocalLLM.plan
        plan_res = self.llm.plan(prompt, dry_run=True)
        self.assertEqual(plan_res.get("action"), "data_science")
        self.assertIsNotNone(plan_res.get("hud_card"))

    def test_2_interactive_hud_contract(self):
        """
        Test 2 (Interactive HUD Contract):
        Verify ui/orb/index.html contains window.updateHUDCard and window.setOrbState,
        and verify ui/gui.py defines hud_update_signal and orb_state_signal.
        """
        orb_html_path = os.path.join(PROJECT_ROOT, "ui", "orb", "index.html")
        self.assertTrue(os.path.isfile(orb_html_path))
        with open(orb_html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        self.assertIn("window.updateHUDCard", html_content)
        self.assertIn("window.setOrbState", html_content)
        self.assertIn("hud-left", html_content)
        self.assertIn("hud-right", html_content)

        gui_py_path = os.path.join(PROJECT_ROOT, "ui", "gui.py")
        self.assertTrue(os.path.isfile(gui_py_path))
        with open(gui_py_path, "r", encoding="utf-8") as f:
            gui_content = f.read()

        self.assertIn("hud_update_signal", gui_content)
        self.assertIn("orb_state_signal", gui_content)

    def test_3_forged_skill_unit_test_verifier(self):
        """
        Test 3 (Forged Skill Unit-Test Verifier):
        Forge a skill via SkillForge.create_skill(), verify test_skill.py is auto-generated
        and executed, and verify test_passed == True.
        """
        res = self.skill_forge.create_skill(
            "Create a new skill called System Uptime Check that checks how long my PC has been running",
            dry_run=False
        )
        self.assertEqual(res.get("status"), "success")
        self.assertTrue(res.get("test_passed"), f"Auto-generated skill unit test failed: {res.get('test_output')}")
        test_file = res.get("test_file")
        self.assertIsNotNone(test_file)
        self.assertTrue(os.path.isfile(test_file), f"Expected test_skill.py at {test_file}")

    def test_4_idle_daemon_maintenance_cycle(self):
        """
        Test 4 (Idle Daemon Maintenance Cycle):
        Simulate idle_seconds = 1000, run IdleTaskDaemon.run_maintenance_cycle(dry_run=True),
        and verify all 4 maintenance tasks report completion.
        """
        self.idle_daemon.set_simulated_idle(1000.0)
        self.assertGreaterEqual(self.idle_daemon.get_idle_seconds(), 900.0)

        cycle_res = self.idle_daemon.run_maintenance_cycle(dry_run=True)
        self.assertEqual(cycle_res.get("status"), "completed")
        tasks = cycle_res.get("tasks_completed", [])
        self.assertEqual(len(tasks), 4, f"Expected 4 maintenance tasks, got: {tasks}")
        self.assertIn("game_and_file_index_refresh", tasks)
        self.assertIn("memory_and_context_compaction", tasks)
        self.assertIn("temp_plot_and_log_rotation", tasks)
        self.assertIn("thermal_and_ram_guard", tasks)

    def test_5_idle_daemon_active_user_guard(self):
        """
        Test 5 (Idle Daemon Active User Guard):
        Call record_user_activity(), verify get_idle_seconds() < 5, and verify
        run_maintenance_cycle() immediately skips execution when the user is active.
        """
        self.idle_daemon.record_user_activity()
        idle_sec = self.idle_daemon.get_idle_seconds()
        self.assertLess(idle_sec, 5.0)

        skip_res = self.idle_daemon.run_maintenance_cycle(dry_run=True)
        self.assertEqual(skip_res.get("status"), "skipped")
        self.assertEqual(skip_res.get("reason"), "user_active")
        self.assertEqual(len(skip_res.get("tasks_completed", [])), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
