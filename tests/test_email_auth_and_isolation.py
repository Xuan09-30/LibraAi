"""
=============================================================================
TEST SUITE: SECURE EMAIL AUTHENTICATION, OTP VERIFICATION & CHAT ISOLATION
Target: tests/test_email_auth_and_isolation.py
Verifies:
  1. OTP generation, uniqueness, and email dispatch fallback logging
  2. OTP verification with attempt limiting and expiration
  3. Google Authenticator TOTP calculation & validation
  4. Alt host account (REDACTED) receiving role='host'
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
        cls.admin_email = cls.cfg.get("admin_email", "REDACTED")
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
        """Test REDACTED is strictly host and others default to tester unless promoted."""
        # 1. Primary host
        code1, _, _, *extra = self.memory.generate_email_otp("REDACTED")
        ok1, user1, _ = self.memory.verify_email_otp("REDACTED", code1)
        self.assertTrue(ok1)
        self.assertEqual(user1["role"], "host")

        # 2. Other account defaults to tester
        code2, _, _, *extra = self.memory.generate_email_otp("REDACTED")
        ok2, user2, _ = self.memory.verify_email_otp("REDACTED", code2)
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
        res_main = self.client.post("/api/auth/google-login", json={"email": "REDACTED", "name": "Chuah Chen xuan"})
        self.assertEqual(res_main.status_code, 200)
        data_main = res_main.json()
        self.assertEqual(data_main["status"], "success")
        self.assertEqual(data_main["email"], "REDACTED")
        self.assertEqual(data_main["role"], "host")

        # Test other account chenxuanchuah2
        res = self.client.post("/api/auth/google-login", json={"email": "REDACTED", "name": "Chuah Chen Xuan"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["email"], "REDACTED")
        self.assertEqual(data["role"], "tester")
        self.assertTrue(data["token"].startswith("libra_usr_"))

        # Test Hugo Chuah
        res_hugo = self.client.post("/api/auth/google-login", json={"email": "REDACTED", "name": "Hugo Chuah Chen you"})
        self.assertEqual(res_hugo.status_code, 200)
        data_hugo = res_hugo.json()
        self.assertEqual(data_hugo["status"], "success")
        self.assertEqual(data_hugo["email"], "REDACTED")
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
        res_host = self.client.post("/api/auth/google-login", json={"email": "REDACTED"})
        host_tok = res_host.json()["token"]

        # Tester user logs in to get tester token
        res_tester = self.client.post("/api/auth/google-login", json={"email": "REDACTED"})
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
        self.assertIn("REDACTED", emails)

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
            json={"email": "REDACTED", "role": "tester"},
            headers={"Authorization": f"Bearer {host_tok}"}
        )
        self.assertEqual(res_bad_demo.status_code, 400)

        # 8. Host deletes the invited user
        res_del = self.client.delete(f"/api/users/{invite_email}", headers={"Authorization": f"Bearer {host_tok}"})
        self.assertEqual(res_del.status_code, 200)
        self.assertIsNone(self.memory.get_registered_user_by_email(invite_email))

    def test_10_server_side_client_scope_and_403_on_local_desktop_spoof(self):
        """
        Tier 1 Security: Derive client_scope server-side from the auth token, never from the request body.
        Sending 'client_scope': 'local_desktop' as a remote user must return HTTP 403.
        """
        # Authenticate as a remote tester user
        res_tester = self.client.post(
            "/api/auth/google-login",
            json={"email": "spoof_tester@example.com", "display_name": "Spoof Tester"}
        )
        self.assertEqual(res_tester.status_code, 200)
        tester_tok = res_tester.json()["token"]
        tester_headers = {"Authorization": f"Bearer {tester_tok}"}

        # 1. Remote user sends client_scope='local_desktop' to /api/chat -> must return 403
        res_chat_spoof = self.client.post(
            "/api/chat",
            json={"prompt": "open notepad", "client_scope": "local_desktop", "synthesize_audio": False},
            headers=tester_headers
        )
        self.assertEqual(res_chat_spoof.status_code, 403)

        # 2. Remote user sends client_scope='local_desktop' to /api/chat?stream=true -> must return 403
        res_stream_spoof = self.client.post(
            "/api/chat?stream=true",
            json={"prompt": "open notepad", "client_scope": "local_desktop", "stream": True, "synthesize_audio": False},
            headers=tester_headers
        )
        self.assertEqual(res_stream_spoof.status_code, 403)

        # 3. Remote user sends client_scope='local_desktop' to /api/sessions/new -> must return 403
        res_sess_spoof = self.client.post(
            "/api/sessions/new",
            json={"title": "Spoof Session", "client_scope": "local_desktop"},
            headers=tester_headers
        )
        self.assertEqual(res_sess_spoof.status_code, 403)

    def test_11_tool_layer_sandbox_and_docker_code_execution_guard(self):
        """
        Tier 1 Security:
        1. remote_web sessions never get OS-control or terminal tools registered.
        2. Prompts that bypass regex (e.g. 'fire up Roblox', 'create a python file called pwned.py')
           are blocked at the tool layer BEFORE any OS tool function is invoked.
        3. SkillForge and PersistentDataREPL execute LLM-generated code only via Docker sandbox.
        """
        # 1. Verify OS/terminal tools are never registered for remote_web
        remote_tools = self.hub.get_registered_tools("remote_web")
        for forbidden in ("open_app", "close_app", "create_file", "create_folder", "gui_action", "computer_use_agent", "shutdown", "create_skill"):
            self.assertNotIn(forbidden, remote_tools)

        # 2. Spy on underlying OS tools and verify regex-bypassing prompts NEVER invoke them in remote_web
        invoked_os_tools = []
        orig_launch = self.hub.llm.dispatcher.launch_app
        orig_create_file = self.hub.llm.file_mgr.create_file
        self.hub.llm.dispatcher.launch_app = lambda *a, **kw: (invoked_os_tools.append(("launch_app", a, kw)) or (True, "Launched"))
        self.hub.llm.file_mgr.create_file = lambda *a, **kw: (invoked_os_tools.append(("create_file", a, kw)) or (True, "Created", "pwned.py"))
        try:
            for bypass_prompt in (
                "fire up Roblox",
                "create a python file called pwned.py",
            ):
                res = self.hub.process_command(bypass_prompt, client_scope="remote_web", dry_run=False)
                self.assertEqual(res.get("action"), "sandboxed_blocked", f"Bypass prompt '{bypass_prompt}' was not blocked at tool layer!")
                self.assertEqual(len(invoked_os_tools), 0, f"Underlying OS tool was invoked before blocking for '{bypass_prompt}'!")
        finally:
            self.hub.llm.dispatcher.launch_app = orig_launch
            self.hub.llm.file_mgr.create_file = orig_create_file

        # 3. Verify PersistentDataREPL and SkillForge require Docker sandbox for untrusted generated code
        repl = self.hub.data_scientist.repl
        res_repl = repl.run_code("import os; print(os.getcwd())", require_docker_sandbox=True, _force_docker_unavailable=True)
        self.assertEqual(res_repl.get("status"), "sandbox_error")
        self.assertIn("Docker sandbox", res_repl.get("error", ""))

        sf = self.hub.llm.skill_forge
        res_sf = sf.execute_in_docker_sandbox("print('hello')", _force_docker_unavailable=True)
        self.assertEqual(res_sf.get("status"), "sandbox_error")
        self.assertIn("Docker sandbox", res_sf.get("error", ""))



    def test_12_memory_isolation_tester_cannot_write_host_vault_or_lessons(self):
        """
        Tier 1 Security:
        Isolate memory per user so a Tester cannot write to the Host's vault (assets/vault/)
        or LESSONS.md, nor overwrite Host semantic facts.
        """
        tester = self.memory.get_or_create_registered_user("tester_mem@example.com")
        tester_headers = {"Authorization": f"Bearer {tester['unique_token']}"}

        # 1. Tester attempting to POST/PUT/DELETE on /api/vault is rejected with 403
        r_post = self.client.post(
            "/api/vault",
            json={"entity": "host_pc", "relation": "owner", "value": "tester_spoof"},
            headers=tester_headers
        )
        self.assertEqual(r_post.status_code, 403)

        # 2. Direct memory calls with non-host role must not write to Host LESSONS.md or Host vault
        lid = self.memory.record_correction(
            "open browser",
            "opened edge",
            "open chrome",
            user_email="tester_mem@example.com",
            role="tester"
        )
        self.assertEqual(lid, -1, "Tester should not be permitted to write operational rules to Host LESSONS.md!")

        fid = self.memory.upsert_semantic_fact(
            "user",
            "favorite_drink",
            "matcha",
            user_email="tester_mem@example.com",
            role="tester"
        )
        # Host semantic facts for entity='user' must not be polluted by tester
        host_facts = self.memory.get_semantic_facts(entity="user")
        self.assertFalse(any(f.get("value") == "matcha" for f in host_facts))

    def test_13_hashed_expiring_invite_tokens_and_rate_limiting(self):
        """
        Tier 1 Security:
        1. Guest/invite tokens are stored hashed (SHA-256) in SQLite, never in plaintext,
           and enforce expiration by default.
        2. Rate limiting returns HTTP 429 when request burst exceeds limit.
        """
        # 1. Create guest token and inspect raw SQLite table to verify hashed storage & default expiry
        created = self.memory.create_guest_token(label="TempEvaluator")
        raw_tok = created["token"]
        self.assertTrue(raw_tok.startswith("libra_guest_"))
        self.assertIsNotNone(created.get("expires_at"), "Guest token must have an expiration timestamp by default!")

        conn = self.memory._get_connection()
        rows = conn.execute("SELECT token FROM guest_tokens WHERE label = 'TempEvaluator' ORDER BY rowid DESC").fetchall()
        if self.memory.db_path != ":memory:":
            conn.close()
        self.assertGreaterEqual(len(rows), 1)
        stored_tok = rows[0][0]
        self.assertNotEqual(stored_tok, raw_tok, "Plaintext guest token must not be stored in SQLite!")
        self.assertTrue(stored_tok.startswith("sha256:"))

        # Validation still works with raw token
        valid = self.memory.validate_guest_token(raw_tok)
        self.assertIsNotNone(valid)
        self.assertEqual(valid["label"], "TempEvaluator")

        # Expired token is rejected
        expired = self.memory.create_guest_token(label="ExpiredEval", expires_in_days=-1)
        self.assertIsNone(self.memory.validate_guest_token(expired["token"]))

        # 2. Rate limiting check on /api/chat
        tester = self.memory.get_or_create_registered_user("ratelimit_user@example.com")
        headers = {"Authorization": f"Bearer {tester['unique_token']}"}
        self.app.state.rate_limit_max_requests = 3
        try:
            statuses = []
            for i in range(5):
                r = self.client.post("/api/chat", json={"prompt": "what time is it"}, headers=headers)
                statuses.append(r.status_code)
            self.assertIn(429, statuses, f"Expected HTTP 429 rate limit in statuses, got {statuses}")
        finally:
            self.app.state.rate_limit_max_requests = 60


    def test_14_round2_item_a_remote_scope_restrictions(self):
        """
        Round 2 Item A: Remote scope audit and restrictions:
        A.2: remote_host must NOT get OS-control or terminal tools (open_app, close_app, create_file,
             create_folder, gui_action, computer_use_agent, shutdown, create_skill) over the tunnel.
             Make them local_desktop-only. Test: a remote_host session cannot call any of them.
        A.3: remote_web: confirm forget_memory, recall_memory, remember_fact only touch that user's
             namespace (user:<email>:*), never the host's facts.
        A.4: document_rag in remote scopes: restrict to files uploaded by that user. Reject arbitrary
             paths and path traversal (..). Test both.
        A.5: daily_briefing and hardware vitals must not be returned to remote_web (Tester/Guest).
             Remove from their registered tools or redact host details.
        """
        local_tools = self.hub.get_registered_tools("local_desktop")
        remote_host_tools = self.hub.get_registered_tools("remote_host")
        remote_web_tools = self.hub.get_registered_tools("remote_web")

        # A.2: OS-control and terminal tools must be local_desktop-only (not in remote_host or remote_web)
        forbidden_os_tools = (
            "open_app", "close_app", "create_file", "create_folder",
            "gui_action", "computer_use_agent", "shutdown", "create_skill"
        )
        for tool_name in forbidden_os_tools:
            self.assertIn(tool_name, local_tools)
            self.assertNotIn(tool_name, remote_host_tools, f"OS tool '{tool_name}' must NOT be registered for remote_host!")
            self.assertNotIn(tool_name, remote_web_tools, f"OS tool '{tool_name}' must NOT be registered for remote_web!")

        # Test that a remote_host session cannot call any of them
        os_test_prompts = [
            "open calculator",
            "close chrome",
            "create file test_remote_host.txt",
            "create folder test_remote_host_dir",
            "click the start button",
            "open chrome and go to youtube.com and search for cats",
            "shutdown my computer",
            "create a skill to check disk usage",
        ]
        for p in os_test_prompts:
            res = self.hub.process_command(p, client_scope="remote_host", dry_run=False)
            self.assertEqual(res.get("action"), "sandboxed_blocked", f"Prompt '{p}' was not blocked in remote_host: {res}")

        # Also test /api/chat as remote host over tunnel (with x-forwarded-for proxy header)
        host_user = self.memory.get_or_create_registered_user("REDACTED", default_role="host")
        host_headers = {
            "Authorization": f"Bearer {host_user['unique_token']}",
            "X-Forwarded-For": "203.0.113.42"
        }
        res_chat_host = self.client.post(
            "/api/chat",
            json={"prompt": "open notepad", "synthesize_audio": False},
            headers=host_headers
        )
        self.assertEqual(res_chat_host.status_code, 200)
        self.assertIn(res_chat_host.json().get("action"), ("sandboxed_blocked", "remote_sandbox_blocked"))

        # A.3: remote_web forget_memory, recall_memory, remember_fact only touch user:<email>:* namespace
        for mem_tool in ("forget_memory", "recall_memory", "remember_fact"):
            self.assertIn(mem_tool, remote_web_tools, f"'{mem_tool}' must be registered for remote_web!")

        # Seed a host fact
        self.memory.remember_fact("My secret host project codename is Project Apollo", user_email="REDACTED", role="host")

        # Authenticate as remote_web tester
        tester_email = "alice_tester@example.com"
        self.hub.llm.active_user_email = tester_email
        self.hub.llm.active_user_role = "tester"

        # 1. Tester remembers a fact -> stored under user:alice_tester@example.com:*
        res_rem = self.hub.process_command("Remember that my favorite color is turquoise", client_scope="remote_web", dry_run=False)
        self.assertEqual(res_rem.get("action"), "remember_fact")

        # Verify category in DB has user:<email>: prefix
        conn = self.memory._get_connection()
        rows_alice = conn.execute(
            "SELECT category, content FROM facts WHERE LOWER(user_email) = ?",
            (tester_email,)
        ).fetchall()
        if self.memory.db_path != ":memory:":
            conn.close()
        self.assertTrue(any(r[0].startswith(f"user:{tester_email}:") and "turquoise" in r[1] for r in rows_alice))

        # 2. Tester tries to recall host's secret codename -> must NOT return host fact
        recalled_by_alice = self.memory.recall_relevant("Project Apollo", user_email=tester_email)
        self.assertEqual(len(recalled_by_alice), 0, "Tester must not recall host facts!")

        # 3. Tester tries to forget host's secret codename -> must NOT delete host fact
        res_forget_host = self.hub.process_command("Forget about Project Apollo", client_scope="remote_web", dry_run=False)
        self.assertEqual(res_forget_host.get("action"), "forget_memory")
        host_recalled = self.memory.recall_relevant("Project Apollo", user_email="REDACTED")
        self.assertGreaterEqual(len(host_recalled), 1, "Host fact was deleted by remote_web tester!")

        # 4. Tester forgets their own fact -> succeeds
        res_forget_own = self.hub.process_command("Forget about turquoise", client_scope="remote_web", dry_run=False)
        self.assertEqual(res_forget_own.get("action"), "forget_memory")
        self.assertEqual(len(self.memory.recall_relevant("turquoise", user_email=tester_email)), 0)

        # A.4: document_rag in remote scopes restricted to files uploaded by that user; reject arbitrary paths and ..
        # 1. Arbitrary path in remote_web -> rejected
        rag_arb = self.hub.llm.document_rag.query_document(
            "README.md",
            "Summarize this file",
            dry_run=True,
            client_scope="remote_web",
            user_email=tester_email
        )
        self.assertEqual(rag_arb.get("status"), "forbidden", f"Expected arbitrary path to be forbidden in remote_web, got {rag_arb}")

        # 2. Path traversal (..) in remote_web and remote_host -> rejected
        for trav_path in ("../config.json", "..\\config.local.json", "assets/uploads/../../README.md"):
            rag_trav = self.hub.llm.document_rag.query_document(
                trav_path,
                "What is inside?",
                dry_run=True,
                client_scope="remote_host",
                user_email="REDACTED"
            )
            self.assertEqual(rag_trav.get("status"), "forbidden", f"Expected path traversal '{trav_path}' to be forbidden, got {rag_trav}")

        # 3. File uploaded by that user succeeds in remote_web, but another user cannot read it
        tester_user = self.memory.get_or_create_registered_user(tester_email, default_role="tester")
        tester_headers = {"Authorization": f"Bearer {tester_user['unique_token']}"}
        up_res = self.client.post(
            "/api/upload",
            files={"file": ("alice_notes.txt", b"Alice private research notes about quantum computing.", "text/plain")},
            headers=tester_headers
        )
        self.assertEqual(up_res.status_code, 200)
        alice_file_path = up_res.json()["file_path"]

        # Alice can query her own uploaded file in remote_web
        rag_own = self.hub.llm.document_rag.query_document(
            alice_file_path,
            "What are the notes about?",
            dry_run=True,
            client_scope="remote_web",
            user_email=tester_email
        )
        self.assertEqual(rag_own.get("status"), "success", f"Expected Alice's own upload to succeed, got {rag_own}")

        # Bob (another remote_web user) cannot query Alice's uploaded file
        rag_other = self.hub.llm.document_rag.query_document(
            alice_file_path,
            "What are the notes about?",
            dry_run=True,
            client_scope="remote_web",
            user_email="bob_tester@example.com"
        )
        self.assertEqual(rag_other.get("status"), "forbidden", f"Expected Bob to be forbidden from reading Alice's upload, got {rag_other}")

        # A.5: daily_briefing and hardware vitals (system_status) must not be returned to remote_web
        self.assertNotIn("daily_briefing", remote_web_tools)
        self.assertNotIn("system_status", remote_web_tools)

        res_brief = self.hub.process_command("give me my daily briefing", client_scope="remote_web", dry_run=False)
        self.assertEqual(res_brief.get("action"), "sandboxed_blocked")

        res_vitals_cmd = self.hub.process_command("check system status and cpu usage", client_scope="remote_web", dry_run=False)
        self.assertEqual(res_vitals_cmd.get("action"), "sandboxed_blocked")

        # HTTP /api/vitals must not return host hardware details to remote_web (Tester/Guest)
        res_vitals_http = self.client.get("/api/vitals", headers=tester_headers)
        self.assertEqual(res_vitals_http.status_code, 403)



    def test_15_round2_item_d_docker_sandbox_hardening(self):
        """
        Round 2 Item D: Docker sandbox hardening:
        1. Add to the docker run flags: --cap-drop ALL, --security-opt no-new-privileges,
           --pids-limit 128, run as a non-root user (--user 65534:65534 or --user nobody),
           and --tmpfs /tmp so --read-only doesn't break scripts.
        2. Confirm no host folder is mounted writable.
        3. Done when: a test runs a normal analysis script successfully inside the hardened
           container, and a test confirms the container cannot write outside /tmp or reach the network.
        """
        repl = self.hub.data_scientist.repl
        sf = self.hub.llm.skill_forge

        # 1. Inspect the exact docker run command flags for both PersistentDataREPL and SkillForge
        repl_cmd = repl.build_docker_sandbox_command("print(1+1)")
        sf_cmd = sf.build_docker_sandbox_command("print(1+1)")

        for label, cmd in (("PersistentDataREPL", repl_cmd), ("SkillForge", sf_cmd)):
            cmd_str = " ".join(cmd)
            self.assertIn("--cap-drop", cmd, f"{label} missing --cap-drop")
            self.assertEqual(cmd[cmd.index("--cap-drop") + 1], "ALL")
            self.assertIn("--security-opt", cmd, f"{label} missing --security-opt")
            self.assertEqual(cmd[cmd.index("--security-opt") + 1], "no-new-privileges")
            self.assertIn("--pids-limit", cmd, f"{label} missing --pids-limit")
            self.assertEqual(cmd[cmd.index("--pids-limit") + 1], "128")
            self.assertIn("--user", cmd, f"{label} missing --user")
            self.assertIn(cmd[cmd.index("--user") + 1], ("65534:65534", "nobody"))
            self.assertIn("--tmpfs", cmd, f"{label} missing --tmpfs")
            self.assertTrue(cmd[cmd.index("--tmpfs") + 1].startswith("/tmp"))
            self.assertIn("--read-only", cmd)
            self.assertIn("--network", cmd)
            self.assertEqual(cmd[cmd.index("--network") + 1], "none")
            # Confirm no host folder is mounted (-v or --volume or --mount)
            self.assertNotIn("-v", cmd, f"{label} must not mount any host folder")
            self.assertNotIn("--volume", cmd, f"{label} must not mount any host folder")
            self.assertNotIn("--mount", cmd, f"{label} must not mount any host folder")

        # 2. Run a normal analysis script inside the hardened container (uses /tmp for temporary files)
        normal_analysis_code = (
            "import tempfile, os, json\n"
            "with open('/tmp/analysis_scratch.json', 'w') as f:\n"
            "    json.dump({'values': [10, 20, 30, 40], 'mean': 25.0}, f)\n"
            "with open('/tmp/analysis_scratch.json', 'r') as f:\n"
            "    data = json.load(f)\n"
            "print(f\"MEAN={data['mean']}\")\n"
        )
        res_ok = repl.run_in_docker_sandbox(normal_analysis_code, _simulate_if_no_daemon=True)
        self.assertEqual(res_ok.get("status"), "success", f"Expected normal analysis script to succeed in hardened container: {res_ok}")
        self.assertIn("MEAN=25.0", res_ok.get("stdout", ""))

        # 3. Confirm the container CANNOT write outside /tmp (read-only rootfs & non-root user 65534:65534)
        write_outside_tmp_code = (
            "with open('/etc/pwned.txt', 'w') as f:\n"
            "    f.write('escape')\n"
        )
        res_ro = repl.run_in_docker_sandbox(write_outside_tmp_code, _simulate_if_no_daemon=True)
        self.assertEqual(res_ro.get("status"), "error", "Writing outside /tmp must fail inside read-only container!")
        self.assertTrue(
            any(k in (res_ro.get("error") or "").lower() for k in ("read-only", "permission", "read only", "oserror", "permissionerror")),
            f"Expected read-only or permission error, got: {res_ro}"
        )

        # 4. Confirm the container CANNOT reach the network (--network none)
        network_attempt_code = (
            "import socket\n"
            "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "s.settimeout(1.0)\n"
            "s.connect(('8.8.8.8', 53))\n"
        )
        res_net = repl.run_in_docker_sandbox(network_attempt_code, _simulate_if_no_daemon=True)
        self.assertEqual(res_net.get("status"), "error", "Outbound network access must fail inside --network none container!")
        self.assertTrue(
            any(k in (res_net.get("error") or "").lower() for k in ("network", "unreachable", "blocked", "oserror", "permission")),
            f"Expected network error, got: {res_net}"
        )

if __name__ == "__main__":
    unittest.main()

