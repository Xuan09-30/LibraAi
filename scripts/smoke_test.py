"""
Project Libra - Fast Comprehensive Smoke Test
Runs in under 30 seconds.
1. Dynamically imports every python module across core/, tools/, ui/, and web/
   to verify zero import-time exceptions, missing dependencies, or sys.path issues.
2. Spawns the web server on an isolated test port, hits /api/health and /,
   and verifies HTTP 200 responses.
"""

import os
import sys
import time
import socket
import importlib
import threading
import urllib.request
import json
from typing import List, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_imports() -> Tuple[int, List[Tuple[str, str]]]:
    """Imports every python module under core/, tools/, ui/, web/."""
    folders = ["core", "tools", "ui", "web"]
    passed_count = 0
    failures = []

    for folder in folders:
        folder_path = os.path.join(PROJECT_ROOT, folder)
        if not os.path.isdir(folder_path):
            continue
        for fname in sorted(os.listdir(folder_path)):
            if fname.endswith(".py") and not fname.startswith("__"):
                mod_name = f"{folder}.{fname[:-3]}"
                try:
                    importlib.import_module(mod_name)
                    passed_count += 1
                except Exception as err:
                    import traceback
                    failures.append((mod_name, traceback.format_exc()))

    return passed_count, failures


def test_web_server(test_port: int) -> Tuple[bool, str]:
    """Starts Uvicorn serving web.server:create_app on a test port and hits /api/health."""
    from web.server import create_app
    import uvicorn

    app = create_app()
    u_config = uvicorn.Config(app=app, host="127.0.0.1", port=test_port, log_level="warning", log_config=None)
    server = uvicorn.Server(config=u_config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # Wait for server to come up (max 5s)
    started = False
    start_t = time.time()
    while time.time() - start_t < 5.0:
        if server.started:
            started = True
            break
        time.sleep(0.05)

    if not started:
        server.should_exit = True
        return False, "Server failed to set server.started within 5 seconds."

    # Hit /api/health
    try:
        url_health = f"http://127.0.0.1:{test_port}/api/health"
        req = urllib.request.Request(url_health)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status != 200:
                server.should_exit = True
                return False, f"/api/health returned HTTP {resp.status}"
            data = json.loads(resp.read().decode())
            if data.get("status") != "ok":
                server.should_exit = True
                return False, f"/api/health status field is {data.get('status')} (expected 'ok')"

        # Hit /
        url_root = f"http://127.0.0.1:{test_port}/"
        with urllib.request.urlopen(url_root, timeout=3.0) as resp:
            if resp.status != 200:
                server.should_exit = True
                return False, f"Root / returned HTTP {resp.status}"

        server.should_exit = True
        server_thread.join(timeout=2.0)
        return True, "Endpoints /api/health and / responded with HTTP 200 OK."
    except Exception as err:
        server.should_exit = True
        return False, f"HTTP request failed: {err}"


def run_smoke_test():
    print("=" * 60)
    print("  PROJECT LIBRA RAPID SMOKE TEST")
    print("=" * 60)
    start_time = time.time()

    # Step 1: Import check
    print("\n[1/2] Verifying module imports (core, tools, ui, web)...")
    passed_count, failures = test_imports()

    if failures:
        print(f"FAILED: {len(failures)} module(s) could not be imported:")
        for mod, tb in failures:
            print(f"\n--- {mod} ---")
            print(tb)
        sys.exit(1)
    else:
        print(f"PASSED: {passed_count} modules imported successfully with zero errors.")

    # Step 2: Web server probe
    test_port = find_free_port()
    print(f"\n[2/2] Spawning web server on ephemeral test port {test_port}...")
    web_ok, web_msg = test_web_server(test_port)

    if not web_ok:
        print(f"FAILED: Web server probe failed: {web_msg}")
        sys.exit(1)
    else:
        print(f"PASSED: {web_msg}")

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print(f"  SMOKE TEST PASSED in {elapsed:.2f}s (well under 30s threshold)")
    print("=" * 60)
    sys.exit(0)


if __name__ == "__main__":
    run_smoke_test()
