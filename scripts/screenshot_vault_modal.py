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

PORT = 9994

def capture_vault_modal():
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

                # Open Vault Modal & populate sample cards
                page.evaluate("""() => {
                    const vm = document.getElementById('vault-modal');
                    vm.classList.add('open');
                    vm.style.display = 'flex';

                    const grid = document.getElementById('vault-cards-grid');
                    grid.innerHTML = `
                        <div class="vault-card pinned">
                          <div class="vault-card-header">
                            <div class="vault-card-header-left">
                              <button class="vault-pin-btn pinned">★</button>
                              <span class="vault-card-key">user.favorite_editor</span>
                            </div>
                            <div class="vault-card-header-right">
                              <span class="vault-category-badge">General</span>
                              <span class="vault-card-time">2026-11-04 11:52</span>
                              <button class="vault-delete-btn">✕</button>
                            </div>
                          </div>
                          <div class="vault-card-body">Antigravity IDE &amp; Neovim with dark syntax theme</div>
                        </div>
                        <div class="vault-card">
                          <div class="vault-card-header">
                            <div class="vault-card-header-left">
                              <button class="vault-pin-btn">☆</button>
                              <span class="vault-card-key">user.favorite_drink</span>
                            </div>
                            <div class="vault-card-header-right">
                              <span class="vault-category-badge">Preference</span>
                              <span class="vault-card-time">2026-11-04 11:50</span>
                              <button class="vault-delete-btn">✕</button>
                            </div>
                          </div>
                          <div class="vault-card-body">Iced matcha latte with oat milk, 25% sugar</div>
                        </div>
                    `;
                }""")
                page.wait_for_timeout(300)

                # Capture full viewport with modal centered
                out_path = os.path.join(OUT_DIR, f"vault_modal_{tag}.png")
                page.screenshot(path=out_path)
                print(f"[Capture] Saved {out_path}")
                page.close()

            browser.close()
    finally:
        httpd.shutdown()
        print("[Capture] Server shut down.")

if __name__ == "__main__":
    capture_vault_modal()
