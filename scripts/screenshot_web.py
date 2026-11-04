"""
Project Libra - Automated Web UI Screenshot Verification Script
Captures Web/PWA interface across standard responsive viewports:
- Mobile: 390px x 844px
- Tablet / iPad: 820px x 1180px
- Desktop: 1280px x 800px
Saves screenshots to docs/screenshots/
"""

import os
import sys
import time
import socketserver
import http.server
import threading
from playwright.sync_api import sync_playwright

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB_DIR = os.path.join(PROJECT_ROOT, "web")
OUT_DIR = os.path.join(PROJECT_ROOT, "docs", "screenshots")
os.makedirs(OUT_DIR, exist_ok=True)

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)
    def log_message(self, format, *args):
        pass

PORT = 9991

def run_screenshot_suite():
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), QuietHandler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    print(f"[Screenshot Suite] Serving web static assets at http://127.0.0.1:{PORT}")

    viewports = [
        {"name": "390px", "width": 390, "height": 844, "label": "Mobile (390px)"},
        {"name": "820px", "width": 820, "height": 1180, "label": "iPad / Tablet (820px)"},
        {"name": "1280px", "width": 1280, "height": 800, "label": "Desktop (1280px)"}
    ]

    captured_files = []

    try:
        with sync_playwright() as p:
            browser = None
            for ch in ["msedge", "chrome", None]:
                try:
                    browser = p.chromium.launch(channel=ch, headless=True)
                    print(f"[Screenshot Suite] Launched Chromium browser via channel: {ch}")
                    break
                except Exception:
                    pass
            if not browser:
                raise RuntimeError("Failed to launch any Chromium browser channel.")

            for vp in viewports:
                tag = vp["name"]
                w, h = vp["width"], vp["height"]
                print(f"\n--- Capturing viewports for {vp['label']} ---")

                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(f"http://127.0.0.1:{PORT}/static/index.html", wait_until="networkidle")

                # Populate mock messages and thinking trace
                page.evaluate("""() => {
                    const chat = document.getElementById('chat-container');
                    const emptyHero = document.getElementById('empty-chat-hero');
                    if (emptyHero) emptyHero.remove();

                    chat.innerHTML = `
                        <div class="msg msg-user">
                          <div class="msg-content">Can you check system status and summarize our latest research notes?</div>
                          <div class="msg-meta user-msg-meta"><span class="token-badge user-token-badge">⚡ Prompt: 14 tok</span></div>
                        </div>
                        <div class="msg msg-libra">
                          <div class="msg-content">
                            <div class="thought-accordion">
                              <div class="thought-top-header">
                                <button class="thought-duration-btn" type="button" aria-expanded="false">
                                  <span class="thought-duration-label">Thought for 2.4s ▾</span>
                                </button>
                              </div>
                              <div class="thought-body collapsed">
                                <div class="thought-actions-list">
                                  <div class="thought-action-row">
                                    <button class="thought-action-btn" type="button"><span class="thought-action-label">Intent &amp; Scope Analysis</span><span class="thought-action-chevron">&gt;</span></button>
                                  </div>
                                  <div class="thought-action-row">
                                    <button class="thought-action-btn" type="button"><span class="thought-action-label">Queried Core Memory Vault (BM25 FTS5)</span><span class="thought-action-chevron">&gt;</span></button>
                                  </div>
                                  <div class="thought-action-row">
                                    <button class="thought-action-btn" type="button"><span class="thought-action-label">Completed Task Synthesis</span><span class="thought-action-chevron">&gt;</span></button>
                                  </div>
                                </div>
                              </div>
                            </div>
                            <div class="markdown-body">
                              <p>Project Libra is operating under nominal parameters. Neural cognitive weights are grounded and your Core Memory Vault holds active preferences.</p>
                            </div>
                          </div>
                          <div class="msg-meta">
                            <span class="tool-badge">MemoryCore.search</span>
                            <span>42ms</span>
                            <span class="token-badge">⚡ Reply: 38 tok • 41.2 tok/s</span>
                            <button class="replay-audio-btn">
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                              <span>Listen</span>
                            </button>
                          </div>
                        </div>
                    `;
                }""")
                page.wait_for_timeout(300)

                # 1. Main Chat Screen
                main_path = os.path.join(OUT_DIR, f"web_main_{tag}.png")
                page.screenshot(path=main_path)
                captured_files.append(main_path)
                print(f"  [+] Saved {os.path.basename(main_path)}")

                # 2. Auth Modal Screen
                page.evaluate("""() => {
                    const m = document.getElementById('auth-modal');
                    m.classList.add('open');
                    m.style.display = 'flex';
                }""")
                page.wait_for_timeout(300)
                auth_path = os.path.join(OUT_DIR, f"web_auth_{tag}.png")
                page.locator("#auth-modal .modal-content").screenshot(path=auth_path)
                captured_files.append(auth_path)
                print(f"  [+] Saved {os.path.basename(auth_path)}")

                # 3. Vault Modal Screen
                page.evaluate("""() => {
                    document.getElementById('auth-modal').classList.remove('open');
                    document.getElementById('auth-modal').style.display = 'none';

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
                              <span class="vault-category-badge">GENERAL</span>
                              <span class="vault-card-time">2026-11-04 11:52</span>
                              <button class="vault-delete-btn">✕</button>
                            </div>
                          </div>
                          <div class="vault-card-body">Antigravity IDE &amp; Neovim with Cyberpunk 2077 syntax theme</div>
                        </div>
                        <div class="vault-card">
                          <div class="vault-card-header">
                            <div class="vault-card-header-left">
                              <button class="vault-pin-btn">☆</button>
                              <span class="vault-card-key">user.favorite_drink</span>
                            </div>
                            <div class="vault-card-header-right">
                              <span class="vault-category-badge">PREFERENCE</span>
                              <span class="vault-card-time">2026-11-04 11:50</span>
                              <button class="vault-delete-btn">✕</button>
                            </div>
                          </div>
                          <div class="vault-card-body">Iced matcha latte with oat milk, 25% sugar</div>
                        </div>
                    `;
                }""")
                page.wait_for_timeout(300)
                vault_path = os.path.join(OUT_DIR, f"web_vault_{tag}.png")
                page.locator("#vault-modal .modal-content").screenshot(path=vault_path)
                captured_files.append(vault_path)
                print(f"  [+] Saved {os.path.basename(vault_path)}")

                page.close()

            # Thinking Trace Inspection Snapshot (Expanded)
            page_think = browser.new_page(viewport={"width": 1280, "height": 800})
            page_think.goto(f"http://127.0.0.1:{PORT}/static/index.html", wait_until="networkidle")
            page_think.evaluate("""() => {
                const emptyHero = document.getElementById('empty-chat-hero');
                if (emptyHero) emptyHero.remove();
                const chat = document.getElementById('chat-container');
                chat.innerHTML = `
                    <div class="msg msg-libra" style="max-width: 680px; margin: 20px auto;">
                      <div class="msg-content">
                        <div class="thought-accordion">
                          <div class="thought-top-header">
                            <button class="thought-duration-btn" type="button" aria-expanded="true">
                              <span class="thought-duration-label">Thought for 3.1s ▾</span>
                            </button>
                          </div>
                          <div class="thought-body" style="display: block;">
                            <div class="thought-actions-list">
                              <div class="thought-action-row open">
                                <button class="thought-action-btn" type="button" aria-expanded="true">
                                  <span class="thought-action-label">Intent &amp; Scope Grounding</span>
                                  <span class="thought-action-chevron">▾</span>
                                </button>
                                <div class="thought-action-pane" style="display: block;">
                                  <div class="thought-action-rationale">Parsed instruction parameters and cross-checked against active security policies.</div>
                                </div>
                              </div>
                              <div class="thought-action-row open">
                                <button class="thought-action-btn" type="button" aria-expanded="true">
                                  <span class="thought-action-label">BM25 Memory Search</span>
                                  <span class="thought-action-chevron">▾</span>
                                </button>
                                <div class="thought-action-pane" style="display: block;">
                                  <div class="thought-action-rationale">Retrieved relevant persistent notes with rank score = 0.94.</div>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                `;
            }""")
            page_think.wait_for_timeout(300)
            think_path = os.path.join(OUT_DIR, "web_thinking_trace.png")
            page_think.locator(".msg-libra").screenshot(path=think_path)
            captured_files.append(think_path)
            print(f"  [+] Saved {os.path.basename(think_path)}")
            page_think.close()

            browser.close()

        print(f"\n[Screenshot Suite Complete] Successfully captured {len(captured_files)} screenshots into {OUT_DIR}")
        return captured_files

    finally:
        httpd.shutdown()
        print("[Screenshot Suite] Test web server stopped.")

if __name__ == "__main__":
    run_screenshot_suite()
