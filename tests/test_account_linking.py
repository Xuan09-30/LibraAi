"""
=============================================================================
TEST SUITE: ACCOUNT LINKING & IDENTITY MODEL (GOOGLE + GITHUB)
Target: tests/test_account_linking.py
Verifies:
  1. (Spec 5) GitHub account with UNVERIFIED email matching an existing Google
     account must NOT trigger a linking prompt or merge. Creates separate account.
  2. (Spec 6) GitHub account with VERIFIED email matching an existing Google
     account DOES trigger a linking prompt, and only links after explicit
     confirmation (Yes), never automatically.
  3. (Spec 7) Declining the link (No / action='separate') creates a separate
     account, not an error.
  4. (Spec 8) An account can only be linked to each provider once
     (UNIQUE constraint on provider + provider_user_id, no duplicate rows).
  5. (Spec 4) Once linked, logging in with either provider resolves to the same
     canonical user_id, same session, and bug reports attribute to the linked
     GitHub username.
=============================================================================
"""

import os
import sys
import unittest
import json
import sqlite3
import re
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.orchestrator import SupervisorHub
from core.llm import LocalLLM
from core.memory import MemoryCore
from web.server import create_app, load_web_config


class TestAccountLinkingSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.llm = LocalLLM()
        cls.hub = SupervisorHub(cls.llm)
        cls.cfg = load_web_config("config.json")
        cls.app = create_app(hub=cls.hub, config_path="config.json")
        cls.client = TestClient(cls.app)
        cls.memory: MemoryCore = cls.hub.llm.memory

    def test_01_github_unverified_email_does_not_prompt_or_merge(self):
        """
        Spec 5: GitHub account with an UNVERIFIED email matching an existing Google
        account must NOT trigger a linking prompt or merge.
        Attacker must NOT be allowed to hijack the existing Google user's account.
        """
        target_email = "victim_google_user@example.com"
        google_sub = "victim_google_user@example.com"

        # 1. Existing Google user created
        google_user = self.memory.create_canonical_user(
            primary_email=target_email,
            display_name="Victim Google User",
            role="user"
        )
        self.memory.link_identity(
            user_id=google_user["user_id"],
            provider="google",
            provider_user_id=google_sub,
            email=target_email,
            email_verified=True
        )

        # Confirm linking candidate check directly in MemoryCore returns None if email_verified=False
        cand = self.memory.find_linking_candidate(target_email, provider="github", email_verified=False)
        self.assertIsNone(cand, "find_linking_candidate must return None for unverified email")

        # 2. Attacker logs in with GitHub claiming target_email, but GitHub reports verified=False
        attacker_gh_login = "evil_hacker_99"
        attacker_gh_uid = "99988877"

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"access_token": "gho_mock_token_attacker"}

        mock_user_resp = MagicMock()
        mock_user_resp.status_code = 200
        mock_user_resp.json.return_value = {
            "login": attacker_gh_login,
            "id": attacker_gh_uid,
            "email": target_email,
            "verified": False,  # UNVERIFIED
            "name": "Evil Hacker"
        }

        mock_emails_resp = MagicMock()
        mock_emails_resp.status_code = 200
        mock_emails_resp.json.return_value = [
            {"email": target_email, "primary": True, "verified": False}
        ]

        with patch("httpx.AsyncClient.post", return_value=mock_token_resp), \
             patch("httpx.AsyncClient.get", side_effect=[mock_user_resp, mock_emails_resp]):
            state = "csrf_state_unverified_test"
            self.client.cookies.set("libra_gh_state", state)
            res = self.client.get(f"/auth/github/callback?code=code_unverified&state={state}")

            # Must NOT prompt for linking
            self.assertNotIn("Link your accounts?", res.text)
            self.assertNotIn("confirm-link-btn", res.text)
            self.assertEqual(res.status_code, 200)

            # Must NOT have merged into Google user's user_id
            attacker_cookie = res.cookies.get("libra_auth")
            self.assertTrue(attacker_cookie)
            attacker_user = self.memory.validate_user_token(attacker_cookie)
            self.assertIsNotNone(attacker_user)
            self.assertNotEqual(
                attacker_user["user_id"],
                google_user["user_id"],
                "Unverified email must NEVER merge into the existing account!"
            )

    def test_02_github_verified_email_triggers_prompt_and_links_on_confirmation(self):
        """
        Spec 6: GitHub account with a VERIFIED email matching an existing Google
        account DOES trigger a linking prompt, and only links after explicit
        confirmation (Yes), never automatically.
        """
        target_email = "alice_verified_both@example.com"
        google_sub = "alice_verified_both@example.com"

        # 1. Existing Google user created
        google_user = self.memory.create_canonical_user(
            primary_email=target_email,
            display_name="Alice Legit",
            role="user"
        )
        self.memory.link_identity(
            user_id=google_user["user_id"],
            provider="google",
            provider_user_id=google_sub,
            email=target_email,
            email_verified=True
        )

        # 2. Alice logs in with GitHub with VERIFIED email
        alice_gh_login = "alice_coder"
        alice_gh_uid = "5551234"

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"access_token": "gho_mock_token_alice"}

        mock_user_resp = MagicMock()
        mock_user_resp.status_code = 200
        mock_user_resp.json.return_value = {
            "login": alice_gh_login,
            "id": alice_gh_uid,
            "email": target_email,
            "verified": True,  # VERIFIED
            "name": "Alice Coder"
        }

        with patch("httpx.AsyncClient.post", return_value=mock_token_resp), \
             patch("httpx.AsyncClient.get", return_value=mock_user_resp):
            state = "csrf_state_alice_link"
            self.client.cookies.set("libra_gh_state", state)
            res = self.client.get(f"/auth/github/callback?code=code_alice&state={state}")

            # Must render confirmation screen
            self.assertEqual(res.status_code, 200)
            self.assertIn("Link your accounts?", res.text)
            self.assertIn(target_email, res.text)
            self.assertIn("Google", res.text)
            self.assertIn("confirm-link-btn", res.text)
            self.assertIn("decline-link-btn", res.text)
            self.assertIn("name=\"link_token\"", res.text)

            # Extract link_token from HTML
            m = re.search(r'name=["\']link_token["\']\s+value=["\']([^"\']+)["\']', res.text)
            self.assertIsNotNone(m, "Link token must be in the confirmation screen form")
            link_token = m.group(1)

            # Identities table must NOT be linked yet (no silent/auto-merge)
            pre_identities = self.memory.get_user_identities(google_user["user_id"])
            self.assertEqual(len(pre_identities), 1)
            self.assertEqual(pre_identities[0]["provider"], "google")

            # 3. Explicit user confirmation: Yes, Link Accounts
            confirm_res = self.client.post(
                "/api/auth/link-account",
                data={"link_token": link_token, "action": "link"},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            self.assertEqual(confirm_res.status_code, 200)
            res_data = confirm_res.json()
            self.assertEqual(res_data.get("status"), "success")
            self.assertEqual(res_data.get("user_id"), google_user["user_id"])

            # Identities table must now contain both Google and GitHub for Alice's canonical user_id
            post_identities = self.memory.get_user_identities(google_user["user_id"])
            self.assertEqual(len(post_identities), 2)
            providers = {i["provider"] for i in post_identities}
            self.assertEqual(providers, {"google", "github"})

            # Canonical user's github_username must be updated
            refreshed_user = self.memory.get_canonical_user_by_id(google_user["user_id"])
            self.assertEqual(refreshed_user["github_username"], alice_gh_login)

    def test_03_declining_link_creates_separate_account_not_error(self):
        """
        Spec 7: Declining the link creates a separate account, not an error.
        """
        target_email = "bob_declining@example.com"
        google_sub = "bob_declining@example.com"

        # 1. Existing Google user
        google_user = self.memory.create_canonical_user(
            primary_email=target_email,
            display_name="Bob Original",
            role="user"
        )
        self.memory.link_identity(
            user_id=google_user["user_id"],
            provider="google",
            provider_user_id=google_sub,
            email=target_email,
            email_verified=True
        )

        # 2. Bob logs in with GitHub with same verified email
        bob_gh_login = "bob_separate"
        bob_gh_uid = "7776665"

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"access_token": "gho_mock_token_bob"}

        mock_user_resp = MagicMock()
        mock_user_resp.status_code = 200
        mock_user_resp.json.return_value = {
            "login": bob_gh_login,
            "id": bob_gh_uid,
            "email": target_email,
            "verified": True,
            "name": "Bob Separate"
        }

        with patch("httpx.AsyncClient.post", return_value=mock_token_resp), \
             patch("httpx.AsyncClient.get", return_value=mock_user_resp):
            state = "csrf_state_bob_decline"
            self.client.cookies.set("libra_gh_state", state)
            res = self.client.get(f"/auth/github/callback?code=code_bob&state={state}")

            m = re.search(r'name=["\']link_token["\']\s+value=["\']([^"\']+)["\']', res.text)
            self.assertIsNotNone(m)
            link_token = m.group(1)

            # 3. User declines: No, Keep Separate
            decline_res = self.client.post(
                "/api/auth/link-account",
                data={"link_token": link_token, "action": "separate"},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            self.assertEqual(decline_res.status_code, 200)
            res_data = decline_res.json()
            self.assertEqual(res_data.get("status"), "success")
            self.assertEqual(res_data.get("action"), "separate")

            # Check token returned
            new_token = res_data.get("token")
            self.assertTrue(new_token)
            new_user = self.memory.validate_user_token(new_token)
            self.assertIsNotNone(new_user)

            # Confirm distinct accounts
            self.assertNotEqual(new_user["user_id"], google_user["user_id"])
            self.assertEqual(new_user["github_username"], bob_gh_login)

            # Existing Google user is untouched
            google_identities = self.memory.get_user_identities(google_user["user_id"])
            self.assertEqual(len(google_identities), 1)
            self.assertEqual(google_identities[0]["provider"], "google")

    def test_04_duplicate_provider_linking_rejected_by_unique_constraint(self):
        """
        Spec 8: An account can only be linked to each provider once
        (UNIQUE constraint on provider + provider_user_id, no duplicate rows).
        """
        user_a = self.memory.create_canonical_user(
            primary_email="user_a@example.com",
            display_name="User A",
            role="user"
        )
        user_b = self.memory.create_canonical_user(
            primary_email="user_b@example.com",
            display_name="User B",
            role="user"
        )

        # Link GitHub ID 12345 to User A
        self.memory.link_identity(
            user_id=user_a["user_id"],
            provider="github",
            provider_user_id="github_unique_12345",
            email="user_a@example.com",
            email_verified=True
        )

        # Attempt to link the same GitHub ID 12345 to User B -> must raise IntegrityError / ValueError
        with self.assertRaises((sqlite3.IntegrityError, ValueError)):
            self.memory.link_identity(
                user_id=user_b["user_id"],
                provider="github",
                provider_user_id="github_unique_12345",
                email="user_b@example.com",
                email_verified=True
            )

        # Query identities for User B, ensure it has 0 GitHub rows
        b_identities = self.memory.get_user_identities(user_b["user_id"])
        self.assertEqual(len(b_identities), 0)

    def test_05_linked_account_shared_session_and_bug_report_attribution(self):
        """
        Spec 4: Once linked, logging in with either provider resolves to the same
        session/user_id, same bug-report attribution, same memory/preferences.
        """
        shared_email = "carol_devops@example.com"
        carol_user = self.memory.create_canonical_user(
            primary_email=shared_email,
            display_name="Carol DevOps",
            role="user",
            github_username="carol_gh"
        )
        canonical_uid = carol_user["user_id"]
        canonical_token = carol_user["unique_token"]

        # Link Google and GitHub to carol_user
        self.memory.link_identity(
            user_id=canonical_uid,
            provider="google",
            provider_user_id=shared_email,
            email=shared_email,
            email_verified=True
        )
        self.memory.link_identity(
            user_id=canonical_uid,
            provider="github",
            provider_user_id="github_carol_id_888",
            email=shared_email,
            email_verified=True,
            github_username="carol_gh"
        )

        # Google login resolves to canonical_uid
        google_res = self.client.post("/api/auth/google-login", json={
            "email": shared_email,
            "name": "Carol DevOps"
        })
        self.assertEqual(google_res.status_code, 200)
        g_data = google_res.json()
        self.assertEqual(g_data.get("user_id"), canonical_uid)
        self.assertEqual(g_data.get("token"), canonical_token)

        # GitHub login resolves to canonical_uid
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"access_token": "gho_mock_token_carol"}

        mock_user_resp = MagicMock()
        mock_user_resp.status_code = 200
        mock_user_resp.json.return_value = {
            "login": "carol_gh",
            "id": "github_carol_id_888",
            "email": shared_email,
            "verified": True,
            "name": "Carol DevOps"
        }

        with patch("httpx.AsyncClient.post", return_value=mock_token_resp), \
             patch("httpx.AsyncClient.get", return_value=mock_user_resp):
            state = "csrf_state_carol_shared"
            self.client.cookies.set("libra_gh_state", state)
            gh_res = self.client.get(f"/auth/github/callback?code=code_carol&state={state}")
            self.assertEqual(gh_res.status_code, 200)
            self.assertIn("Authenticated with GitHub", gh_res.text)

            gh_cookie = gh_res.cookies.get("libra_auth")
            self.assertEqual(gh_cookie, canonical_token)

        # Bug report attribution: Submit bug report using the session token
        # Reporter should be automatically attributed to @carol_gh, not an arbitrary text or host account
        bug_res = self.client.post(
            "/api/bugs",
            json={"title": "Shared account UI issue", "description": "Testing bug report attribution", "reporter": "spoofed_hacker"},
            headers={"Authorization": f"Bearer {canonical_token}"}
        )
        self.assertEqual(bug_res.status_code, 200)
        bug_data = bug_res.json()
        self.assertEqual(bug_data.get("status"), "success")
        bug_id = bug_data.get("id")

        list_res = self.client.get("/api/bugs", headers={"Authorization": f"Bearer {canonical_token}"})
        reports = list_res.json().get("reports", [])
        saved_bug = next((r for r in reports if r.get("id") == bug_id), None)
        self.assertIsNotNone(saved_bug)
        self.assertEqual(saved_bug.get("reporter"), "@carol_gh")


if __name__ == "__main__":
    unittest.main()
