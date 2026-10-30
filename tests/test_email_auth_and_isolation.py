"""
=============================================================================
TEST SUITE: SECURE EMAIL AUTHENTICATION, OTP VERIFICATION & CHAT ISOLATION
Target: tests/test_email_auth_and_isolation.py
Verifies:
  1. OTP generation, uniqueness, and email dispatch fallback logging
  2. OTP verification with attempt limiting and expiration
  3. Google Authenticator TOTP calculation & validation
  4. Alt host account (chenxuanchuah2@gmail.com) receiving role='host'
  5. Login vs Signup mode separation
  6. Direct Google Device Account Login (/api/auth/google-login)
  7. Multi-user session isolation and memory persistence
  8. Chat wipe functionality
=============================================================================
"""

import os
import sys
import unittest
import json
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.orchestrator import SupervisorHub
from core.llm import LocalLLM
from core.memory import MemoryCore
from core.email_auth import (
    load_smtp_config, send_verification_email, log_verification_code_fallback,
    generate_totp_secret, get_current_totp_code, verify_totp_code
)
from web.server import create_app, load_web_config


class TestEmailAuthAndIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.llm = LocalLLM()
        cls.hub = SupervisorHub(cls.llm)
        cls.cfg = load_web_config("config.json")
        cls.admin_email = cls.cfg.get("admin_email", "chenxuanchuah@gmail.com")
        cls.app = create_app(hub=cls.hub, config_path="config.json")
        cls.client = TestClient(cls.app)
        cls.memory = cls.hub.llm.memory

    def test_01_smtp_config_loader(self):
        """Test SMTP config loader safely falls back when disabled or missing credentials."""
        cfg = load_smtp_config("config.json")
        self.assertIn("enabled", cfg)
        self.assertIn("host", cfg)
        self.assertIn("port", cfg)

    def test_02_otp_uniqueness_and_fallback(self):
        """Test OTP generation creates strictly unique 6-digit codes without repetition."""
        test_email = "friend_tester_01@example.com"
        generated_codes = set()
        for _ in range(5):
            code, sent, msg, *extra = self.memory.generate_email_otp(test_email)
            self.assertEqual(len(code), 6)
            self.assertTrue(code.isdigit())
            self.assertNotIn(code, generated_codes, f"Code {code} was repeated!")
            generated_codes.add(code)

        # Check log file exists and contains last entry
        log_path = os.path.join(PROJECT_ROOT, "logs", "verification_codes.log")
        self.assertTrue(os.path.exists(log_path))
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(test_email, content)
        self.assertIn(code, content)

    def test_03_otp_verification_flow(self):
        """Test verifying OTP code creates user account with unique token."""
        test_email = "friend_tester_02@example.com"
        code, sent, msg, *extra = self.memory.generate_email_otp(test_email)

        # Incorrect code fails
        ok_bad, user_bad, msg_bad = self.memory.verify_email_otp(test_email, "000000")
        self.assertFalse(ok_bad)
        self.assertIsNone(user_bad)

        # Correct code succeeds
        ok_good, user_good, msg_good = self.memory.verify_email_otp(test_email, code)
        self.assertTrue(ok_good)
        self.assertIsNotNone(user_good)
        self.assertEqual(user_good["email"], test_email)
        self.assertTrue(user_good["unique_token"].startswith("libra_usr_"))
        self.assertIn(user_good["role"], ("guest", "tester"))

        # Re-using already verified code fails
        ok_reuse, _, _ = self.memory.verify_email_otp(test_email, code)
        self.assertFalse(ok_reuse)

    def test_04_primary_host_and_tester_role_assignment(self):
        """Test chenxuanchuah@gmail.com is strictly host and others default to tester unless promoted."""
        # 1. Primary host
        code1, _, _, *extra = self.memory.generate_email_otp("chenxuanchuah@gmail.com")
        ok1, user1, _ = self.memory.verify_email_otp("chenxuanchuah@gmail.com", code1)
        self.assertTrue(ok1)
        self.assertEqual(user1["role"], "host")

        # 2. Other account defaults to tester
        code2, _, _, *extra = self.memory.generate_email_otp("chenxuanchuah2@gmail.com")
        ok2, user2, _ = self.memory.verify_email_otp("chenxuanchuah2@gmail.com", code2)
        self.assertTrue(ok2)
        self.assertEqual(user2["role"], "tester", "Non-main account must default to tester role!")

    def test_05_google_authenticator_totp(self):
        """Test Google Authenticator TOTP secret generation, live code calculation and verification."""
        secret = generate_totp_secret()
        self.assertTrue(len(secret) >= 16)
        curr_code = get_current_totp_code(secret)
        self.assertEqual(len(curr_code), 6)
        self.assertTrue(curr_code.isdigit())
        self.assertTrue(verify_totp_code(secret, curr_code))
        self.assertFalse(verify_totp_code(secret, "000000"))

        # Verify through memorycore with a user's totp_secret
        email = "totp_user@example.com"
        user = self.memory.get_or_create_registered_user(email, default_role="guest", totp_secret=secret)
        self.assertEqual(user["totp_secret"], secret)

        # Authenticate with Google Authenticator code
        ok, u, _ = self.memory.verify_email_otp(email, curr_code)
        self.assertTrue(ok, "Expected Google Authenticator TOTP to be accepted")
        self.assertEqual(u["email"], email)

    def test_06_login_vs_signup_api_modes(self):
        """Test /api/auth/send-code differentiates login (requires existing) vs signup (blocks duplicate)."""
        new_email = "brand_new_unregistered@example.com"
        reg_email = "already_registered_user@example.com"
        self.memory.get_or_create_registered_user(reg_email, default_role="guest")

        # Login mode with unregistered email -> returns not_found
        res_login_bad = self.client.post("/api/auth/send-code", json={"email": new_email, "mode": "login"})
        self.assertEqual(res_login_bad.status_code, 200)
        self.assertEqual(res_login_bad.json()["status"], "not_found")

        # Signup mode with registered email -> returns already_exists
        res_signup_bad = self.client.post("/api/auth/send-code", json={"email": reg_email, "mode": "signup"})
        self.assertEqual(res_signup_bad.status_code, 200)
        self.assertEqual(res_signup_bad.json()["status"], "already_exists")

        # Signup mode with new email -> succeeds and returns dev_code
        res_signup_ok = self.client.post("/api/auth/send-code", json={"email": new_email, "mode": "signup"})
        self.assertEqual(res_signup_ok.status_code, 200)
        data = res_signup_ok.json()
        self.assertEqual(data["status"], "success")
        self.assertIsNotNone(data["dev_code"])

    def test_07_google_device_login_endpoint(self):
        """Test /api/auth/google-login logs in main host as host and others as tester."""
        # Test Main Host chenxuanchuah
        res_main = self.client.post("/api/auth/google-login", json={"email": "chenxuanchuah@gmail.com", "name": "Chuah Chen xuan"})
        self.assertEqual(res_main.status_code, 200)
        data_main = res_main.json()
        self.assertEqual(data_main["status"], "success")
        self.assertEqual(data_main["email"], "chenxuanchuah@gmail.com")
        self.assertEqual(data_main["role"], "host")

        # Test other account chenxuanchuah2
        res = self.client.post("/api/auth/google-login", json={"email": "chenxuanchuah2@gmail.com", "name": "Chuah Chen Xuan"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["email"], "chenxuanchuah2@gmail.com")
        self.assertEqual(data["role"], "tester")
        self.assertTrue(data["token"].startswith("libra_usr_"))

        # Test Hugo Chuah
        res_hugo = self.client.post("/api/auth/google-login", json={"email": "hugochuahchenyou@gmail.com", "name": "Hugo Chuah Chen you"})
        self.assertEqual(res_hugo.status_code, 200)
        data_hugo = res_hugo.json()
        self.assertEqual(data_hugo["status"], "success")
        self.assertEqual(data_hugo["email"], "hugochuahchenyou@gmail.com")
        self.assertEqual(data_hugo["role"], "tester")
        self.assertTrue(data_hugo["token"].startswith("libra_usr_"))

    def test_08_multi_user_chat_isolation(self):
        """Test User A and User B cannot see each other's sessions."""
        email_a = "alice_tester@example.com"
        email_b = "bob_tester@example.com"

        code_a, _, _, *extra = self.memory.generate_email_otp(email_a)
        _, user_a, _ = self.memory.verify_email_otp(email_a, code_a)
        tok_a = user_a["unique_token"]

        code_b, _, _, *extra = self.memory.generate_email_otp(email_b)
        _, user_b, _ = self.memory.verify_email_otp(email_b, code_b)
        tok_b = user_b["unique_token"]

        # Alice creates session
        res_a = self.client.post(
            "/api/sessions/new",
            json={"title": "Alice Secret Ideas"},
            headers={"Authorization": f"Bearer {tok_a}"}
        )
        self.assertEqual(res_a.status_code, 200)

        # Bob creates session
        res_b = self.client.post(
            "/api/sessions/new",
            json={"title": "Bob Coding Project"},
            headers={"Authorization": f"Bearer {tok_b}"}
        )
        self.assertEqual(res_b.status_code, 200)

        # Alice lists sessions -> only Alice's session visible
        res_list_a = self.client.get("/api/sessions", headers={"Authorization": f"Bearer {tok_a}"})
        titles_a = [s["title"] for s in res_list_a.json()["sessions"]]
        self.assertIn("Alice Secret Ideas", titles_a)
        self.assertNotIn("Bob Coding Project", titles_a)

        # Bob lists sessions -> only Bob's session visible
        res_list_b = self.client.get("/api/sessions", headers={"Authorization": f"Bearer {tok_b}"})
        titles_b = [s["title"] for s in res_list_b.json()["sessions"]]
        self.assertIn("Bob Coding Project", titles_b)
        self.assertNotIn("Alice Secret Ideas", titles_b)

    def test_09_user_management_api(self):
        """Test host user management: list, change role, invite, and delete."""
        # 1. Main host logs in to get host token
        res_host = self.client.post("/api/auth/google-login", json={"email": "chenxuanchuah@gmail.com"})
        host_tok = res_host.json()["token"]

        # Tester user logs in to get tester token
        res_tester = self.client.post("/api/auth/google-login", json={"email": "chenxuanchuah2@gmail.com"})
        tester_tok = res_tester.json()["token"]

        # 2. Tester tries to access /api/users -> 403 Forbidden
        res_forbidden = self.client.get("/api/users", headers={"Authorization": f"Bearer {tester_tok}"})
        self.assertEqual(res_forbidden.status_code, 403)

        # 3. Host lists all users
        res_users = self.client.get("/api/users", headers={"Authorization": f"Bearer {host_tok}"})
        self.assertEqual(res_users.status_code, 200)
        users = res_users.json()["users"]
        self.assertTrue(len(users) > 0)
        emails = [u["email"] for u in users]
        self.assertIn("chenxuanchuah@gmail.com", emails)

        # 4. Host invites a new user with role 'tester'
        invite_email = "team_tester_99@example.com"
        res_inv = self.client.post(
            "/api/users/invite",
            json={"email": invite_email, "role": "tester", "display_name": "Team Tester"},
            headers={"Authorization": f"Bearer {host_tok}"}
        )
        self.assertEqual(res_inv.status_code, 200)

        # 5. Host promotes team_tester_99 to 'host'
        res_promo = self.client.post(
            "/api/users/role",
            json={"email": invite_email, "role": "host"},
            headers={"Authorization": f"Bearer {host_tok}"}
        )
        self.assertEqual(res_promo.status_code, 200)

        # Verify role changed in DB
        u_rec = self.memory.get_registered_user_by_email(invite_email)
        self.assertEqual(u_rec["role"], "host")

        # 6. Demote back to 'tester'
        res_demo = self.client.post(
            "/api/users/role",
            json={"email": invite_email, "role": "tester"},
            headers={"Authorization": f"Bearer {host_tok}"}
        )
        self.assertEqual(res_demo.status_code, 200)
        self.assertEqual(self.memory.get_registered_user_by_email(invite_email)["role"], "tester")

        # 7. Host attempts to demote primary host -> 400 Bad Request
        res_bad_demo = self.client.post(
            "/api/users/role",
            json={"email": "chenxuanchuah@gmail.com", "role": "tester"},
            headers={"Authorization": f"Bearer {host_tok}"}
        )
        self.assertEqual(res_bad_demo.status_code, 400)

        # 8. Host deletes the invited user
        res_del = self.client.delete(f"/api/users/{invite_email}", headers={"Authorization": f"Bearer {host_tok}"})
        self.assertEqual(res_del.status_code, 200)
        self.assertIsNone(self.memory.get_registered_user_by_email(invite_email))


if __name__ == "__main__":
    unittest.main()
