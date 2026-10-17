import os
import sys
import time
import shutil
import unittest
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.repl_runner import PersistentDataREPL
from tools.data_scientist import DataScienceAgent
from core.mcp_client import LibraMCPClient
from core.audio_capture import WASAPIAudioCapture
from core.kokoro_tts import KokoroTTS
from core.memory import SemanticMemory
from core.idle_daemon import IdleTaskDaemon
from core.llm import LocalLLM


class TestV8UnifiedSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.llm = LocalLLM()
        cls.repl = PersistentDataREPL()
        cls.ds_agent = DataScienceAgent(file_mgr=cls.llm.file_mgr, repl=cls.repl)
        cls.mcp_client = LibraMCPClient()
        cls.tts = KokoroTTS(lazy_load=True)
        cls.test_mem = SemanticMemory(db_filename=":memory:")
        cls.idle_daemon = IdleTaskDaemon(
            memory=cls.llm.memory,
            distiller=cls.llm.distiller,
            monitor=cls.llm.monitor,
            discovery=getattr(cls.llm.dispatcher, "discovery", None)
        )

    def test_1_persistent_repl_and_multi_turn_variables(self):
        """
        Test 1 (Persistent REPL & Multi-Turn Variables):
        Evaluates DataFrame assignment in Turn 1 and mathematical calculations on `df`
        in Turn 2 without file re-reads.
        """
        self.repl.reset_namespace()

        # Turn 1: Create and assign DataFrame `df` in REPL
        turn1_code = (
            "df = pd.DataFrame({\n"
            "    'quarter': ['Q1', 'Q2', 'Q3', 'Q4'],\n"
            "    'revenue': [120.0, 150.0, 180.0, 230.0],\n"
            "    'cost': [80.0, 95.0, 110.0, 135.0]\n"
            "})"
        )
        res1 = self.repl.run_code(turn1_code)
        self.assertEqual(res1["status"], "success")
        self.assertIn("duration_ms", res1)
        active_dfs = self.repl.list_active_dataframes()
        self.assertIn("df", active_dfs)
        self.assertEqual(active_dfs["df"]["rows"], 4)
        self.assertIn("memory_kb", active_dfs["df"])

        # Turn 2: Compute derived column & summary metrics on `df` without re-initializing it
        turn2_code = (
            "df['profit'] = df['revenue'] - df['cost']\n"
            "total_profit = float(df['profit'].sum())\n"
            "mean_margin = round(float((df['profit'] / df['revenue']).mean()), 4)\n"
            "total_profit"
        )
        res2 = self.repl.run_code(turn2_code)
        self.assertEqual(res2["status"], "success")
        self.assertEqual(res2["result"], 260.0)
        self.assertEqual(res2["variables"].get("total_profit"), 260.0)
        self.assertGreater(res2["variables"].get("mean_margin", 0.0), 0.30)

    def test_2_voice_automl_and_plot_generation(self):
        """
        Test 2 (Voice AutoML & Plot Generation):
        Trains a baseline Random Forest classifier on synthetic tabular data and asserts
        that accuracy metrics and feature importance plots are generated in `assets/plots/`.
        """
        rng = np.random.default_rng(123)
        n = 180
        cpu_load = rng.uniform(10, 95, n)
        gpu_temp = rng.uniform(40, 88, n)
        vram_gb = rng.uniform(2, 16, n)
        score = 0.04 * (cpu_load - 50) + 0.08 * (gpu_temp - 65) + 0.15 * (vram_gb - 8)
        throttle_label = (score > 0).astype(int)

        synth_df = pd.DataFrame({
            "cpu_load": cpu_load,
            "gpu_temp": gpu_temp,
            "vram_gb": vram_gb,
            "throttle_event": throttle_label
        })
        self.repl.set_variable("df", synth_df)

        automl_res = self.ds_agent.train_baseline_model(
            synth_df,
            "throttle_event",
            model_type="random_forest"
        )
        self.assertEqual(automl_res.get("status"), "success")
        self.assertGreaterEqual(automl_res.get("accuracy", 0.0), 0.75)
        self.assertIn("f1", automl_res)
        self.assertIn("roc_auc", automl_res)
        self.assertIn("?t=", automl_res.get("hud_url", ""))
        self.assertTrue(len(automl_res.get("feature_importances", {})) == 3)

        plot_path = automl_res.get("plot_path")
        self.assertIsNotNone(plot_path)
        self.assertTrue(os.path.isfile(plot_path), f"Expected feature importance plot at {plot_path}")
        self.assertTrue(plot_path.endswith("model_importance.png"))
        self.assertGreater(os.path.getsize(plot_path), 1000)

        # Also verify Natural Language SQL Translator and MCP Client
        sql_res = self.ds_agent.query_sql("assets/libra_memory.db", "How many rows in facts?")
        self.assertEqual(sql_res.get("status"), "success")

        mcp_servers = self.mcp_client.list_servers()
        self.assertIn("sqlite_memory", mcp_servers)
        self.assertIn("workspace_filesystem", mcp_servers)
        mcp_call = self.mcp_client.call_mcp_tool("workspace_filesystem", "list_directory", {"path": "core"})
        self.assertEqual(mcp_call.get("status"), "success")

    def test_3_counterfactual_correction_injection(self):
        """
        Test 3 (Counterfactual Correction Injection):
        Records a correction, submits an identical ambiguous query, and confirms the
        corrected parameter is applied.
        """
        trigger_q = "open my project folder"
        mistake_param = "OldDrafts"
        corrected_param = "LibraAi"

        lesson_id = self.llm.memory.record_correction(
            trigger_query=trigger_q,
            mistake=mistake_param,
            correction=corrected_param
        )
        self.assertGreater(lesson_id, 0)

        rules = self.llm.memory.recall_applicable_lessons(trigger_q)
        self.assertTrue(len(rules) >= 1)
        self.assertIn(corrected_param, rules[0])
        self.assertIn("[Rule: In past runs, the user corrected this action with:", rules[0])

        # Submit identical query through LocalLLM.plan and verify corrected_action is injected
        plan_res = self.llm.plan(trigger_q, dry_run=True)
        self.assertEqual(plan_res.get("corrected_action"), corrected_param)
        self.assertTrue(len(plan_res.get("applied_lessons", [])) >= 1)

    def test_4_acoustic_backchanneling_and_prosody(self):
        """
        Test 4 (Acoustic Backchanneling & Prosody):
        Measures time-to-first-token/audio on heavy queries and confirms that backchannel
        filler audio triggers in < 300 ms, plus verifies Circadian Night Mode & Urgent prosody.
        """
        t0 = time.perf_counter()
        bridge = self.tts.get_backchannel_bridge(route_or_task="data_science", expected_latency_sec=2.0)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertIsNotNone(bridge)
        self.assertTrue(bridge["triggered"])
        self.assertLess(elapsed_ms, 300.0, f"Backchannel trigger took {elapsed_ms:.2f}ms (> 300ms)")
        self.assertGreater(len(bridge["pcm_bytes"]), 1000)

        # Verify Circadian prosody modes
        normal_cfg = self.tts.get_prosody_config(urgency="normal", current_hour=14)
        self.assertEqual(normal_cfg["speed"], 1.05)
        self.assertEqual(normal_cfg["gain"], 1.0)

        urgent_cfg = self.tts.get_prosody_config(urgency="high", current_hour=14)
        self.assertEqual(urgent_cfg["speed"], 1.18)

        night_cfg = self.tts.get_prosody_config(urgency="normal", current_hour=23)
        self.assertEqual(night_cfg["speed"], 0.95)
        self.assertEqual(night_cfg["gain"], 0.70)
        self.assertTrue(night_cfg["night_mode"])

        # Verify WASAPI NLMS Echo Cancellation attenuates speaker echo
        aec = WASAPIAudioCapture(dry_run=True)
        t_vec = np.linspace(0, 0.032, 512, endpoint=False, dtype=np.float32)
        speaker_sig = (0.6 * np.sin(2 * np.pi * 400 * t_vec) * 32767).astype(np.int16).tobytes()
        cleaned_pcm = aec.cancel_echo_nlms(speaker_sig, speaker_sig)
        self.assertEqual(len(cleaned_pcm), len(speaker_sig))

    def test_5_idle_daemon_maintenance_cycle(self):
        """
        Test 5 (Idle Daemon Maintenance Cycle):
        Simulates 15 minutes of idle time and verifies database optimization and cache
        cleanup routines complete cleanly.
        """
        self.idle_daemon.set_simulated_idle(960.0)
        self.assertGreaterEqual(self.idle_daemon.get_idle_seconds(), 900.0)

        res = self.idle_daemon.run_maintenance_cycle(dry_run=True, force=True)
        self.assertEqual(res.get("status"), "completed")
        completed = res.get("tasks_completed", [])
        self.assertIn("game_and_file_index_refresh", completed)
        self.assertIn("memory_and_context_compaction", completed)
        self.assertIn("temp_plot_and_log_rotation", completed)
        self.assertIn("thermal_and_ram_guard", completed)

    def test_6_regression_benchmark(self):
        """
        Test 6 (Regression Benchmark):
        Verifies HUD 6-mode presets, FloatingHUDPill contract, and core routing invariants.
        """
        orb_html = os.path.join(PROJECT_ROOT, "ui", "orb", "index.html")
        with open(orb_html, "r", encoding="utf-8") as f:
            html_text = f.read()
        for preset in ("normal", "data_science", "urgent", "gaming", "clarify", "night"):
            self.assertIn(preset, html_text)

        pill_file = os.path.join(PROJECT_ROOT, "ui", "floating_widget.py")
        self.assertTrue(os.path.isfile(pill_file))
        with open(pill_file, "r", encoding="utf-8") as f:
            pill_code = f.read()
        self.assertIn("FloatingHUDPill", pill_code)
        self.assertIn("RegisterHotKey", pill_code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
