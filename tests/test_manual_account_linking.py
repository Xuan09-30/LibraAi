"""
=============================================================================
TEST SUITE: MANUAL ACCOUNT LINKING & PRE-EXISTING ACCOUNT MERGE
Target: tests/test_manual_account_linking.py
Verifies:
  1. Authenticated user initiating manual link for an unlinked identity
     directly links without requiring a merge confirmation screen.
  2. Merging two pre-existing accounts (e.g. separate Google & GitHub accounts):
     - Displays merge confirmation screen explaining combining accounts cannot be undone.
     - On confirmed merge: transfers bug reports, memory/vault notes, and preferences to surviving account.
     - Creates pre-deletion backup of secondary account data.
     - Secondary account's session token is invalidated (401 on subsequent requests).
     - Secondary account can no longer log in standalone; GitHub login resolves to surviving account.
  3. Security: Cannot merge without completing real OAuth as that identity (proof of ownership).
  4. Security: Unverified GitHub email cannot be manually linked.
=============================================================================
"""

import os
import sys
import unittest
import json
import re
import urllib.parse
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.orchestrator import SupervisorHub
from core.llm import LocalLLM
from core.memory import MemoryCore
from web.server import create_app, load_web_config


class TestManualAccountLinking(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.llm = LocalLLM()
        cls.hub = SupervisorHub(cls.llm)
        cls.cfg = load_web_config("config.json")
        cls.app = create_app(hub=cls.hub, config_path="config.json")
        cls.memory: MemoryCore = cls.hub.llm.memory

    def setUp(self):
        self.client = TestClient(self.app)

    def test_01_manual_link_unlinked_identity_directly_links_without_prompt(self):
        """
        Step 1 & 2a: Authenticated user clicks 'Link GitHub Account' for an identity
        NOT already linked to any account. It directly links without merge confirmation.
        """
        user_email = "manual_link_user1@example.com"
        user = self.memory.create_canonical_user(
            primary_email=user_email,
            display_name="User One",
            role="user"
        )
        self.memory.link_identity(
            user_id=user["user_id"],
            provider="google",
            provider_user_id=user_email,
            email=user_email,
            email_verified=True
        )
        user_tok = user["unique_token"]

        # Authenticated user starts manual link for GitHub
        self.client.cookies.set("libra_auth", user_tok)
        start_res = self.client.get("/auth/link/start?provider=github", headers={"Authorization": f"Bearer {user_tok}"}, follow_redirects=False)
        self.assertIn(start_res.status_code, (302, 307), f"Expected redirect, got: {start_res.status_code}")
        loc = start_res.headers.get("location", "")
        self.assertIn("github.com/login/oauth/authorize", loc)

        # Extract state from redirect URL or cookie
        import urllib.parse
        parsed = urllib.parse.urlparse(loc)
        qs = urllib.parse.parse_qs(parsed.query)
        state = qs.get("state", [""])[0]
        self.assertTrue(state, "OAuth state must be generated for manual link")

        # Mock GitHub callback with fresh, unlinked identity
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"access_token": "gho_mock_new_identity"}

        mock_user_resp = MagicMock()
        mock_user_resp.status_code = 200
        mock_user_resp.json.return_value = {
            "login": "fresh_coder_99",
            "id": "gh_uid_fresh_99",
            "email": "fresh_coder_99@github.com",
            "verified": True,
            "name": "Fresh Coder"
        }

        with patch("httpx.AsyncClient.post", return_value=mock_token_resp), \
             patch("httpx.AsyncClient.get", return_value=mock_user_resp):
            self.client.cookies.set("libra_gh_state", state)
            cb_res = self.client.get(f"/auth/github/callback?code=mock_code_1&state={state}")
            self.assertEqual(cb_res.status_code, 200)

            # Must NOT show merge confirmation screen since identity is new
            self.assertNotIn("This will combine", cb_res.text)

            # Verify user now has both identities directly
            identities = self.memory.get_user_identities(user["user_id"])
            self.assertEqual(len(identities), 2)
            providers = {i["provider"] for i in identities}
            self.assertEqual(providers, {"google", "github"})

            # Canonical user has github_username set
            refreshed = self.memory.get_canonical_user_by_id(user["user_id"])
            self.assertEqual(refreshed["github_username"], "fresh_coder_99")

    def test_02_merge_two_existing_accounts_transfers_data_and_invalidates_secondary(self):
        """
        Step 2b, 3, 4: Merging two pre-existing accounts (e.g. existing Google and separate existing GitHub):
        - Callback shows merge confirmation screen: "This will combine <A> and <B> into one account. This cannot be undone."
        - On confirmation: transfers bug reports, memory/vault notes to surviving account.
        - Backs up secondary account before deleting/deactivating.
        - Invalidates secondary account sessions/tokens.
        """
        # Account A (Surviving account - Google)
        email_a = "surviving_google@example.com"
        user_a = self.memory.create_canonical_user(
            primary_email=email_a,
            display_name="Surviving User",
            role="user"
        )
        self.memory.link_identity(
            user_id=user_a["user_id"],
            provider="google",
            provider_user_id=email_a,
            email=email_a,
            email_verified=True
        )
        tok_a = user_a["unique_token"]

        # Account A memory note
        self.memory.remember_fact("Note belonging to Account A", user_email=email_a)

        # Account B (Secondary account - GitHub)
        email_b = "secondary_gh@example.com"
        user_b = self.memory.create_canonical_user(
            primary_email=email_b,
            display_name="Secondary GH User",
            role="user",
            github_username="secondary_dev"
        )
        self.memory.link_identity(
            user_id=user_b["user_id"],
            provider="github",
            provider_user_id="gh_uid_secondary_888",
            email=email_b,
            email_verified=True,
            github_username="secondary_dev"
        )
        tok_b = user_b["unique_token"]

        # Account B memory note
        self.memory.remember_fact("Secret memory note from Account B", user_email=email_b)

        # Account B creates a bug report using its token tok_b
        bug_res = self.client.post(
            "/api/bugs",
            json={"title": "Bug filed by secondary account", "description": "Secondary account bug", "reporter": "@secondary_dev"},
            headers={"Authorization": f"Bearer {tok_b}"}
        )
        self.assertEqual(bug_res.status_code, 200)
        bug_id = bug_res.json().get("id")

        # Now, logged in as Account A, start manual link for GitHub
        self.client.cookies.set("libra_auth", tok_a)
        start_res = self.client.get("/auth/link/start?provider=github", headers={"Authorization": f"Bearer {tok_a}"}, follow_redirects=False)
        self.assertIn(start_res.status_code, (302, 307))
        loc = start_res.headers.get("location", "")
        parsed = urllib.parse.urlparse(loc)
        state = urllib.parse.parse_qs(parsed.query).get("state", [""])[0]

        # GitHub callback returns Account B's identity!
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"access_token": "gho_mock_token_secondary"}

        mock_user_resp = MagicMock()
        mock_user_resp.status_code = 200
        mock_user_resp.json.return_value = {
            "login": "secondary_dev",
            "id": "gh_uid_secondary_888",
            "email": email_b,
            "verified": True,
            "name": "Secondary GH User"
        }

        with patch("httpx.AsyncClient.post", return_value=mock_token_resp), \
             patch("httpx.AsyncClient.get", return_value=mock_user_resp):
            self.client.cookies.set("libra_gh_state", state)
            cb_res = self.client.get(f"/auth/github/callback?code=mock_code_merge&state={state}")

            # MUST render merge confirmation screen
            self.assertEqual(cb_res.status_code, 200)
            self.assertIn("This will combine", cb_res.text)
            self.assertIn("into one account. This cannot be undone.", cb_res.text)
            self.assertIn(email_a, cb_res.text)
            self.assertIn(email_b, cb_res.text)

            # Extract merge_token from HTML
            m = re.search(r'name=["\']merge_token["\']\s+value=["\']([^"\']+)["\']', cb_res.text)
            self.assertIsNotNone(m, "merge_token must be present in merge confirmation screen form")
            merge_token = m.group(1)

            # Confirm merge via POST /api/auth/merge-accounts
            merge_res = self.client.post(
                "/api/auth/merge-accounts",
                data={"merge_token": merge_token, "action": "merge"},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            self.assertEqual(merge_res.status_code, 200)

        # 1. Check surviving account has acquired Account B's identity
        identities_a = self.memory.get_user_identities(user_a["user_id"])
        self.assertEqual(len(identities_a), 2)
        providers_a = {i["provider"] for i in identities_a}
        self.assertEqual(providers_a, {"google", "github"})

        # Surviving account github_username updated
        refreshed_a = self.memory.get_canonical_user_by_id(user_a["user_id"])
        self.assertEqual(refreshed_a["github_username"], "secondary_dev")

        # 2. Check bug report was transferred to surviving account / handle
        list_bugs = self.client.get("/api/bugs", headers={"Authorization": f"Bearer {tok_a}"})
        reports = list_bugs.json().get("reports", [])
        transferred_bug = next((r for r in reports if r.get("id") == bug_id), None)
        self.assertIsNotNone(transferred_bug)
        self.assertEqual(transferred_bug.get("reporter"), "@secondary_dev")

        # 3. Check memory notes were transferred from Account B to Account A
        conn = self.memory._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT content FROM facts WHERE user_email = ?", (email_a,))
            a_facts = [r[0] for r in cursor.fetchall()]
            self.assertIn("Secret memory note from Account B", a_facts)
        finally:
            if self.memory.db_path != ":memory:":
                conn.close()

        # 4. Check backup exists
        backup = self.memory.get_merge_backup(user_b["user_id"])
        self.assertIsNotNone(backup, "Secondary account data backup must exist before deletion")

        # 5. Check secondary account token is invalidated (401 on requests)
        invalid_res = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok_b}"})
        self.assertEqual(invalid_res.status_code, 401, "Secondary account's previous session must be kicked out / invalidated")

        # Secondary account cannot log in standalone
        sec_user = self.memory.validate_user_token(tok_b)
        self.assertIsNone(sec_user, "Secondary token must not validate after merge")

    def test_03_cannot_merge_without_valid_oauth_proof(self):
        """
        Step 5: User cannot merge an account that belongs to someone else without
        going through real OAuth as that identity (proof of ownership).
        """
        # User tries to submit arbitrary / fake merge token directly
        fake_res = self.client.post(
            "/api/auth/merge-accounts",
            data={"merge_token": "forged_merge_token_12345", "action": "merge"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        self.assertIn(fake_res.status_code, (400, 401, 403, 422))

    def test_04_unverified_github_email_rejected_for_manual_link(self):
        """
        Step 2: Unverified GitHub email cannot be manually linked to an account.
        """
        user = self.memory.create_canonical_user(
            primary_email="charlie_test@example.com",
            display_name="Charlie Test",
            role="user"
        )
        user_tok = user["unique_token"]

        self.client.cookies.set("libra_auth", user_tok)
        start_res = self.client.get("/auth/link/start?provider=github", headers={"Authorization": f"Bearer {user_tok}"}, follow_redirects=False)
        loc = start_res.headers.get("location", "")
        parsed = urllib.parse.urlparse(loc)
        state = urllib.parse.parse_qs(parsed.query).get("state", [""])[0]

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"access_token": "gho_mock_unverified"}

        mock_user_resp = MagicMock()
        mock_user_resp.status_code = 200
        mock_user_resp.json.return_value = {
            "login": "unverified_charlie",
            "id": "gh_uid_unverified_55",
            "email": "charlie_fake@example.com",
            "verified": False,
            "name": "Unverified Charlie"
        }

        mock_emails_resp = MagicMock()
        mock_emails_resp.status_code = 200
        mock_emails_resp.json.return_value = [
            {"email": "charlie_fake@example.com", "primary": True, "verified": False}
        ]

        with patch("httpx.AsyncClient.post", return_value=mock_token_resp), \
             patch("httpx.AsyncClient.get", side_effect=[mock_user_resp, mock_emails_resp]):
            self.client.cookies.set("libra_gh_state", state)
            res = self.client.get(f"/auth/github/callback?code=mock_code_unverified&state={state}")

            # Must reject unverified email
            self.assertIn(res.status_code, (400, 403))
            self.assertIn("unverified", res.text.lower())

            # User must NOT have GitHub identity linked
            identities = self.memory.get_user_identities(user["user_id"])
            gh_ids = [i for i in identities if i["provider"] == "github"]
            self.assertEqual(len(gh_ids), 0)

    def test_05_linked_identities_api_returns_status_and_link_flags(self):
        """
        Step 1: Settings API /api/auth/linked-identities returns linked providers and available link targets.
        """
        user = self.memory.create_canonical_user(
            primary_email="dan_settings@example.com",
            display_name="Dan Settings",
            role="user"
        )
        self.memory.link_identity(
            user_id=user["user_id"],
            provider="google",
            provider_user_id="dan_settings@example.com",
            email="dan_settings@example.com",
            email_verified=True
        )
        tok = user["unique_token"]

        # Call with auth
        res = self.client.get("/api/auth/linked-identities", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("user_id"), user["user_id"])
        self.assertTrue(data.get("has_google"))
        self.assertFalse(data.get("has_github"))
        self.assertTrue(data.get("can_link_github"))
        self.assertFalse(data.get("can_link_google"))

        # Call without auth returns 401
        anon_res = self.client.get("/api/auth/linked-identities")
        self.assertEqual(anon_res.status_code, 401)


if __name__ == "__main__":
    unittest.main()
