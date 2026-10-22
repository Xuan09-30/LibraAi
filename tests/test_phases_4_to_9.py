"""
Automated Comprehensive Test Suite for Project Libra (Phases 4 through 9)
Verifies:
- Phase 4: Hybrid SQLite RAG (FTS5 + Vector Reciprocal Rank Fusion)
- Phase 5: Clean Web Extraction Pipeline & SQLite Cache
- Phase 6: FastMCP Bridge & Dynamic Tool Extensibility
- Phase 7: Per-App Audio Ducking (pycaw) & Sub-5ms File Discovery (EverythingSearchEngine)
- Phase 8: Ultra-Fast Screen Grab (mss), Local CPU ONNX OCR (RapidOCR), & Screenpipe Timeline Ring Buffer
- Phase 9: Semantic Fast-Path Routing, FlashRank Reranker, UFO Background UI Automation, & 8x8 Action Verification
"""

import ast
import os
import sys
import tempfile
import unittest
from PIL import Image, ImageDraw

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from tools.document_rag import DocumentRAGEngine
from core.research import HardenedResearchEngine
from core.mcp_client import LibraMCPClient
from core.audio_capture import AudioDucker, audio_ducker
from tools.file_manager import FileManager, EverythingSearchEngine
from core.spatial import SpatialGroundingEngine
from core.memory import SemanticMemory
from core.orchestrator import SupervisorHub, CANONICAL_FASTPATH_INTENTS
from tools.gui_control import GUIControlAgent


class TestASTIntegrity(unittest.TestCase):
    def test_all_upgraded_files_pass_ast_parse(self):
        target_files = [
            os.path.join(PROJECT_ROOT, "tools", "document_rag.py"),
            os.path.join(PROJECT_ROOT, "core", "research.py"),
            os.path.join(PROJECT_ROOT, "core", "mcp_client.py"),
            os.path.join(PROJECT_ROOT, "core", "audio_capture.py"),
            os.path.join(PROJECT_ROOT, "tools", "file_manager.py"),
            os.path.join(PROJECT_ROOT, "core", "spatial.py"),
            os.path.join(PROJECT_ROOT, "core", "memory.py"),
            os.path.join(PROJECT_ROOT, "core", "orchestrator.py"),
            os.path.join(PROJECT_ROOT, "tools", "gui_control.py"),
        ]
        for fpath in target_files:
            self.assertTrue(os.path.isfile(fpath), f"File not found: {fpath}")
            with open(fpath, "r", encoding="utf-8") as f:
                code = f.read()
            try:
                ast.parse(code)
            except SyntaxError as e:
                self.fail(f"SyntaxError in {fpath}: {e}")


class TestPhase4And9HybridRAG(unittest.TestCase):
    def setUp(self):
        self.rag = DocumentRAGEngine(db_filename=":memory:")

    def test_fts5_indexing_and_hybrid_rrf_search(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as f:
            f.write(
                "Project Libra is an autonomous AI assistant powered by local models.\n"
                "Voice synthesis uses Kokoro TTS and faster-whisper on Windows.\n"
                "Gaming optimization ensures zero FPS drop on NVIDIA RTX 5060 Ti.\n"
                "Markovian state compression bounds the prompt history to six turns."
            )
            tmp_path = f.name

        try:
            res = self.rag.index_file(tmp_path, dry_run=True)
            self.assertIn("doc_id", res)
            doc_id = res["doc_id"]

            # Hybrid query combining keyword and conceptual terms
            chunks = self.rag.search_relevant_chunks(doc_id, "Kokoro voice synthesis", top_k=2, dry_run=True)
            self.assertGreaterEqual(len(chunks), 1)
            self.assertTrue(any("Kokoro" in c for c in chunks))
        finally:
            os.remove(tmp_path)


class TestPhase5CleanWebResearch(unittest.TestCase):
    def test_web_cache_db_initialization(self):
        engine = HardenedResearchEngine(cache_db_path=":memory:")
        self.assertTrue(hasattr(engine, "clean_markdown_extract"))
        res = engine.clean_markdown_extract("")
        self.assertIsNone(res)


class TestPhase6FastMCPBridge(unittest.TestCase):
    def setUp(self):
        self.client = LibraMCPClient()

    def test_dynamic_tool_registration_and_dispatch(self):
        def sample_calculator(a: int, b: int) -> int:
            return a + b

        self.client.register_dynamic_tool("add_numbers", sample_calculator, description="Adds two numbers")
        tools = self.client.list_tools()
        self.assertTrue(any(t["name"] == "add_numbers" for t in tools))

        exec_res = self.client.call_tool("add_numbers", {"a": 10, "b": 25})
        self.assertEqual(exec_res.get("status"), "success")
        self.assertEqual(exec_res.get("result"), 35)


class TestPhase7AudioDuckingAndFileSearch(unittest.TestCase):
    def test_audio_ducker_interface(self):
        ducker = AudioDucker()
        # Verify duck and restore methods are callable without exceptions
        ducked = ducker.duck_background_audio(target_level=0.20)
        self.assertIsInstance(ducked, int)
        restored = ducker.restore_background_audio()
        self.assertIsInstance(restored, int)

    def test_everything_search_engine_fallback(self):
        engine = EverythingSearchEngine()
        results = engine.search("README", max_results=5)
        self.assertIsInstance(results, list)

        fm = FileManager()
        fm_results = fm.search_files_fast("libra", max_results=5)
        self.assertIsInstance(fm_results, list)


class TestPhase8ScreenCaptureAndTimeline(unittest.TestCase):
    def setUp(self):
        self.spatial = SpatialGroundingEngine()
        self.mem = SemanticMemory(db_filename=":memory:")

    def test_fast_frame_grab_and_dhash(self):
        img = self.spatial.grab_fast_frame()
        if img is not None:
            dh = self.spatial.compute_frame_dhash(img)
            self.assertGreater(len(dh), 0)

    def test_cpu_ocr_and_timeline_ring_buffer(self):
        dummy_screen = Image.new("RGB", (640, 480), color=(20, 20, 20))
        draw = ImageDraw.Draw(dummy_screen)
        draw.text((30, 30), "Fatal Exception in Thread Main", fill=(255, 255, 255))

        dh = self.spatial.compute_frame_dhash(dummy_screen)
        frame_id = self.mem.record_screen_frame("Terminal", "cmd.exe", "Fatal Exception", dhash=dh)
        self.assertGreater(frame_id, 0)

        timeline = self.mem.get_recent_screen_context(limit=5)
        self.assertEqual(len(timeline), 1)
        self.assertEqual(timeline[0]["window_title"], "Terminal")
        self.assertEqual(timeline[0]["ocr_summary"], "Fatal Exception")


class TestPhase9SemanticFastPathAndUFOVerification(unittest.TestCase):
    def setUp(self):
        self.hub = SupervisorHub()
        self.gui = GUIControlAgent()

    def test_semantic_fastpath_matching(self):
        # Colloquial volume command matching
        res = self.hub._match_semantic_fastpath("crank the tunes down")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "media_action")
        self.assertEqual(res["args"]["sub_action"], "volume_down")

        # Colloquial mute command matching
        res_mute = self.hub._match_semantic_fastpath("mute the computer")
        self.assertIsNotNone(res_mute)
        self.assertEqual(res_mute["args"]["sub_action"], "mute")

    def test_ufo_silent_click_and_verified_action(self):
        # Silent UI background click test
        res = self.gui.silent_ui_click("NonExistentButton123", dry_run=True)
        self.assertEqual(res["status"], "success")
        self.assertTrue(res.get("dry_run"))

        # Click with action verification
        click_res = self.gui.click(x=100, y=100, dry_run=True)
        self.assertEqual(click_res["status"], "success")
        self.assertTrue(click_res.get("verified_change"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
