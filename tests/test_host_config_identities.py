"""
=============================================================================
TEST SUITE: CONFIG-BASED HOST IDENTITIES
Target: tests/test_host_config_identities.py
Verifies:
  1. Host eligibility is dynamically read from config ("host_identities"),
     NOT hardcoded in source.
  2. Users with emails or GitHub usernames listed in config get role="host".
  3. Unconfigured emails/usernames do NOT receive host role, proving no
     hardcoded fallback bypasses the configuration.
=============================================================================
"""

import os
import sys
import unittest
from unittest.mock import patch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.memory import MemoryCore, is_host_identity, get_host_identities


class TestHostConfigIdentities(unittest.TestCase):
    def setUp(self):
        self.memory = MemoryCore(db_path=":memory:")

    def test_01_host_eligibility_read_from_config_not_hardcoded(self):
        """
        Confirms host eligibility is determined strictly via config
        ('host_identities' block) and not hardcoded strings in source code.
        """
        mock_host_config = {
            "emails": ["configured_director@corp.internal", "configured_lead@corp.internal"],
            "github_usernames": ["configured_lead_gh"]
        }

        with patch("core.memory.get_host_identities", return_value=mock_host_config):
            # 1. Configured email is recognized as host
            self.assertTrue(
                is_host_identity(email="configured_director@corp.internal"),
                "Configured email must be recognized as host"
            )
            # Case-insensitivity check
            self.assertTrue(
                is_host_identity(email="CONFIGURED_LEAD@corp.internal"),
                "Configured email check must be case-insensitive"
            )

            # 2. Configured GitHub username is recognized as host
            self.assertTrue(
                is_host_identity(github_username="configured_lead_gh"),
                "Configured GitHub username must be recognized as host"
            )
            self.assertTrue(
                is_host_identity(github_username="Configured_Lead_GH"),
                "Configured GitHub username check must be case-insensitive"
            )

            # 3. Unconfigured email/username is NOT recognized as host
            self.assertFalse(
                is_host_identity(email="random_stranger@example.com"),
                "Unconfigured email must NOT be recognized as host"
            )
            self.assertFalse(
                is_host_identity(github_username="random_gh_user"),
                "Unconfigured GitHub user must NOT be recognized as host"
            )

            # 4. Canonical user creation honors dynamic config
            host_user = self.memory.create_canonical_user(
                primary_email="configured_director@corp.internal",
                display_name="Director Host"
            )
            self.assertEqual(
                host_user["role"],
                "host",
                "User with configured host email must receive role='host'"
            )

            gh_host_user = self.memory.create_canonical_user(
                primary_email="other_email@example.com",
                display_name="GH Lead",
                github_username="configured_lead_gh"
            )
            self.assertEqual(
                gh_host_user["role"],
                "host",
                "User with configured host GitHub username must receive role='host'"
            )

            normal_user = self.memory.create_canonical_user(
                primary_email="normal_dev@corp.internal",
                display_name="Normal Dev"
            )
            self.assertNotEqual(
                normal_user["role"],
                "host",
                "User without host identity must not receive role='host'"
            )


if __name__ == "__main__":
    unittest.main()
