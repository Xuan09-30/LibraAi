import os
import sys
import unittest
import json
import wave
import io
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.orchestrator import SupervisorHub
from core.llm import LocalLLM
from core.version import LIBRA_VERSION
from web.server import create_app, load_web_config


class TestPhase10WebPWA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.llm = LocalLLM()
        cls.hub = SupervisorHub(cls.llm)
        cls.cfg = load_web_config("config.json")
        cls.admin_email = cls.cfg.get("admin_email", "chenxuanchuah@gmail.com")
        cls.token = cls.cfg.get("access_token", "libra_access_token_phase10_secure")
        cls.app = create_app(hub=cls.hub, config_path="config.json")
        cls.client = TestClient(cls.app)

    # -----------------------------------------------------------------------
    # 1. CLIENT SCOPE SANDBOXING TESTS
    # -----------------------------------------------------------------------
    def test_01_sandboxing_blocks_desktop_actions_in_remote_scope(self):
        """Test 1: Remote web scope blocks OS app launching and mouse control."""
        # Query asking to open app
        q_app = "launch notepad"
        res_remote = self.hub.process_command(q_app, client_scope="remote_web", dry_run=True)
        self.assertEqual(res_remote.get("status"), "blocked")
        self.assertEqual(res_remote.get("action"), "sandboxed_blocked")
        self.assertIn("Remote Web Mode active", res_remote.get("voice_response", ""))

        # Query asking to click on screen
        q_click = "click the green launch button on my screen"
        res_click = self.hub.process_command(q_click, client_scope="remote_web", dry_run=True)
        self.assertEqual(res_click.get("status"), "blocked")
        self.assertIn("Remote Web Mode active", res_click.get("voice_response", ""))

        # Query asking to inspect screen
        q_screen = "look at my screen and tell me what is showing"
        res_screen = self.hub.process_command(q_screen, client_scope="remote_web", dry_run=True)
        self.assertEqual(res_screen.get("status"), "blocked")
        self.assertIn("Remote Web Mode active", res_screen.get("voice_response", ""))

    def test_02_sandboxing_allows_safe_remote_queries(self):
        """Test 2: Remote web scope allows conversational, weather, places, and knowledge queries."""
        # Conversational / General knowledge
        q_chat = "What is the capital of Japan?"
        res_chat = self.hub.process_command(q_chat, client_scope="remote_web", dry_run=True)
        self.assertNotEqual(res_chat.get("status"), "blocked")
        self.assertNotEqual(res_chat.get("action"), "sandboxed_blocked")

        # System status (read-only vitals)
        q_vitals = "check system vitals"
        res_vitals = self.hub.process_command(q_vitals, client_scope="remote_web", dry_run=True)
        self.assertNotEqual(res_vitals.get("status"), "blocked")
        self.assertEqual(res_vitals.get("action"), "system_status")

    def test_03_desktop_scope_remains_unrestricted(self):
        """Test 3: Default local_desktop client_scope allows desktop control without sandboxing."""
        q_app = "launch notepad"
        res_local = self.hub.process_command(q_app, client_scope="local_desktop", dry_run=True)
        self.assertNotEqual(res_local.get("status"), "blocked")
        self.assertEqual(res_local.get("action"), "open_app")

    # -----------------------------------------------------------------------
    # 2. ZERO-TRUST GMAIL & TOKEN AUTHENTICATION TESTS
    # -----------------------------------------------------------------------
    def test_04_auth_unauthorized_rejection(self):
        """Test 4: Unauthenticated request returns 401, wrong email returns 403."""
        # No credentials -> 401 Unauthorized
        res_no_auth = self.client.get("/api/vitals")
        self.assertEqual(res_no_auth.status_code, 401)

        # Stranger email header -> 403 Forbidden
        headers_stranger = {"Cf-Access-Authenticated-User-Email": "stranger@gmail.com"}
        res_stranger = self.client.get("/api/vitals", headers=headers_stranger)
        self.assertEqual(res_stranger.status_code, 403)

    def test_05_auth_authorized_gmail_and_token(self):
        """Test 5: Authorized Gmail and valid Bearer tokens are permitted."""
        # Authorized Gmail via Cloudflare header
        headers_cf = {"Cf-Access-Authenticated-User-Email": self.admin_email}
        res_cf = self.client.get("/api/vitals", headers=headers_cf)
        self.assertEqual(res_cf.status_code, 200)

        # Authorized Gmail via custom header
        headers_custom = {"X-User-Email": self.admin_email}
        res_custom = self.client.get("/api/vitals", headers=headers_custom)
        self.assertEqual(res_custom.status_code, 200)

        # Valid Bearer token
        headers_token = {"Authorization": f"Bearer {self.token}"}
        res_token = self.client.get("/api/vitals", headers=headers_token)
        self.assertEqual(res_token.status_code, 200)

    # -----------------------------------------------------------------------
    # 3. API ENDPOINTS INTEGRATION TESTS
    # -----------------------------------------------------------------------
    def test_06_get_vitals_telemetry(self):
        """Test 6: /api/vitals returns RTX 5060 Ti VRAM and system metrics."""
        headers = {"Authorization": f"Bearer {self.token}"}
        res = self.client.get("/api/vitals", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "online")
        self.assertEqual(data.get("version"), LIBRA_VERSION)
        self.assertIn("vram_used_mb", data)
        self.assertIn("vram_total_mb", data)
        self.assertIn("gpu", data)

    def test_07_post_chat_remote_web(self):
        """Test 7: /api/chat executes prompt under remote_web scope."""
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {
            "prompt": "what is the capital of France?",
            "client_scope": "remote_web",
            "synthesize_audio": False
        }
        res = self.client.post("/api/chat", json=payload, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "success")
        self.assertTrue(len(data.get("reply_text", "")) > 0)
        self.assertEqual(data.get("client_scope"), "remote_web")

    def test_08_post_chat_sandboxing_enforced(self):
        """Test 8: /api/chat enforces desktop sandboxing for remote OS launch commands."""
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {
            "prompt": "please open chrome for me",
            "client_scope": "remote_web"
        }
        res = self.client.post("/api/chat", json=payload, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "blocked")
        self.assertIn("Remote Web Mode active", data.get("reply_text", ""))

    def test_09_post_voice_audio_processing(self):
        """Test 9: /api/voice accepts audio upload and processes speech."""
        headers = {"Authorization": f"Bearer {self.token}"}

        # Create a 0.5s silent WAV file (16kHz mono 16-bit PCM)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 8000)
        wav_bytes = buf.getvalue()

        files = {"audio": ("test.wav", wav_bytes, "audio/wav")}
        res = self.client.post("/api/voice?client_scope=remote_web", files=files, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("reply_text", data)

    # -----------------------------------------------------------------------
    # 4. PWA STATIC ASSETS TESTS
    # -----------------------------------------------------------------------
    def test_10_pwa_static_assets(self):
        """Test 10: Root, manifest.json, sw.js, and Three.js static assets are served."""
        # Index HTML
        res_root = self.client.get("/")
        self.assertEqual(res_root.status_code, 200)
        self.assertIn("<title>Project Libra // Remote Web Agent</title>", res_root.text)
        self.assertIn("three.min.js", res_root.text)

        # Manifest JSON
        res_mf = self.client.get("/manifest.json")
        self.assertEqual(res_mf.status_code, 200)
        mf_data = res_mf.json()
        self.assertEqual(mf_data.get("name"), "Project Libra Remote Web Agent")
        self.assertEqual(mf_data.get("display"), "standalone")

        # Service Worker
        res_sw = self.client.get("/sw.js")
        self.assertEqual(res_sw.status_code, 200)
        self.assertIn("libra-pwa", res_sw.text)

        # Three.js library
        res_three = self.client.get("/static/three.min.js")
        self.assertEqual(res_three.status_code, 200)
        self.assertTrue(len(res_three.content) > 100000)


if __name__ == "__main__":
    unittest.main()
