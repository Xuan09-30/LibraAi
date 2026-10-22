"""
=============================================================================
TEST SUITE: TAILSCALE PWA, GEMINI-STYLE MULTI-CHAT THREADS & TOKEN TELEMETRY
Target: tests/test_web_sessions_and_tokens.py
Phase 10: Multi-session CRUD, Token Metrics Extraction, Tailscale Auth & UI
=============================================================================
"""

import os
import sys
import unittest
import json
import time
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.orchestrator import SupervisorHub
from core.llm import LocalLLM
from core.memory import MemoryCore
from core.version import LIBRA_VERSION
from web.server import create_app, load_web_config


class TestWebSessionsAndTokens(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.llm = LocalLLM()
        cls.hub = SupervisorHub(cls.llm)
        cls.cfg = load_web_config("config.json")
        cls.admin_email = cls.cfg.get("admin_email", "chenxuanchuah@gmail.com")
        cls.token = cls.cfg.get("access_token", "libra_access_token_phase10_secure")
        cls.app = create_app(hub=cls.hub, config_path="config.json")
        cls.client = TestClient(cls.app)
        cls.auth_headers = {"Authorization": f"Bearer {cls.token}"}

    # -----------------------------------------------------------------------
    # 1. TAILSCALE AUTHENTICATION TESTS
    # -----------------------------------------------------------------------
    def test_01_tailscale_serve_headers(self):
        """Test Tailscale-User-Login header authentication."""
        # Allowed Tailscale admin email
        ts_headers = {
            "Tailscale-User-Login": self.admin_email,
            "Tailscale-User-Name": "Chen Xuan"
        }
        res_ok = self.client.get("/api/vitals", headers=ts_headers)
        self.assertEqual(res_ok.status_code, 200)

        # Stranger Tailscale login should be rejected with 403 Forbidden
        ts_bad_headers = {
            "Tailscale-User-Login": "attacker@tailscale.net",
            "Tailscale-User-Name": "Attacker"
        }
        res_bad = self.client.get("/api/vitals", headers=ts_bad_headers)
        self.assertEqual(res_bad.status_code, 403)

    # -----------------------------------------------------------------------
    # 2. GEMINI-STYLE MULTI-CHAT SESSIONS (CRUD)
    # -----------------------------------------------------------------------
    def test_02_create_and_list_sessions(self):
        """Test creating new conversation threads and listing them."""
        # Create a new session
        create_payload = {"title": "Quantum Physics Research", "client_scope": "remote_web"}
        res_create = self.client.post("/api/sessions/new", json=create_payload, headers=self.auth_headers)
        self.assertEqual(res_create.status_code, 200)
        data = res_create.json()
        self.assertEqual(data.get("status"), "success")
        self.assertIn("session_id", data)
        session_id = data["session_id"]
        self.assertEqual(data.get("title"), "Quantum Physics Research")

        # List sessions and verify new thread is present
        res_list = self.client.get("/api/sessions", headers=self.auth_headers)
        self.assertEqual(res_list.status_code, 200)
        list_data = res_list.json()
        self.assertEqual(list_data.get("status"), "success")
        sessions = list_data.get("sessions", [])
        found = any(s["session_id"] == session_id for s in sessions)
        self.assertTrue(found, f"Session {session_id} not found in session list")

    def test_03_rename_and_get_session(self):
        """Test renaming a chat thread and retrieving its details and messages."""
        # Create session
        res_create = self.client.post(
            "/api/sessions/new",
            json={"title": "Draft Topic", "client_scope": "remote_web"},
            headers=self.auth_headers
        )
        session_id = res_create.json()["session_id"]

        # Rename thread
        res_rename = self.client.patch(
            f"/api/sessions/{session_id}",
            json={"title": "Autonomous Drone Fleet"},
            headers=self.auth_headers
        )
        self.assertEqual(res_rename.status_code, 200)
        self.assertEqual(res_rename.json().get("title"), "Autonomous Drone Fleet")

        # Get session details
        res_get = self.client.get(f"/api/sessions/{session_id}", headers=self.auth_headers)
        self.assertEqual(res_get.status_code, 200)
        get_data = res_get.json()
        self.assertEqual(get_data.get("status"), "success")
        self.assertEqual(get_data["session"]["title"], "Autonomous Drone Fleet")
        self.assertIsInstance(get_data["messages"], list)

    def test_04_delete_session(self):
        """Test deleting a chat thread."""
        res_create = self.client.post(
            "/api/sessions/new",
            json={"title": "Temporary Thread to Delete"},
            headers=self.auth_headers
        )
        session_id = res_create.json()["session_id"]

        # Delete session
        res_del = self.client.delete(f"/api/sessions/{session_id}", headers=self.auth_headers)
        self.assertEqual(res_del.status_code, 200)
        self.assertEqual(res_del.json().get("status"), "success")

        # Verify not in list
        res_list = self.client.get("/api/sessions", headers=self.auth_headers)
        sessions = res_list.json().get("sessions", [])
        self.assertFalse(any(s["session_id"] == session_id for s in sessions))

    def test_05_auto_titling_logic(self):
        """Test MemoryCore.generate_thread_title generates concise title-cased titles."""
        memory = self.hub.llm.memory
        title1 = memory.generate_thread_title("Hey Libra, can you explain quantum computing to me?")
        self.assertTrue(len(title1.split()) <= 6)
        self.assertNotIn("Hey", title1)
        self.assertNotIn("Libra", title1)

        title2 = memory.generate_thread_title("how to write a binary search algorithm in python")
        self.assertTrue(len(title2.split()) <= 6)
        self.assertIn("Binary Search", title2)

    # -----------------------------------------------------------------------
    # 3. REAL-TIME TOKEN ACCOUNTING & METRICS TELEMETRY
    # -----------------------------------------------------------------------
    def test_06_token_summary_endpoint(self):
        """Test GET /api/tokens/summary returns all 4 metric breakdown cards."""
        res_create = self.client.post(
            "/api/sessions/new",
            json={"title": "Token Test Thread"},
            headers=self.auth_headers
        )
        session_id = res_create.json()["session_id"]

        # Add mock session messages directly to memory with known tokens
        memory = self.hub.llm.memory
        memory.add_session_message(
            session_id=session_id,
            role="user",
            content="Hello token counter",
            input_tokens=15,
            output_tokens=0,
            tokens_per_sec=0.0,
            model_used="qwen3:8b",
            latency_ms=10
        )
        memory.add_session_message(
            session_id=session_id,
            role="assistant",
            content="Greetings! Telemetry operational.",
            input_tokens=15,
            output_tokens=32,
            tokens_per_sec=45.2,
            model_used="qwen3:8b",
            latency_ms=710,
            saved_tokens=350
        )

        # Query token summary endpoint
        res = self.client.get(f"/api/tokens/summary?session_id={session_id}", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json().get("data", {})

        # Verify last_turn metrics
        self.assertIn("last_turn", data)
        self.assertEqual(data["last_turn"]["output_tokens"], 32)
        self.assertAlmostEqual(data["last_turn"]["tokens_per_sec"], 45.2, delta=0.5)

        # Verify active_session metrics
        self.assertIn("active_session", data)
        self.assertEqual(data["active_session"]["session_id"], session_id)
        self.assertGreaterEqual(data["active_session"]["turn_count"], 1)

        # Verify today & saved_tokens metrics
        self.assertIn("today", data)
        self.assertIn("saved_tokens", data)
        self.assertGreaterEqual(data["saved_tokens"]["total_saved"], 350)

    def test_07_fast_path_saved_tokens_telemetry(self):
        """Test fast-path queries report 0 input/output tokens and 350 saved tokens."""
        res = self.hub.process_command("check system vitals", client_scope="remote_web", dry_run=True)
        metrics = res.get("token_metrics", {})
        self.assertTrue(metrics.get("fast_path"))
        self.assertEqual(metrics.get("input_tokens"), 0)
        self.assertEqual(metrics.get("output_tokens"), 0)
        self.assertEqual(metrics.get("saved_tokens"), 350)

    # -----------------------------------------------------------------------
    # 4. CHAT WITH SESSION PERSISTENCE
    # -----------------------------------------------------------------------
    def test_08_post_chat_in_specific_session(self):
        """Test /api/chat logs conversation turns specifically to requested session_id."""
        res_create = self.client.post(
            "/api/sessions/new",
            json={"title": "Multi-turn Thread"},
            headers=self.auth_headers
        )
        session_id = res_create.json()["session_id"]

        chat_payload = {
            "prompt": "What is the boiling point of water in Celsius?",
            "session_id": session_id,
            "client_scope": "remote_web",
            "synthesize_audio": False
        }
        res_chat = self.client.post("/api/chat", json=chat_payload, headers=self.auth_headers)
        self.assertEqual(res_chat.status_code, 200)
        chat_data = res_chat.json()
        self.assertEqual(chat_data.get("session_id"), session_id)
        self.assertIn("token_metrics", chat_data)

        # Verify message persisted in that session
        res_sess = self.client.get(f"/api/sessions/{session_id}", headers=self.auth_headers)
        messages = res_sess.json().get("messages", [])
        self.assertTrue(len(messages) >= 2, "Expected user and assistant messages in session")
        self.assertEqual(messages[0]["content"], chat_payload["prompt"])

    # -----------------------------------------------------------------------
    # 5. GLOBAL H-MEM PERSISTENCE ACROSS SESSIONS
    # -----------------------------------------------------------------------
    def test_09_global_hmem_across_sessions(self):
        """Test long-term semantic facts in MemoryCore remain global across all sessions."""
        memory = self.hub.llm.memory
        memory.store_semantic_fact("User favorite editor", "Antigravity IDE", confidence=1.0)

        # Check retrieval in session A
        facts_a = memory.get_all_semantic_facts()
        found_in_a = any(f.get("fact_key", "").lower() == "user favorite editor" for f in facts_a)
        self.assertTrue(found_in_a)

        # Create session B
        res_b = self.client.post("/api/sessions/new", json={"title": "Session B"}, headers=self.auth_headers)
        sid_b = res_b.json()["session_id"]

        # Fact must still be present and accessible globally
        facts_b = memory.get_all_semantic_facts()
        found_in_b = any(f.get("fact_key", "").lower() == "user favorite editor" for f in facts_b)
        self.assertTrue(found_in_b)

    # -----------------------------------------------------------------------
    # 6. STATIC ASSETS & PWA INTEGRITY
    # -----------------------------------------------------------------------
    def test_10_pwa_static_assets_and_hud_elements(self):
        """Test style.css, app.js, and index.html contain Phase 10 HUD elements."""
        # style.css
        res_css = self.client.get("/static/style.css")
        self.assertEqual(res_css.status_code, 200)
        self.assertIn("#drawer", res_css.text)
        self.assertIn(".token-hud-btn", res_css.text)
        self.assertIn("#token-modal", res_css.text)

        # app.js
        res_js = self.client.get("/static/app.js")
        self.assertEqual(res_js.status_code, 200)
        self.assertIn("fetchSessions", res_js.text)
        self.assertIn("switchSession", res_js.text)
        self.assertIn("fetchTokenSummary", res_js.text)

        # index.html
        res_html = self.client.get("/")
        self.assertEqual(res_html.status_code, 200)
        self.assertIn("token-hud-btn", res_html.text)
        self.assertIn("token-modal", res_html.text)
        self.assertIn("session-list", res_html.text)
        self.assertIn("new-chat-btn", res_html.text)


if __name__ == "__main__":
    unittest.main()
