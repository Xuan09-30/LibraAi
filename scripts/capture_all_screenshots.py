import os
import shutil
import socketserver
import http.server
import threading
from playwright.sync_api import sync_playwright

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB_DIR = os.path.join(PROJECT_ROOT, "web")
ROUND6_DIR = os.path.join(PROJECT_ROOT, "docs", "screenshots", "round6")
DOCS_SCREENSHOTS_DIR = os.path.join(PROJECT_ROOT, "docs", "screenshots")
os.makedirs(ROUND6_DIR, exist_ok=True)

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)
    def log_message(self, format, *args):
        pass

PORT = 9998

def capture_all():
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), QuietHandler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    print(f"[Capture] Server running on port {PORT}")

    viewports = [
        ("390px", 390, 844),
        ("820px", 820, 1180),
        ("1280px", 1280, 800)
    ]

    try:
        with sync_playwright() as p:
            browser = None
            for ch in ["msedge", "chrome", None]:
                try:
                    browser = p.chromium.launch(channel=ch, headless=True)
                    print(f"[Capture] Browser launched with channel: {ch}")
                    break
                except Exception:
                    pass
            if not browser:
                raise RuntimeError("Could not launch browser")

            # 1. Main Chat Viewports (390px, 820px, 1280px)
            for tag, w, h in viewports:
                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(f"http://127.0.0.1:{PORT}/static/index.html", wait_until="networkidle")
                page.evaluate("""() => {
                    const emptyHero = document.getElementById('empty-chat-hero');
                    if (emptyHero) emptyHero.remove();
                    const chat = document.getElementById('chat-container');
                    chat.innerHTML = `
                        <div class="msg msg-user">
                          <div class="msg-content">Can you summarize my preferences from memory and check active tasks?</div>
                          <div class="msg-meta user-msg-meta"><span class="token-badge user-token-badge">Prompt: 14 tok</span></div>
                        </div>
                        <div class="msg msg-libra">
                          <div class="msg-content">
                            <div class="thought-accordion">
                              <div class="thought-top-header">
                                <button class="thought-duration-btn" type="button" aria-expanded="false">
                                  <span class="thought-duration-label">Thought for 2.4s ▾</span>
                                </button>
                              </div>
                            </div>
                            <div class="markdown-body">
                              <p>I reviewed your memory vault notes. You prefer dark syntax themes, concise answers with step-by-step reasoning, and iced matcha latte with oat milk.</p>
                            </div>
                          </div>
                          <div class="msg-meta">
                            <span class="tool-badge">MemoryCore.search</span>
                            <span>38ms</span>
                            <span class="token-badge">Reply: 42 tok</span>
                          </div>
                        </div>
                    `;
                }""")
                page.wait_for_timeout(300)
                out_r6 = os.path.join(ROUND6_DIR, f"main_{tag}.png")
                page.screenshot(path=out_r6)
                shutil.copyfile(out_r6, os.path.join(DOCS_SCREENSHOTS_DIR, f"web_main_{tag}.png"))
                print(f"[Capture] Saved main {tag}")
                page.close()

            # 2. Auth Modal Viewports (390px, 820px, 1280px)
            for tag, w, h in viewports:
                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(f"http://127.0.0.1:{PORT}/static/index.html", wait_until="networkidle")
                page.evaluate("""() => {
                    const m = document.getElementById('auth-modal');
                    m.classList.add('open');
                    m.style.display = 'flex';
                }""")
                page.wait_for_timeout(300)
                out_r6 = os.path.join(ROUND6_DIR, f"auth_modal_{tag}.png")
                page.screenshot(path=out_r6)
                shutil.copyfile(out_r6, os.path.join(DOCS_SCREENSHOTS_DIR, f"web_auth_{tag}.png"))
                print(f"[Capture] Saved auth modal {tag}")
                page.close()

            # 3. Vault Modal Viewports (390px, 820px, 1280px)
            for tag, w, h in viewports:
                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(f"http://127.0.0.1:{PORT}/static/index.html", wait_until="networkidle")
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
                          <div class="vault-card-val">Antigravity IDE</div>
                        </div>
                        <div class="vault-card">
                          <div class="vault-card-header">
                            <div class="vault-card-header-left">
                              <button class="vault-pin-btn">☆</button>
                              <span class="vault-card-key">user.favorite_drink</span>
                            </div>
                            <div class="vault-card-header-right">
                              <span class="vault-category-badge">Preference</span>
                              <span class="vault-card-time">2026-11-04 11:52</span>
                              <button class="vault-delete-btn">✕</button>
                            </div>
                          </div>
                          <div class="vault-card-val">Matcha Latte (Oat Milk)</div>
                        </div>
                    `;
                }""")
                page.wait_for_timeout(300)
                out_r6 = os.path.join(ROUND6_DIR, f"vault_modal_{tag}.png")
                page.screenshot(path=out_r6)
                shutil.copyfile(out_r6, os.path.join(DOCS_SCREENSHOTS_DIR, f"web_vault_{tag}.png"))
                print(f"[Capture] Saved vault modal {tag}")
                page.close()

            # 4. Options Modal (1280px)
            page_opt = browser.new_page(viewport={"width": 1280, "height": 800})
            page_opt.goto(f"http://127.0.0.1:{PORT}/static/index.html", wait_until="networkidle")
            page_opt.evaluate("""() => {
                const m = document.getElementById('options-modal');
                m.classList.add('open');
                m.style.display = 'flex';
            }""")
            page_opt.wait_for_timeout(300)
            out_opt = os.path.join(ROUND6_DIR, "options_modal_1280px.png")
            page_opt.screenshot(path=out_opt)
            print(f"[Capture] Saved options modal 1280px")
            page_opt.close()

            # 5. Bug Report Modal (1280px)
            page_bug = browser.new_page(viewport={"width": 1280, "height": 800})
            page_bug.goto(f"http://127.0.0.1:{PORT}/static/index.html", wait_until="networkidle")
            page_bug.evaluate("""() => {
                const m = document.getElementById('bug-report-modal');
                m.classList.add('open');
                m.style.display = 'flex';
            }""")
            page_bug.wait_for_timeout(300)
            out_bug = os.path.join(ROUND6_DIR, "bug_modal_1280px.png")
            page_bug.screenshot(path=out_bug)
            print(f"[Capture] Saved bug modal 1280px")
            page_bug.close()

            # 6. Thinking Trace
            page_think = browser.new_page(viewport={"width": 1280, "height": 800})
            page_think.goto(f"http://127.0.0.1:{PORT}/static/index.html", wait_until="networkidle")
            page_think.evaluate("""() => {
                const emptyHero = document.getElementById('empty-chat-hero');
                if (emptyHero) emptyHero.remove();
                const chat = document.getElementById('chat-container');
                chat.innerHTML = `
                    <div class="msg msg-libra" style="max-width: 680px; margin: 40px auto;">
                      <div class="msg-content">
                        <div class="thought-accordion">
                          <div class="thought-top-header">
                            <button class="thought-duration-btn" type="button" aria-expanded="true">
                              <span class="thought-duration-label">Thought for 2.4s ▾</span>
                            </button>
                          </div>
                          <div class="thought-body" style="display: block;">
                            <div class="thought-actions-list">
                              <div class="thought-action-row open">
                                <button class="thought-action-btn" type="button" aria-expanded="true">
                                  <span class="thought-action-label">Scope grounding</span>
                                  <span class="thought-action-chevron">▾</span>
                                </button>
                                <div class="thought-action-pane" style="display: block;">
                                  <div class="thought-action-rationale">Parsed instruction parameters and verified memory access scopes.</div>
                                </div>
                              </div>
                              <div class="thought-action-row open">
                                <button class="thought-action-btn" type="button" aria-expanded="true">
                                  <span class="thought-action-label">Memory search</span>
                                  <span class="thought-action-chevron">▾</span>
                                </button>
                                <div class="thought-action-pane" style="display: block;">
                                  <div class="thought-action-rationale">Retrieved active preference notes for editor and drink.</div>
                                </div>
                              </div>
                              <div class="thought-action-row">
                                <button class="thought-action-btn" type="button" aria-expanded="false">
                                  <span class="thought-action-label">Completed task</span>
                                  <span class="thought-action-chevron">&gt;</span>
                                </button>
                              </div>
                            </div>
                          </div>
                        </div>
                        <div class="markdown-body">
                          <p>Synthesized response from persistent memory.</p>
                        </div>
                      </div>
                    </div>
                `;
            }""")
            page_think.wait_for_timeout(300)
            out_think = os.path.join(ROUND6_DIR, "thinking_trace.png")
            page_think.locator(".msg-libra").screenshot(path=out_think)
            shutil.copyfile(out_think, os.path.join(DOCS_SCREENSHOTS_DIR, "web_thinking_trace.png"))
            print(f"[Capture] Saved thinking trace")
            page_think.close()

            browser.close()
    finally:
        httpd.shutdown()
        print("[Capture] Server shut down.")

if __name__ == "__main__":
    capture_all()
