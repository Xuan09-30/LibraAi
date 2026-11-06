import os
import time
import socketserver
import http.server
import threading
from playwright.sync_api import sync_playwright

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB_DIR = os.path.join(PROJECT_ROOT, "web")
OUT_DIR = os.path.join(PROJECT_ROOT, "docs", "screenshots", "round6")
os.makedirs(OUT_DIR, exist_ok=True)

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)
    def log_message(self, format, *args):
        pass

PORT = 9993

def capture_auth_modal():
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), QuietHandler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    print(f"[Capture] Server running on port {PORT}")

    viewports = [
        {"name": "390px", "width": 390, "height": 844},
        {"name": "1280px", "width": 1280, "height": 800}
    ]

    try:
        with sync_playwright() as p:
            browser = None
            for ch in ["msedge", "chrome", None]:
                try:
                    browser = p.chromium.launch(channel=ch, headless=True)
                    print(f"[Capture] Launched browser via channel {ch}")
                    break
                except Exception:
                    pass
            if not browser:
                raise RuntimeError("Could not launch browser")

            for vp in viewports:
                tag = vp["name"]
                w, h = vp["width"], vp["height"]
                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(f"http://127.0.0.1:{PORT}/static/index.html", wait_until="networkidle")

                # Open Auth Modal
                page.evaluate("""() => {
                    const m = document.getElementById('auth-modal');
                    m.classList.add('open');
                    m.style.display = 'flex';
                }""")
                page.wait_for_timeout(300)

                # Capture full viewport with modal centered
                out_path = os.path.join(OUT_DIR, f"auth_modal_{tag}.png")
                page.screenshot(path=out_path)
                print(f"[Capture] Saved {out_path}")
                page.close()

            browser.close()
    finally:
        httpd.shutdown()
        print("[Capture] Server shut down.")

if __name__ == "__main__":
    capture_auth_modal()
