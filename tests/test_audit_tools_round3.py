import os
import sys
import unittest
import asyncio

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.free_utilities import FreeUtilityBelt
from core.orchestrator import REMOTE_WEB_ALLOWED_TOOLS, REMOTE_HOST_ALLOWED_TOOLS, SupervisorHub
from core.llm import LocalLLM


class TestAuditToolsRound3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.belt = FreeUtilityBelt()
        cls.llm = LocalLLM()
        cls.hub = SupervisorHub(cls.llm)

    def test_01_math_eval_ast_safety(self):
        """Verify math_eval safely parses math via AST and blocks function calls, attributes, and malicious syntax."""
        # Valid math
        res_valid = self.belt.evaluate_math_or_unit("calculate 15 * (4 + 6)")
        self.assertEqual(res_valid.get("status"), "success")
        self.assertEqual(res_valid.get("result"), 150)

        # Rejection of function calls or code injection
        res_inj1 = self.belt.evaluate_math_or_unit("what is __import__('os').system('calc')")
        self.assertEqual(res_inj1.get("status"), "error")

        # Huge exponent rejection (denial of service defense)
        res_exp = self.belt.evaluate_math_or_unit("what is 2 to the power of 5000")
        self.assertEqual(res_exp.get("status"), "error")

    def test_02_ping_check_ssrf_blocking(self):
        """Verify check_network_ping blocks localhost, private IPs, and metadata services."""
        # Private / loopback host targets must be rejected
        blocked_targets = [
            "127.0.0.1",
            "localhost",
            "::1",
            "192.168.1.1",
            "10.0.0.1",
            "172.16.0.1",
            "169.254.169.254",
        ]
        for target in blocked_targets:
            res = self.belt.check_network_ping(target_host=target)
            self.assertEqual(res.get("status"), "blocked", f"Target {target} must be blocked by ping_check!")
            self.assertIn("Private or local network targets are blocked", res.get("voice_response", ""))

    def test_03_research_ssrf_blocking(self):
        """Verify web_search and deep_research extractors block SSRF to localhost and private ranges."""
        from core.research import is_safe_public_url, HardenedResearchEngine
        engine = HardenedResearchEngine()

        # is_safe_public_url validator check
        self.assertFalse(is_safe_public_url("http://127.0.0.1:8765/api/vitals"))
        self.assertFalse(is_safe_public_url("http://localhost:8765"))
        self.assertFalse(is_safe_public_url("http://169.254.169.254/latest/meta-data/"))
        self.assertFalse(is_safe_public_url("http://192.168.1.1/admin"))
        self.assertFalse(is_safe_public_url("http://10.0.0.1/"))
        self.assertTrue(is_safe_public_url("https://www.google.com"))

        # clean_markdown_extract refuses SSRF targets
        res_sync = engine.clean_markdown_extract("http://127.0.0.1:8765/api/vitals")
        self.assertIsNone(res_sync, "clean_markdown_extract must return None for SSRF target!")

        # async_clean_markdown_extract refuses SSRF targets
        res_async = asyncio.run(engine.async_clean_markdown_extract("http://169.254.169.254/latest/meta-data"))
        self.assertIsNone(res_async, "async_clean_markdown_extract must return None for SSRF target!")

    def test_04_vision_qa_removed_from_remote_scopes(self):
        """Verify vision_qa is removed from REMOTE_WEB_ALLOWED_TOOLS and REMOTE_HOST_ALLOWED_TOOLS."""
        self.assertNotIn(
            "vision_qa",
            REMOTE_WEB_ALLOWED_TOOLS,
            "vision_qa can capture the host screen and must NOT be in REMOTE_WEB_ALLOWED_TOOLS!"
        )
        self.assertNotIn(
            "vision_qa",
            REMOTE_HOST_ALLOWED_TOOLS,
            "vision_qa can capture the host screen and must NOT be in REMOTE_HOST_ALLOWED_TOOLS!"
        )

        # Orchestrator blocks vision_qa in remote_host and remote_web scopes
        for scope in ["remote_web", "remote_host"]:
            res = self.hub.process_command("look at my screen and tell me what is showing", client_scope=scope, dry_run=True)
            self.assertEqual(res.get("status"), "blocked")
            self.assertEqual(res.get("action"), "sandboxed_blocked")


if __name__ == "__main__":
    unittest.main()
