import os
import re
import sqlite3
import pytest
from core.memory import MemoryCore
from core.research import HardenedResearchEngine
from core.context_distiller import ContextDistiller
from core.llm import LocalLLM

def test_sqlite_wal_mode_and_concurrency():
    """Verify WAL mode, busy_timeout, and normal synchronous pragmas on MemoryCore and HardenedResearchEngine."""
    mem = MemoryCore(":memory:")
    conn = mem._get_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA busy_timeout;")
    assert cur.fetchone()[0] == 15000

    # Test file-based MemoryCore
    test_db = "assets/test_wal_verify.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    try:
        mem_file = MemoryCore(test_db)
        fconn = mem_file._get_connection()
        fcur = fconn.cursor()
        fcur.execute("PRAGMA journal_mode;")
        assert fcur.fetchone()[0].lower() == "wal"
        fcur.execute("PRAGMA busy_timeout;")
        assert fcur.fetchone()[0] == 15000
        fcur.execute("PRAGMA synchronous;")
        # 1 corresponds to NORMAL
        assert fcur.fetchone()[0] in (1, "1", "NORMAL")
    finally:
        if os.path.exists(test_db):
            try:
                os.remove(test_db)
            except Exception:
                pass

    # Test HardenedResearchEngine cache DB
    research = HardenedResearchEngine()
    rconn = research._get_conn()
    rcur = rconn.cursor()
    rcur.execute("PRAGMA journal_mode;")
    assert rcur.fetchone()[0].lower() == "wal"
    rcur.execute("PRAGMA busy_timeout;")
    assert rcur.fetchone()[0] == 15000
    rconn.close()

def test_ollama_options_num_ctx_8192():
    """Verify num_ctx=8192 and temperature=0.7 in server.py and llm.py."""
    with open("web/server.py", "r", encoding="utf-8") as f:
        srv_text = f.read()

    assert '"num_ctx": 8192' in srv_text
    assert '"temperature": 0.7' in srv_text
    assert '"keep_alive": "15m"' in srv_text

    with open("core/llm.py", "r", encoding="utf-8") as f:
        llm_text = f.read()

    assert '"num_ctx": 8192' in llm_text
    assert '"temperature": 0.7' in llm_text

def test_sliding_window_distiller():
    """Verify sliding-window distillation for threads with >8 turns."""
    distiller = ContextDistiller()
    turns = [
        {"role": "user", "content": f"Turn {i}: I am configuring the Docker container for Project Alpha"} if i % 2 == 0
        else {"role": "assistant", "content": f"Turn {i}: Docker container configuration updated with RTX 5080."}
        for i in range(12)
    ]
    assert len(turns) == 12

    # Verify build_summary operates cleanly on older turns
    older = turns[:-6]
    assert len(older) == 6
    summary = distiller._build_summary(older)
    assert "Context Summary" in summary
    assert "Project Alpha" in summary or "Docker" in summary

    # Verify compress_history
    compressed, summary_text = distiller.compress_history(turns, threshold=8)
    assert len(compressed) <= 8
    assert compressed[0]["role"] == "system"
    assert "Context Summary" in compressed[0]["content"]

def test_pwa_service_worker_v10_2_5():
    """Verify sw.js contains v10.2.5, all static assets, and stale-while-revalidate."""
    sw_path = "web/static/sw.js"
    assert os.path.exists(sw_path)

    with open(sw_path, "r", encoding="utf-8") as f:
        sw_code = f.read()

    assert "libra-pwa-v10.2.5" in sw_code
    for asset in [
        "/static/prism.min.js",
        "/static/prism.css",
        "/static/three.min.js",
        "/static/html2canvas.min.js",
        "/static/app.js",
        "/static/style.css"
    ]:
        assert asset in sw_code, f"Asset {asset} missing from sw.js"

    # Verify stale-while-revalidate logic exists
    assert "caches.match(event.request)" in sw_code
    assert "fetch(event.request)" in sw_code
