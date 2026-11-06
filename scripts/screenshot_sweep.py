import os
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

PORT = 9995

def capture_sweep():
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), QuietHandler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    print(f"[Sweep] Server running on port {PORT}")

    try:
        with sync_playwright() as p:
            browser = None
            for ch in ["msedge", "chrome", None]:
                try:
                    browser = p.chromium.launch(channel=ch, headless=True)
                    print(f"[Sweep] Launched browser via channel {ch}")
                    break
                except Exception:
                    pass
            if not browser:
                raise RuntimeError("Could not launch browser")

            # 1. Main Chat 390px & 1280px
            for tag, (w, h) in [("390px", (390, 844)), ("1280px", (1280, 800))]:
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
                main_out = os.path.join(OUT_DIR, f"main_{tag}.png")
                page.screenshot(path=main_out)
                print(f"[Sweep] Saved {main_out}")
                page.close()

            # 2. Options Modal 1280px
            page_opt = browser.new_page(viewport={"width": 1280, "height": 800})
            page_opt.goto(f"http://127.0.0.1:{PORT}/static/index.html", wait_until="networkidle")
            page_opt.evaluate("""() => {
                const m = document.getElementById('options-modal');
                m.classList.add('open');
                m.style.display = 'flex';
            }""")
            page_opt.wait_for_timeout(300)
            opt_out = os.path.join(OUT_DIR, "options_modal_1280px.png")
            page_opt.screenshot(path=opt_out)
            print(f"[Sweep] Saved {opt_out}")
            page_opt.close()

            # 3. Bug Modal 1280px
            page_bug = browser.new_page(viewport={"width": 1280, "height": 800})
            page_bug.goto(f"http://127.0.0.1:{PORT}/static/index.html", wait_until="networkidle")
            page_bug.evaluate("""() => {
                const m = document.getElementById('bug-report-modal');
                m.classList.add('open');
                m.style.display = 'flex';
            }""")
            page_bug.wait_for_timeout(300)
            bug_out = os.path.join(OUT_DIR, "bug_modal_1280px.png")
            page_bug.screenshot(path=bug_out)
            print(f"[Sweep] Saved {bug_out}")
            page_bug.close()

            # 4. Thinking Trace (Expanded Detail)
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
            think_out = os.path.join(OUT_DIR, "thinking_trace.png")
            page_think.locator(".msg-libra").screenshot(path=think_out)
            print(f"[Sweep] Saved {think_out}")
            page_think.close()

            browser.close()
    finally:
        httpd.shutdown()
        print("[Sweep] Server shut down.")

if __name__ == "__main__":
    capture_sweep()
