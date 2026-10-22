"""
Project Libra Version & Build Metadata.
Central source of truth for Project Libra's semantic version and reload tracking.
"""

LIBRA_VERSION = "10.2.0"
LIBRA_CODENAME = "Argon-RemoteWeb"
BUILD_DATE = "2026-10-22"

def get_full_version_string(reload_count: int = 0) -> str:
    """Return formatted version string with reload revision if applicable."""
    if reload_count > 0:
        return f"v{LIBRA_VERSION}-r{reload_count}"
    return f"v{LIBRA_VERSION}"
