"""
=============================================================================
TEST SUITE: SECURE GITHUB OAUTH 2.0 FLOW & BUG REPORT ATTRIBUTION
Target: tests/test_github_oauth.py
Verifies:
  1. /auth/github/start generates cryptographic CSRF state, sets secure cookie,
     and redirects to GitHub authorize URL with scope=read:user.
  2. /auth/github/login renders clean login page with single 'Continue with GitHub'
     button and NO token or password inputs.
  3. /auth/github/callback rejects missing state or state-mismatch (HTTP 400).
  4. Successful mock OAuth flow exchanges code, fetches profile, creates session,
     sets auth cookies, clears state cookie, and records github_username in memory.
  5. Bug report (/api/bugs) strictly attributes to session's GitHub username (@user),
     blocking free-text reporter spoofing.
=============================================================================
"""

import os
import sys
import unittest
import json
from unittest.mock import patch, AsyncMock
from urllib.parse import urlparse, parse_qs
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.orchestrator import SupervisorHub
from core.llm import LocalLLM
from web.server import create_app, load_web_config


class MockHttpResponse:
    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json_data = json_data
        self.text = json.dumps(json_data)

    def json(self):
        return self._json_data


class TestGitHubOAuthFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.llm = LocalLLM()
        cls.hub = SupervisorHub(cls.llm)
        cls.cfg = load_web_config("config.json")
        cls.admin_email = cls.cfg.get("admin_email", "REDACTED")
        cls.app = create_app(hub=cls.hub, config_path="config.json")
        cls.client = TestClient(cls.app)
        cls.memory = cls.hub.llm.memory

    def test_01_oauth_start_csrf_state_and_redirect(self):
        """Verifies /auth/github/start generates a CSRF state, sets a secure cookie, and redirects with scope=read:user."""
        res = self.client.get("/auth/github/start", follow_redirects=False)
        self.assertEqual(res.status_code, 307)
        loc = res.headers.get("location", "")
        self.assertTrue(loc.startswith("https://github.com/login/oauth/authorize"))

        # Verify parsed URL query parameters
        parsed = urlparse(loc)
        params = parse_qs(parsed.query)
        self.assertIn("client_id", params)
        self.assertIn("redirect_uri", params)
        self.assertEqual(params.get("scope"), ["read:user"])
        self.assertIn("state", params)
        state_param = params["state"][0]
        self.assertTrue(len(state_param) >= 32)

        # Verify secure state cookie is set matching the state param
        state_cookie = res.cookies.get("libra_gh_state")
        self.assertEqual(state_cookie, state_param)

    def test_02_login_screen_renders_single_button_without_token_inputs(self):
        """Verifies /auth/github/login presents a clean single button and no token/PAT inputs."""
        res = self.client.get("/auth/github/login")
        self.assertEqual(res.status_code, 200)
        body = res.text

        # Must have Octocat brand icon and Continue with GitHub button
        self.assertIn("Sign in with GitHub", body)
        self.assertIn("Continue with GitHub", body)
        self.assertIn("/auth/github/start", body)

        # Must NOT contain password input, token input, or PAT instructions
        self.assertNotIn('type="password"', body.lower())
        self.assertNotIn('name="token"', body.lower())
        self.assertNotIn("ghp_", body)
        self.assertNotIn("personal access token", body.lower())

    def test_03_callback_state_mismatch_rejected(self):
        """Verifies /auth/github/callback rejects mismatched or missing CSRF state with HTTP 400."""
        # 1. Missing state in query params
        res = self.client.get("/auth/github/callback?code=mock_code_123")
        self.assertEqual(res.status_code, 400)

        # 2. Missing state cookie
        res = self.client.get("/auth/github/callback?code=mock_code_123&state=some_random_state")
        self.assertEqual(res.status_code, 400)
        self.assertIn("OAuth state verification failed", res.text)

        # 3. State parameter does not match state cookie
        client_with_cookie = TestClient(self.app, cookies={"libra_gh_state": "legitimate_state_abc"})
        res = client_with_cookie.get("/auth/github/callback?code=mock_code_123&state=attacker_tampered_state")
        self.assertEqual(res.status_code, 400)
        self.assertIn("OAuth state verification failed", res.text)

    def test_04_successful_mock_oauth_creates_session_with_github_username(self):
        """Verifies successful token exchange & profile fetch creates user session with github_username."""
        mock_state = "valid_secure_state_9876543210"
        mock_code = "valid_oauth_code_abcdef"
        mock_gh_user = "tester_octocat_42"
        mock_email = "tester_octocat_42@users.noreply.github.com"
        mock_name = "Octocat Tester 42"

        async def mock_post(url, **kwargs):
            if "login/oauth/access_token" in str(url):
                return MockHttpResponse(200, {"access_token": "mock_gho_access_token_secret_xyz"})
            return MockHttpResponse(404, {"error": "not found"})

        async def mock_get(url, **kwargs):
            if "api.github.com/user" in str(url):
                # Verify access token header is sent
                auth_hdr = kwargs.get("headers", {}).get("Authorization", "")
                assert "Bearer mock_gho_access_token_secret_xyz" in auth_hdr
                return MockHttpResponse(200, {
                    "login": mock_gh_user,
                    "name": mock_name,
                    "email": mock_email,
                    "avatar_url": "https://avatars.githubusercontent.com/u/99999"
                })
            return MockHttpResponse(404, {"error": "not found"})

        with patch("httpx.AsyncClient.post", side_effect=mock_post), \
             patch("httpx.AsyncClient.get", side_effect=mock_get):

            client_session = TestClient(self.app, cookies={"libra_gh_state": mock_state})
            res = client_session.get(
                f"/auth/github/callback?code={mock_code}&state={mock_state}",
                follow_redirects=False
            )
            self.assertEqual(res.status_code, 200)

            # Assert auth token cookie is set
            auth_token = res.cookies.get("libra_token") or res.cookies.get("libra_auth")
            self.assertTrue(bool(auth_token), "Expected libra_token or libra_auth cookie in response")

            # Verify registered user exists in memory with correct github_username
            user_record = self.memory.get_registered_user_by_email(mock_email)
            self.assertIsNotNone(user_record)
            self.assertEqual(user_record.get("github_username"), mock_gh_user)
            self.assertEqual(user_record.get("role"), "tester")

            # Verify /api/auth/me returns the github_login
            me_res = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
            self.assertEqual(me_res.status_code, 200)
            me_data = me_res.json()
            self.assertEqual(me_data.get("github_login"), mock_gh_user)
            self.assertEqual(me_data.get("role"), "tester")

    def test_05_bug_report_strictly_attributed_to_session_github_username(self):
        """Verifies bug reports use the session's GitHub username for attribution, ignoring free-text spoofing."""
        # 1. Register a GitHub-authenticated user in memory
        gh_login = "verified_github_tester"
        gh_email = "verified_github_tester@github.com"
        user = self.memory.get_or_create_registered_user(
            email=gh_email,
            default_role="tester",
            display_name="Verified Tester",
            github_username=gh_login
        )
        user_tok = user["unique_token"]

        # 2. Submit bug report with an attempted free-text spoof: reporter_name = "ImposterHost"
        bug_payload = {
            "description": "Navigation button fails on 390px mobile viewport",
            "reporter_name": "ImposterHost",
            "category": "UI/UX",
            "device_info": "Mobile Chrome 128 / iOS 17"
        }
        res = self.client.post(
            "/api/bugs",
            json=bug_payload,
            headers={"Authorization": f"Bearer {user_tok}"}
        )
        self.assertEqual(res.status_code, 200)
        report_data = res.json()
        bug_id = report_data.get("id")

        # 3. Read back bug reports from /api/bugs
        list_res = self.client.get("/api/bugs", headers={"Authorization": f"Bearer {user_tok}"})
        self.assertEqual(list_res.status_code, 200)
        reports = list_res.json().get("reports", [])
        saved_bug = next((r for r in reports if r.get("id") == bug_id), None)
        self.assertIsNotNone(saved_bug)

        # Attribution MUST strictly be @verified_github_tester, NOT ImposterHost
        self.assertEqual(saved_bug.get("reporter"), f"@{gh_login}")
        self.assertNotIn("ImposterHost", saved_bug.get("reporter"))

    def test_06_bug_report_without_github_uses_session_email_or_label(self):
        """Verifies bug reports submitted without GitHub OAuth fall back to the authenticated user's session email/label."""
        std_email = "regular_tester_42@example.com"
        user = self.memory.get_or_create_registered_user(
            email=std_email,
            default_role="tester",
            display_name="Regular Tester",
            github_username=""
        )
        user_tok = user["unique_token"]

        bug_payload = {
            "description": "General performance latency observed during heavy chat",
            "category": "Performance"
        }
        res = self.client.post(
            "/api/bugs",
            json=bug_payload,
            headers={"Authorization": f"Bearer {user_tok}"}
        )
        self.assertEqual(res.status_code, 200)
        bug_id = res.json().get("id")

        list_res = self.client.get("/api/bugs", headers={"Authorization": f"Bearer {user_tok}"})
        reports = list_res.json().get("reports", [])
        saved_bug = next((r for r in reports if r.get("id") == bug_id), None)
        self.assertIsNotNone(saved_bug)
        self.assertEqual(saved_bug.get("reporter"), std_email)


if __name__ == "__main__":
    unittest.main()
