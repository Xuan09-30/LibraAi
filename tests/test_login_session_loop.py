"""
=============================================================================
TEST SUITE: NON-HOST LOGIN SESSION PERSISTENCE & MODAL LOOP PREVENTION
Target: tests/test_login_session_loop.py
Verifies:
  1. Non-host Google OAuth / Login issues valid session token & persists session
  2. Non-host GitHub OAuth / Login issues valid session token & persists session
  3. MemoryCore provides get_user_by_email / get_registered_user_by_email lookup
  4. Non-host follow-up requests (/api/auth/me, /api/sessions, /api/chat) succeed
  5. Receiving HTTP 403 on restricted endpoints (such as /api/vitals) does NOT
     trigger an auth modal loop or invalidate the user's active session
  6. In a real browser context, logging in as a non-host user does NOT cause
     the login modal to re-appear in an infinite loop.
=============================================================================
"""

import os
import sys
import json
import time
import socket
import threading
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.orchestrator import SupervisorHub
from core.llm import LocalLLM
from web.server import create_app, load_web_config


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class TestLoginSessionLoop:
    @classmethod
    def setup_class(cls):
        cls.llm = LocalLLM()
        cls.hub = SupervisorHub(cls.llm)
        cls.cfg = load_web_config("config.json")
        cls.admin_email = cls.cfg.get("admin_email", "REDACTED")
        cls.app = create_app(hub=cls.hub, config_path="config.json")
        cls.client = TestClient(cls.app)
        cls.memory = cls.hub.llm.memory

    def test_01_memory_has_get_user_by_email(self):
        """Step 3/4: Ensure MemoryCore has get_user_by_email method matching server lookup."""
        assert hasattr(self.memory, "get_user_by_email"), (
            "MemoryCore is missing 'get_user_by_email' alias, causing identity header lookups to fail with 403"
        )
        # Register a test non-host user
        test_email = "tester_loop_01@example.com"
        u = self.memory.get_or_create_registered_user(test_email, default_role="tester", display_name="Loop Tester 1")
        assert u is not None

        # Verify get_user_by_email returns the user
        fetched = self.memory.get_user_by_email(test_email)
        assert fetched is not None
        assert fetched.get("email") == test_email
        assert fetched.get("role") == "tester"

    def test_02_google_login_non_host_and_followup_requests(self):
        """Step 4/5: Non-host Google login returns valid token and follow-up requests succeed."""
        test_email = "sarah_tester@example.com"
        login_res = self.client.post(
            "/api/auth/google-login",
            json={"email": test_email, "name": "Sarah Tester"}
        )
        assert login_res.status_code == 200, f"Google login failed: {login_res.text}"
        data = login_res.json()
        assert data.get("status") == "success"
        token = data.get("token")
        assert token and token.startswith("libra_usr_")
        assert data.get("role") in ("tester", "guest")

        headers = {"Authorization": f"Bearer {token}"}
        cookies = {"libra_auth": token}

        # Follow-up request 1: /api/auth/me
        me_res = self.client.get("/api/auth/me", headers=headers, cookies=cookies)
        assert me_res.status_code == 200, f"/api/auth/me failed: {me_res.text}"
        me_data = me_res.json()
        assert me_data.get("status") == "authenticated"
        assert me_data.get("email") == test_email
        assert me_data.get("role") in ("tester", "guest")

        # Follow-up request 2: /api/sessions
        sess_res = self.client.get("/api/sessions", headers=headers, cookies=cookies)
        assert sess_res.status_code == 200, f"/api/sessions failed: {sess_res.text}"

        # Follow-up request 3: create new session
        new_sess_res = self.client.post(
            "/api/sessions/new",
            json={"title": "Sarah Chat", "client_scope": "remote_web"},
            headers=headers,
            cookies=cookies
        )
        assert new_sess_res.status_code == 200, f"/api/sessions/new failed: {new_sess_res.text}"
        new_sid = new_sess_res.json().get("session_id")
        assert new_sid is not None

        # Follow-up request 4: /api/vitals returns 403 (host-only) but does NOT invalidate session
        vitals_res = self.client.get("/api/vitals", headers=headers, cookies=cookies)
        assert vitals_res.status_code == 403, "Vitals should be 403 for non-host"

        # Follow-up request 5: Verify subsequent request still succeeds after vitals 403
        subsequent_res = self.client.get("/api/auth/me", headers=headers, cookies=cookies)
        assert subsequent_res.status_code == 200, "Session should persist after 403 from vitals"

    def test_03_github_login_non_host_and_followup_requests(self):
        """Step 4/5: Non-host GitHub login creates session and follow-up requests succeed."""
        test_gh_user = "bob_github_tester"
        test_gh_email = "bob_github_tester@example.com"

        # Mock GitHub OAuth callback
        mock_access_token_resp = MagicMock()
        mock_access_token_resp.json.return_value = {"access_token": "gho_mocked_token_xyz"}

        mock_user_resp = MagicMock()
        mock_user_resp.json.return_value = {
            "login": test_gh_user,
            "email": test_gh_email,
            "name": "Bob GitHub Tester"
        }

        with patch("httpx.AsyncClient.post", return_value=mock_access_token_resp), \
             patch("httpx.AsyncClient.get", return_value=mock_user_resp):
            cb_res = self.client.get("/auth/github/callback?code=mock_valid_code")
            assert cb_res.status_code == 200, f"GitHub callback failed: {cb_res.text}"
            assert "Authenticated with GitHub" in cb_res.text

            # Extract token from Set-Cookie or HTML script
            cookie_tok = cb_res.cookies.get("libra_auth")
            assert cookie_tok, "GitHub callback must set libra_auth cookie"

            headers = {"Authorization": f"Bearer {cookie_tok}"}
            cookies = {"libra_auth": cookie_tok}

            # Follow-up request 1: /api/auth/me
            me_res = self.client.get("/api/auth/me", headers=headers, cookies=cookies)
            assert me_res.status_code == 200
            me_data = me_res.json()
            assert me_data.get("status") == "authenticated"
            assert me_data.get("email") == test_gh_email

            # Follow-up request 2: /api/sessions
            sess_res = self.client.get("/api/sessions", headers=headers, cookies=cookies)
            assert sess_res.status_code == 200

            # Follow-up request 3: /api/vitals is 403 but session persists
            vitals_res = self.client.get("/api/vitals", headers=headers, cookies=cookies)
            assert vitals_res.status_code == 403

            me_res2 = self.client.get("/api/auth/me", headers=headers, cookies=cookies)
            assert me_res2.status_code == 200

    def test_04_frontend_vitals_does_not_open_auth_modal_on_403(self):
        """Step 4: Frontend fetchVitals() in app.js must NOT invoke showAuthModal() on 403."""
        app_js_path = os.path.join(PROJECT_ROOT, "web", "static", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Find fetchVitals definition
        idx = content.find("async function fetchVitals()")
        assert idx != -1, "fetchVitals() not found in app.js"
        fn_slice = content[idx:idx + 600]

        # In buggy code: `if (res.status === 401 || res.status === 403) {\n        showAuthModal();`
        # On 403 Forbidden, showAuthModal() MUST NOT be called because vitals are restricted to host!
        assert "if (res.status === 401 || res.status === 403) {\n\n        showAuthModal();" not in fn_slice and \
               "if (res.status === 401 || res.status === 403) {\n        showAuthModal();" not in fn_slice, (
            "Bug detected: fetchVitals() calls showAuthModal() on 403 Forbidden! "
            "Because /api/vitals returns 403 for all non-host users, this creates an infinite login loop."
        )

    def test_05_browser_non_host_login_modal_visibility(self):
        """Step 1 & 4: In a real browser, logging in as non-host does NOT display auth modal."""
        import uvicorn
        from playwright.sync_api import sync_playwright

        port = find_free_port()
        server_thread = threading.Thread(
            target=lambda: uvicorn.run(self.app, host="127.0.0.1", port=port, log_level="warning"),
            daemon=True
        )
        server_thread.start()
        time.sleep(1.5)

        test_email = "browser_tester@example.com"
        user = self.memory.get_or_create_registered_user(test_email, default_role="tester", display_name="Browser Tester")
        user_tok = user["unique_token"]

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context()
            page = context.new_page()

            # Set cookie and localStorage exactly as login does
            context.add_cookies([{
                "name": "libra_auth",
                "value": user_tok,
                "domain": "127.0.0.1",
                "path": "/"
            }])

            page.goto(f"http://127.0.0.1:{port}/")
            page.evaluate(f"localStorage.setItem('libra_token', '{user_tok}');")
            page.reload()

            # Wait 2.5s for initial vitals and sessions polling
            page.wait_for_timeout(2500)

            # Check if auth-modal is visible
            modal_visible = page.evaluate("""() => {
                const el = document.getElementById('auth-modal');
                return el && (el.style.display === 'flex' || window.getComputedStyle(el).display === 'flex');
            }""")

            browser.close()

            assert not modal_visible, (
                "Bug reproduced: auth-modal is still visible to the user after non-host login!"
            )
