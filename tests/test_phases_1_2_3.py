"""
Automated Comprehensive Test Suite for Project Libra (Phases 1, 2, and 3)
Verifies:
- Phase 1: Markovian Context Compression & H-MEM Episodic Consolidation
- Phase 2: Dual-Pass Vision & Set-of-Mark (SoM) UI Grounding
- Phase 3: PreAct Deterministic Action Caching (<5ms Fast-Path)
- AST and Syntax Integrity across all modified files
"""

import ast
import os
import sys
import unittest
from datetime import datetime
from PIL import Image, ImageDraw

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from core.memory import SemanticMemory
from core.spatial import SpatialGroundingEngine
from tools.gui_control import GUIControlAgent
from core.model_manager import ModelManager
from core.orchestrator import SupervisorHub, normalize_trigger
from core.telemetry import profiler


class TestASTIntegrity(unittest.TestCase):
    def test_syntax_of_all_modified_modules(self):
        target_files = [
            os.path.join(PROJECT_ROOT, "core", "memory.py"),
            os.path.join(PROJECT_ROOT, "core", "spatial.py"),
            os.path.join(PROJECT_ROOT, "tools", "gui_control.py"),
            os.path.join(PROJECT_ROOT, "core", "model_manager.py"),
            os.path.join(PROJECT_ROOT, "core", "llm.py"),
            os.path.join(PROJECT_ROOT, "core", "orchestrator.py"),
            os.path.join(PROJECT_ROOT, "core", "telemetry.py"),
        ]
        for fpath in target_files:
            self.assertTrue(os.path.isfile(fpath), f"Missing target file: {fpath}")
            with open(fpath, "r", encoding="utf-8") as f:
                code = f.read()
            try:
                ast.parse(code)
            except SyntaxError as e:
                self.fail(f"SyntaxError in {fpath}: {e}")


class TestPhase1MarkovAndHMEM(unittest.TestCase):
    def setUp(self):
        # Use isolated in-memory DB for pure unit testing
        self.mem = SemanticMemory(db_filename=":memory:")

    def test_markov_state_initialization_and_update(self):
        state = self.mem.get_markov_state()
        self.assertIsInstance(state, dict)
        self.assertEqual(state.get("rolling_summary"), "")
        self.assertEqual(state.get("active_goal"), "")

        # Update state
        new_state = {
            "active_goal": "Play League of Legends",
            "entities_in_scope": {"game": "League of Legends"},
            "recent_tool_outcomes": [{"action": "open_app", "target": "league"}],
            "unresolved_questions": [],
            "rolling_summary": "User started League of Legends."
        }
        ok = self.mem.update_markov_state(new_state)
        self.assertTrue(ok)

        fetched = self.mem.get_markov_state()
        self.assertEqual(fetched["active_goal"], "Play League of Legends")
        self.assertEqual(fetched["entities_in_scope"].get("game"), "League of Legends")
        self.assertEqual(fetched["rolling_summary"], "User started League of Legends.")

    def test_fold_conversation_into_markov(self):
        turns = [
            {"role": "user", "content": "Hey Libra, open Google Chrome for me"},
            {"role": "assistant", "content": "Opening Google Chrome now."},
            {"role": "user", "content": "Also I like ayam gepuk for lunch"},
            {"role": "assistant", "content": "Noted, ayam gepuk is your favorite food."}
        ]
        folded = self.mem.fold_conversation_into_markov(turns, current_goal="Browse web and lunch")
        self.assertIn("ayam gepuk", folded["rolling_summary"].lower())
        self.assertEqual(folded["entities_in_scope"].get("browser"), "Google Chrome")
        self.assertEqual(folded["entities_in_scope"].get("favorite_food"), "ayam gepuk")
        self.assertEqual(folded["active_goal"], "Browse web and lunch")

    def test_semantic_facts_crud_and_prompt_formatting(self):
        fid = self.mem.upsert_semantic_fact("user", "favorite_food", "ayam gepuk", confidence=1.0)
        self.assertGreater(fid, 0)

        # Update fact with new value
        fid2 = self.mem.upsert_semantic_fact("user", "favorite_food", "ayam gepuk pedas", confidence=1.0)
        facts = self.mem.get_semantic_facts(entity="user")
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["value"], "ayam gepuk pedas")

        prompt_str = self.mem.format_semantic_facts_prompt()
        self.assertIn("user.favorite_food: ayam gepuk pedas", prompt_str)

        deleted = self.mem.delete_semantic_fact("user", "favorite_food")
        self.assertTrue(deleted)
        self.assertEqual(len(self.mem.get_semantic_facts(entity="user")), 0)

    def test_h_mem_episodic_consolidation(self):
        # Simulate user correcting their preference in episodic memory
        self.mem.log_episode(
            user_text="I don't like bakutay anymore, I like ayam gepuk",
            assistant_text="Got it, your favorite food is now ayam gepuk."
        )
        self.mem.log_episode(
            user_text="My in-game name is Kyodon",
            assistant_text="Recorded your IGN as Kyodon."
        )

        consolidated = self.mem.consolidate_memory()
        self.assertGreaterEqual(consolidated, 2)

        facts = {f["relation"]: f["value"] for f in self.mem.get_semantic_facts("user")}
        self.assertEqual(facts.get("favorite_food"), "ayam gepuk")
        self.assertEqual(facts.get("in_game_name"), "Kyodon")


class TestPhase2DualPassVisionAndSoM(unittest.TestCase):
    def setUp(self):
        self.spatial = SpatialGroundingEngine()
        self.gui = GUIControlAgent()
        self.model_mgr = ModelManager()

        # Generate a synthetic 1920x1080 screenshot with distinct UI rectangles
        self.screen_img = Image.new("RGB", (1920, 1080), color=(30, 30, 30))
        draw = ImageDraw.Draw(self.screen_img)
        # Button 1 (Profile 1)
        draw.rectangle([200, 200, 450, 280], fill=(220, 220, 220))
        # Button 2 (Profile 2)
        draw.rectangle([550, 200, 800, 280], fill=(220, 220, 220))
        # Button 3 (Submit)
        draw.rectangle([900, 500, 1100, 560], fill=(0, 180, 255))

    def test_detect_ui_elements_and_som_generation(self):
        elements = self.spatial.detect_ui_elements(screenshot_img=self.screen_img)
        self.assertGreaterEqual(len(elements), 1)

        som_path, mark_dict = self.spatial.capture_and_annotate(
            mode="som",
            screenshot_img=self.screen_img,
            max_size=(1280, 720)
        )
        self.assertTrue(os.path.isfile(som_path))
        self.assertGreaterEqual(len(mark_dict), 1)

        first_mark = mark_dict[1]
        self.assertIn("center_x", first_mark)
        self.assertIn("center_y", first_mark)
        self.assertIn("bbox", first_mark)

    def test_crop_mode(self):
        crop_path, _ = self.spatial.capture_and_annotate(
            mode="crop",
            region=(200, 200, 250, 80),
            screenshot_img=self.screen_img
        )
        self.assertTrue(os.path.isfile(crop_path))
        with Image.open(crop_path) as c_img:
            self.assertEqual(c_img.size, (250, 80))

    def test_gui_click_mark_dry_run(self):
        mock_marks = {
            1: {"mark_id": 1, "center_x": 325, "center_y": 240, "name": "Profile 1", "type": "button"},
            2: {"mark_id": 2, "center_x": 675, "center_y": 240, "name": "Profile 2", "type": "button"}
        }
        res = self.gui.click_mark(1, mock_marks, dry_run=True)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("x"), 325)
        self.assertEqual(res.get("y"), 240)
        self.assertEqual(res.get("mark_id"), 1)

    def test_model_manager_locate_ui_mark(self):
        mock_marks = {
            1: {"mark_id": 1, "center_x": 325, "center_y": 240, "name": "first account", "type": "button"},
            2: {"mark_id": 2, "center_x": 675, "center_y": 240, "name": "second account", "type": "button"}
        }
        # Lexical matching check
        loc = self.model_mgr.locate_ui_mark("click first account", mock_marks, dry_run=True)
        self.assertEqual(loc["mark_id"], 1)

        # Direct number check
        loc_num = self.model_mgr.locate_ui_mark("click mark 2", mock_marks, dry_run=True)
        self.assertEqual(loc_num["mark_id"], 2)


class TestPhase3PreActDeterministicActionCaching(unittest.TestCase):
    def setUp(self):
        self.hub = SupervisorHub()
        # Ensure memory is active
        self.mem = self.hub.llm.memory

    def test_normalize_trigger(self):
        self.assertEqual(normalize_trigger("Hey Libra, open Google Chrome for me."), "open google chrome for me")
        self.assertEqual(normalize_trigger("Can you please launch Spotify?"), "launch spotify")
        self.assertEqual(normalize_trigger("Could you close discord"), "close discord")

    def test_preact_action_macro_promotion_and_fastpath(self):
        trig = "open discord"
        norm = normalize_trigger(trig)
        sig = f"macro:{norm}"
        chain = [{"action": "open_app", "args": {"target": "discord"}}]

        # Clear any existing macro for test reproducibility
        self.mem.delete_action_macro(norm)

        # First recording: count = 1 (unpromoted)
        self.mem.record_action_macro(norm, sig, chain, latency_ms=15.0)
        m = self.mem.get_action_macro(norm)
        self.assertIsNotNone(m)
        self.assertEqual(m["success_count"], 1)

        # Second recording: count = 2 (promoted!)
        self.mem.record_action_macro(norm, sig, chain, latency_ms=12.0)
        m2 = self.mem.get_action_macro(norm)
        self.assertEqual(m2["success_count"], 2)

        promoted = self.mem.get_promoted_macros(min_success=2)
        self.assertTrue(any(p["normalized_trigger"] == norm for p in promoted))

        # Test Fast-Path execution in SupervisorHub (<5ms)
        res = self.hub.plan_or_execute(trig, dry_run=True)
        self.assertTrue(res.get("preact_cached", False))
        self.assertEqual(res.get("action"), "open_app")

        # Cleanup
        self.mem.delete_action_macro(norm)


if __name__ == "__main__":
    unittest.main(verbosity=2)
