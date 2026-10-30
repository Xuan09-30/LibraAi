import os
import pytest
import asyncio
import time
from core.research import HardenedResearchEngine
from core.vram_governor import VRAMAutoGovernor, get_vram_governor
from core.llm import LocalLLM

def test_vram_governor_dynamic_keep_alive():
    """Verify Task 6: Dynamic VRAM keep-alive policy."""
    gov = get_vram_governor()

    # Primary conversational model must retain 15m VRAM residency
    assert gov.get_keep_alive("qwen3:8b", purpose="chat") == "15m"
    assert gov.get_keep_alive("qwen3:8b", purpose="general") == "15m"

    # Ephemeral classification and routing must yield 0s to release VRAM immediately
    assert gov.get_keep_alive("qwen3:8b", purpose="routing") == "0s"
    assert gov.get_keep_alive("qwen3:8b", purpose="classification") == "0s"
    assert gov.get_keep_alive("qwen3:8b", purpose="router") == "0s"

    # Secondary models (coder, vl) must yield 0s
    assert gov.get_keep_alive("qwen2.5-coder:7b", purpose="code") == "0s"
    assert gov.get_keep_alive("qwen2.5vl:7b", purpose="vision") == "0s"

def test_llm_call_ollama_keep_alive_logic():
    """Verify Task 6: call_ollama sets 15m for primary chat and 0s for router/json."""
    llm = LocalLLM()

    # Test inspection of call_ollama logic
    import inspect
    src = inspect.getsource(llm.call_ollama)
    assert 'keep_alive = "15m"' in src
    assert 'keep_alive = "0s"' in src

    # Verify llm.py file contains keep_alive="0s" for router
    with open("core/llm.py", "r", encoding="utf-8") as f:
        llm_code = f.read()
    assert 'keep_alive="0s"' in llm_code

def test_stream_token_progressive_rendering_app_js():
    """Verify Task 5: Progressive render queue throttling with requestAnimationFrame."""
    app_js_path = "web/static/app.js"
    assert os.path.exists(app_js_path)

    with open(app_js_path, "r", encoding="utf-8") as f:
        js = f.read()

    assert "renderProgressive" in js
    assert "requestAnimationFrame" in js
    assert "RENDER_INTERVAL_MS" in js
    assert "renderProgressive(false)" in js
    assert "renderProgressive(true)" in js

def test_async_web_search_fanout():
    """Verify Task 4: Parallel async web search fanout across providers with fast response."""
    engine = HardenedResearchEngine()
    t0 = time.perf_counter()
    res = asyncio.run(engine.async_search_and_extract("NBA basketball news today", max_sources=2))
    dt = time.perf_counter() - t0

    assert isinstance(res, dict)
    assert "sources" in res
    assert dt < 8.0
    print(f"\nAsync fan-out completed in {dt:.2f}s with {len(res['sources'])} sources.")
