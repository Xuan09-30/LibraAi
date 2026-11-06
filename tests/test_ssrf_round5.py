import pytest
import socket
from unittest.mock import patch, MagicMock
import httpx

from core.research import is_safe_public_url, HardenedResearchEngine
from tools.free_utilities import FreeUtilityBelt


def test_hostname_resolving_to_127_0_0_1_blocked():
    """Round 5 Item 4: A hostname resolving to 127.0.0.1 must be blocked."""
    belt = FreeUtilityBelt()

    # Mock socket.getaddrinfo for a custom domain resolving to 127.0.0.1
    def mock_getaddrinfo(host, port, *args, **kwargs):
        if host == "spoofed-local.example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]

    with patch("socket.getaddrinfo", side_effect=mock_getaddrinfo):
        # 1. is_safe_public_url
        assert is_safe_public_url("http://spoofed-local.example.com/status") is False
        assert is_safe_public_url("https://spoofed-local.example.com:8080/admin") is False

        # 2. ping_check
        res = belt.check_network_ping(target_host="spoofed-local.example.com")
        assert res.get("status") == "blocked"
        assert "blocked" in res.get("voice_response", "").lower()


def test_ipv6_loopback_blocked():
    """Round 5 Item 4: An IPv6 loopback (::1 or hostname resolving to ::1) must be blocked."""
    belt = FreeUtilityBelt()

    # Direct IPv6 loopback URL and ping target
    assert is_safe_public_url("http://[::1]/") is False
    assert is_safe_public_url("https://[::1]:8443/secret") is False

    res_direct = belt.check_network_ping(target_host="::1")
    assert res_direct.get("status") == "blocked"

    # Hostname resolving to ::1
    def mock_getaddrinfo(host, port, *args, **kwargs):
        if host == "ipv6-loopback.example.com":
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 80, 0, 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]

    with patch("socket.getaddrinfo", side_effect=mock_getaddrinfo):
        assert is_safe_public_url("http://ipv6-loopback.example.com/data") is False
        res = belt.check_network_ping(target_host="ipv6-loopback.example.com")
        assert res.get("status") == "blocked"


def test_redirect_to_169_254_169_254_blocked():
    """
    Round 5 Item 4:
    A redirect to 169.254.169.254 (AWS/cloud metadata service) must be re-validated
    and blocked on the redirect hop.
    """
    engine = HardenedResearchEngine()
    test_url = "http://public-site.com/bounce"

    # Clean any previous cached test entry
    try:
        conn = engine._get_conn()
        conn.execute("DELETE FROM web_cache WHERE url = ?", (test_url,))
        conn.commit()
        conn.close()
    except Exception:
        pass

    # Simulate an HTTP server responding with 302 redirecting to http://169.254.169.254/latest/meta-data/
    def handler(request: httpx.Request):
        if request.url == test_url:
            return httpx.Response(
                302,
                headers={"Location": "http://169.254.169.254/latest/meta-data/"},
                request=request
            )
        elif "169.254.169.254" in str(request.url):
            return httpx.Response(200, text="<html><body><article><p>" + "This is stolen secret AWS metadata IAM role payload with credentials " * 20 + "</p></article></body></html>", request=request)
        return httpx.Response(404, request=request)

    # Allow public-site.com to pass initial is_safe_public_url check
    orig_is_safe = is_safe_public_url
    def mock_safe(url):
        if "169.254.169.254" in url:
            return False
        if "public-site.com" in url:
            return True
        return orig_is_safe(url)

    mock_transport = httpx.MockTransport(handler)

    try:
        with patch("core.research.is_safe_public_url", side_effect=mock_safe), \
             patch("httpx.get", side_effect=lambda url, **kw: httpx.Client(transport=mock_transport, **kw).get(url)), \
             patch("trafilatura.fetch_url", return_value=None):
            res = engine.clean_markdown_extract(test_url)
            # Must be blocked and return None, NEVER returning metadata contents
            assert res is None, f"Expected redirect to 169.254.169.254 to be blocked, but got: {res}"
    finally:
        try:
            conn = engine._get_conn()
            conn.execute("DELETE FROM web_cache WHERE url = ?", (test_url,))
            conn.commit()
            conn.close()
        except Exception:
            pass
