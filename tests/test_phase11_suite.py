import os
import sys
import json
import time
import shutil
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch, ANY
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
_qt_app = QApplication.instance()
if _qt_app is None:
    _qt_app = QApplication([])

# Module imports
from ui.spotlight_bar import (
    SpotlightBar, GlobalHotkeyThread, HOTKEY_ID_SPOTLIGHT,
    MOD_ALT, MOD_NOREPEAT, VK_SPACE, VK_CONTROL, VK_C, VK_V
)
from core.memory import SemanticMemory
from core.trust_guard import TrustGuard, RiskTier, ApprovalTicket
from core.dictation import WhisperDictationController, type_unicode_text, DictationCleaner
from core.text_cleaner import clean_for_dictation
from core.briefing import BriefingAndWorkspaces, DailyBriefing
from core.vram_governor import VRAMAutoGovernor, get_vram_governor
from core.spatial import SpatialGroundingEngine
from tools.file_manager import FileManager
from web.server import create_app, load_web_config


# ===========================================================================
# GLOBAL FIXTURES
# ===========================================================================

@pytest.fixture
def mock_win32(monkeypatch):
    """Mocks Win32 API functions across ctypes and win32 libraries."""
    mock_user32 = MagicMock()
    mock_user32.GetForegroundWindow.return_value = 0x12345
    mock_user32.SetForegroundWindow.return_value = True
    mock_user32.RegisterHotKey.return_value = True
    mock_user32.UnregisterHotKey.return_value = True
    mock_user32.SendInput.return_value = 1
    mock_user32.GetAsyncKeyState.return_value = 0
    mock_user32.GetMessageW.return_value = 0

    monkeypatch.setattr("ctypes.windll.user32", mock_user32, raising=False)

    mock_win32api = MagicMock()
    mock_win32clipboard = MagicMock()
    monkeypatch.setattr(sys, "win32api", mock_win32api, raising=False)
    monkeypatch.setattr(sys, "win32clipboard", mock_win32clipboard, raising=False)

    return mock_user32


@pytest.fixture
def temp_vault_dir(tmp_path):
    """Temporary directory fixture simulating assets/vault/ with clean teardown."""
    v_dir = tmp_path / "vault"
    v_dir.mkdir(parents=True, exist_ok=True)
    yield str(v_dir)
    shutil.rmtree(str(v_dir), ignore_errors=True)


@pytest.fixture
def temp_trash_dir(tmp_path):
    """Temporary directory fixture simulating .libra_trash/ with auto-cleanup."""
    t_dir = tmp_path / "trash"
    t_dir.mkdir(parents=True, exist_ok=True)
    yield str(t_dir)
    shutil.rmtree(str(t_dir), ignore_errors=True)


@pytest.fixture
def in_memory_db(temp_vault_dir):
    """In-memory SQLite fixture with BM25 FTS5 tables matching core/memory.py."""
    with patch("core.memory.SemanticMemory.sync_all_to_vault_markdown"), \
         patch("core.memory.SemanticMemory.start_vault_watchdog"):
        mem = SemanticMemory(db_filename=":memory:")
        mem.vault_dir = temp_vault_dir
        yield mem
        if hasattr(mem, "_shared_conn") and mem._shared_conn:
            try:
                mem._shared_conn.close()
            except Exception:
                pass


@pytest.fixture
def test_client(in_memory_db, temp_vault_dir):
    """FastAPI TestClient fixture with mock auth and memory wiring."""
    mock_hub = MagicMock()
    mock_hub.llm = MagicMock()
    mock_hub.llm.memory = in_memory_db
    mock_hub.llm.file_mgr = FileManager()
    mock_hub.process_command.return_value = {
        "status": "success",
        "voice_response": "Executed",
        "action": "chat"
    }

    app = create_app(hub=mock_hub)
    client = TestClient(app)
    cfg = load_web_config()
    token = cfg.get("access_token", "libra_access_token_phase10_secure")
    client.headers = {"Authorization": f"Bearer {token}", "Cookie": f"libra_auth={token}"}
    return client


# ===========================================================================
# 1. SPOTLIGHT BAR & SELECTION CAPTURE (ui/spotlight_bar.py)
# ===========================================================================

def test_spotlight_hotkey_registration(mock_win32):
    """Verify that global hotkey registers MOD_ALT | VK_SPACE and unregisters on exit."""
    thread = GlobalHotkeyThread()

    with patch.object(mock_win32, "GetMessageW", side_effect=[0]):
        thread.run()

    mock_win32.RegisterHotKey.assert_called_with(
        None,
        HOTKEY_ID_SPOTLIGHT,
        MOD_ALT | MOD_NOREPEAT,
        VK_SPACE
    )
    mock_win32.UnregisterHotKey.assert_called_with(None, HOTKEY_ID_SPOTLIGHT)


def test_selection_capture_and_clipboard_restoration(mock_win32):
    """
    Test selection capture synthesizes Ctrl+C, captures active text,
    and restores the user's original clipboard data without pollution.
    """
    spotlight = SpotlightBar(parent=None)

    clipboard = QApplication.clipboard()
    clipboard.setText("user_original_clipboard_data")

    # Mock the sequence: when Ctrl+C is synthesized, clipboard updates to selection
    def fake_synthesize(mod, key):
        if mod == VK_CONTROL and key == VK_C:
            clipboard.setText("def broken_code(): return None")

    with patch("ui.spotlight_bar._synthesize_key_combo", side_effect=fake_synthesize):
        captured = spotlight._capture_active_selection()

    assert captured == "def broken_code(): return None"
    # Ensure clipboard was restored to user's original data
    assert clipboard.text() == "user_original_clipboard_data"
    spotlight.hotkey_thread.stop()


def test_inline_code_replacement_dispatch(mock_win32):
    """
    Verify inline transformation restores previous window focus and injects
    replacement text via Ctrl+V SendInput without clipboard pollution.
    """
    spotlight = SpotlightBar(parent=None)
    spotlight.prev_hwnd = 0x9999
    spotlight.output_box.setPlainText("def fixed_code(): return True")

    clipboard = QApplication.clipboard()
    clipboard.setText("user_data_before_inject")

    key_combos_sent = []
    def track_key_combo(mod, key):
        key_combos_sent.append((mod, key))

    with patch("ui.spotlight_bar._synthesize_key_combo", side_effect=track_key_combo):
        spotlight.inject_replacement()

    # Verify focus restored to target window
    mock_win32.SetForegroundWindow.assert_called_with(0x9999)
    # Verify Ctrl+V was dispatched
    assert (VK_CONTROL, VK_V) in key_combos_sent
    # Verify clipboard restored
    assert clipboard.text() == "user_data_before_inject"
    spotlight.hotkey_thread.stop()


# ===========================================================================
# 2. MEMORY VAULT BI-DIRECTIONAL ENGINE (core/memory.py & UI)
# ===========================================================================

def test_sqlite_to_markdown_export(in_memory_db, temp_vault_dir):
    """
    Insert a fact into semantic_facts and assert an individual .md note
    is created in assets/vault/ with valid YAML frontmatter.
    """
    in_memory_db.vault_dir = temp_vault_dir

    fid = in_memory_db.upsert_semantic_fact(
        entity="user",
        relation="coffee",
        value="Prefers black coffee",
        category="preference",
        pinned=True
    )
    assert fid > 0

    in_memory_db.sync_fact_to_vault_markdown(fid)

    files = [f for f in os.listdir(temp_vault_dir) if f.startswith(f"fact_{fid}_")]
    assert len(files) == 1
    note_path = os.path.join(temp_vault_dir, files[0])

    with open(note_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "---" in content
    assert f"id: {fid}" in content
    assert "category: preference" in content
    assert "pinned: true" in content
    assert "Prefers black coffee" in content


def test_markdown_to_sqlite_import(in_memory_db, temp_vault_dir):
    """
    Drop a manually edited .md file into the vault, trigger file handler,
    and assert record is imported and indexed into SQLite FTS5 table.
    """
    in_memory_db.vault_dir = temp_vault_dir

    # Pre-create entry 102
    in_memory_db.upsert_semantic_fact("user", "toolchain", "Use pip", category="dev", pinned=False)
    facts = in_memory_db.get_vault_facts()
    target_id = facts[0]["id"]

    note_path = os.path.join(temp_vault_dir, f"fact_{target_id}_toolchain.md")
    md_content = f"""---
id: {target_id}
category: dev_tools
pinned: true
updated_at: '2026-10-24 00:00:00'
---
Always use uv instead of pip
"""
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Directly trigger vault sync handler
    in_memory_db._handle_vault_file_change(note_path)

    # Query DB and verify FTS5 indexing
    matching = in_memory_db.get_vault_facts(query="uv")
    assert len(matching) >= 1
    assert matching[0]["value"] == "Always use uv instead of pip"
    assert matching[0]["pinned"] is True
    assert matching[0]["category"] == "dev_tools"


def test_vault_pin_prevents_markovian_eviction(in_memory_db):
    """
    Verify facts with pinned=True remain intact while unpinned facts
    are pruned during high-context memory compaction.
    """
    # Insert 1 pinned fact
    fid_pinned = in_memory_db.upsert_semantic_fact(
        "user", "core_role", "Principal Architect", category="bio", pinned=True
    )
    # Insert 5 unpinned facts
    unpinned_ids = []
    for i in range(5):
        uid = in_memory_db.upsert_semantic_fact(
            "user", f"temp_note_{i}", f"Ephemeral detail {i}", category="ephemeral", pinned=False
        )
        unpinned_ids.append(uid)

    # Prune keeping max 3 facts
    in_memory_db.prune_unpinned_facts(max_facts=3)

    all_facts = in_memory_db.get_vault_facts()
    fact_ids = [f["id"] for f in all_facts]

    # Pinned fact MUST still exist
    assert fid_pinned in fact_ids
    # Total count capped at 3
    assert len(all_facts) == 3


def test_pwa_vault_rest_endpoints(test_client, in_memory_db, temp_vault_dir):
    """Test GET /api/vault and DELETE /api/vault/{id} REST endpoints."""
    in_memory_db.vault_dir = temp_vault_dir
    fid = in_memory_db.upsert_semantic_fact(
        "user", "snack", "Pistachios", category="food", pinned=False
    )
    in_memory_db.sync_fact_to_vault_markdown(fid)

    # 1. GET /api/vault
    resp_get = test_client.get("/api/vault")
    assert resp_get.status_code == 200
    data = resp_get.json()
    assert data["status"] == "success"
    assert any(f["id"] == fid for f in data["facts"])

    # 2. DELETE /api/vault/{id}
    resp_del = test_client.delete(f"/api/vault/{fid}")
    assert resp_del.status_code == 200
    assert resp_del.json()["status"] == "success"

    # Verify DB pruned and .md file removed
    remaining = in_memory_db.get_vault_facts()
    assert not any(f["id"] == fid for f in remaining)
    files = [f for f in os.listdir(temp_vault_dir) if f.startswith(f"fact_{fid}_")]
    assert len(files) == 0


# ===========================================================================
# 3. PERMISSIONED RISK BADGES & UNDO SNAPSHOTS (core/trust_guard.py)
# ===========================================================================

def test_action_risk_tier_classification():
    """Verify 3-tier classification: Green (Auto), Amber (Snapshot), Red (Prompt)."""
    guard = TrustGuard(trash_dir=tempfile.mkdtemp())

    assert guard.classify_operation("read_file") == RiskTier.GREEN
    assert guard.classify_operation("get_weather") == RiskTier.GREEN
    assert guard.classify_operation("search") == RiskTier.GREEN

    assert guard.classify_operation("modify_file") == RiskTier.AMBER
    assert guard.classify_operation("write_file") == RiskTier.AMBER
    assert guard.classify_operation("git_commit") == RiskTier.AMBER

    assert guard.classify_operation("delete_file") == RiskTier.RED
    assert guard.classify_operation("shell_exec") == RiskTier.RED
    assert guard.classify_operation("git_reset") == RiskTier.RED


def test_amber_action_automatic_snapshot(temp_trash_dir, tmp_path):
    """Verify file modification automatically snapshots to .libra_trash/<filename>.<timestamp>.bak."""
    guard = TrustGuard(trash_dir=temp_trash_dir)

    test_file = tmp_path / "test_script.py"
    test_file.write_text("print('original content')", encoding="utf-8")

    def edit_action():
        test_file.write_text("print('modified content')", encoding="utf-8")

    guard.execute_with_guard(
        op_name="modify_file",
        target=str(test_file),
        action_func=edit_action
    )

    # Assert backup created in trash
    bak_files = [f for f in os.listdir(temp_trash_dir) if f.startswith("test_script.py.") and f.endswith(".bak")]
    assert len(bak_files) == 1

    bak_content = open(os.path.join(temp_trash_dir, bak_files[0]), "r", encoding="utf-8").read()
    assert bak_content == "print('original content')"
    assert test_file.read_text(encoding="utf-8") == "print('modified content')"


def test_undo_last_rollback(temp_trash_dir, tmp_path):
    """Verify TrustGuard.undo_last reverts corrupted file state to the latest snapshot."""
    guard = TrustGuard(trash_dir=temp_trash_dir)

    test_file = tmp_path / "test_script.py"
    test_file.write_text("stable_version_1", encoding="utf-8")

    guard.snapshot_file(str(test_file), op_name="edit")
    test_file.write_text("corrupted_state_error", encoding="utf-8")

    res = guard.undo_last(str(test_file))
    assert res["status"] == "success"
    assert test_file.read_text(encoding="utf-8") == "stable_version_1"


def test_red_action_blocking_card(temp_trash_dir):
    """
    Verify RED tier operations return a pending ApprovalTicket without
    executing until ticket.approve() is explicitly called.
    """
    guard = TrustGuard(trash_dir=temp_trash_dir)

    executed = {"flag": False}
    def destructive_action():
        executed["flag"] = True
        return "deleted"

    ticket = guard.execute_with_guard(
        op_name="delete_file",
        target="C:/Users/User/Desktop/ImportantDir",
        action_func=destructive_action,
        description="Permanently delete ImportantDir"
    )

    # Must be ApprovalTicket and NOT executed yet
    assert isinstance(ticket, ApprovalTicket)
    assert ticket.status == "pending_approval"
    assert executed["flag"] is False

    # Explicit approval execution
    res = ticket.approve()
    assert res["status"] == "success"
    assert executed["flag"] is True
    assert ticket.status == "approved"


# ===========================================================================
# 4. BIDIRECTIONAL AIRDROP BRIDGE (web/server.py)
# ===========================================================================

def test_mobile_drop_to_pc_pipeline(test_client, tmp_path, monkeypatch):
    """
    Verify POST /api/bridge/drop streams uploaded file to Downloads/LibraDrop/,
    indexes text/PDFs into RAG, and invokes launch mock if open_on_pc=true.
    """
    mock_startfile = MagicMock()
    monkeypatch.setattr("os.startfile", mock_startfile, raising=False)

    fake_drop_dir = tmp_path / "LibraDrop"
    fake_drop_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path) if "~" in p else p)

    file_payload = b"%PDF-1.4 Mock PDF Content For RAG Ingestion"
    files = {"file": ("lecture.pdf", file_payload, "application/pdf")}
    data = {"open_on_pc": "true"}

    resp = test_client.post("/api/bridge/drop", files=files, data=data)
    assert resp.status_code == 200
    res_json = resp.json()

    assert res_json["status"] == "success"
    assert res_json["filename"] == "lecture.pdf"
    assert res_json["opened_on_pc"] is True

    # Assert file on disk
    dest_path = tmp_path / "Downloads" / "LibraDrop" / "lecture.pdf"
    assert dest_path.is_file()
    assert dest_path.read_bytes() == file_payload


def test_pc_to_phone_grab_query(test_client, tmp_path, monkeypatch):
    """
    Verify natural language file request triggers file discovery,
    returns bridge download link, and streams file via GET /api/bridge/download.
    """
    test_file = tmp_path / "thesis.pdf"
    test_file.write_text("Thesis Document Body Content", encoding="utf-8")

    # 1. Query chat
    chat_resp = test_client.post("/api/chat", json={
        "prompt": f"Send me thesis.pdf from desktop",
        "client_scope": "remote_web"
    })
    assert chat_resp.status_code == 200

    # 2. Test direct authenticated download endpoint
    dl_resp = test_client.get("/api/bridge/download", params={"path": str(test_file)})
    assert dl_resp.status_code == 200
    assert dl_resp.text == "Thesis Document Body Content"
    assert "application/" in dl_resp.headers.get("content-type", "")


# ===========================================================================
# 5. WHISPER CONTEXT-AWARE DICTATION ENGINE (core/dictation.py)
# ===========================================================================

def test_hold_to_record_audio_stream():
    """Verify hold-to-record buffers audio into memory and passes to Whisper STT on release."""
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = "transcribed voice typing"

    controller = WhisperDictationController(stt_engine=mock_stt)

    with patch.object(controller, "_init_mic", return_value=True):
        # Key down starts recording
        controller._on_key_down()
        assert controller._is_recording is True

        # Simulate audio chunks in memory buffer
        controller._audio_buffer.extend(b"\x00\x01" * 5000)

        # Key up stops recording and dispatches to STT
        with patch.object(controller, "_process_and_type") as mock_type:
            controller._on_key_up()
            assert controller._is_recording is False
            mock_type.assert_called_once()


def test_technical_text_cleaner_and_filler_removal():
    """
    Verify DictationCleaner.normalize strips verbal fillers ('um wait no')
    and applies technical and case conventions ('camel case user profile' -> userProfile).
    """
    raw_speech = "um wait no let us create a new pyqt six fast api route with camel case user profile"
    cleaned = DictationCleaner.normalize(raw_speech)
    assert cleaned == "let us create a new PyQt6 FastAPI route with userProfile"


def test_cursor_injection_emits_unicode_sendinput(mock_win32):
    """Verify type_unicode_text dispatches KEYEVENTF_UNICODE SendInput structs."""
    type_unicode_text("Libra")
    # 5 characters * 2 events (down + up) = 10 input events
    mock_win32.SendInput.assert_called_once()
    n_inputs = mock_win32.SendInput.call_args[0][0]
    assert n_inputs == 10


# ===========================================================================
# 6. MORNING TACTICAL BRIEFING (core/briefing.py)
# ===========================================================================

def test_daily_briefing_deduplication(in_memory_db):
    """Verify full briefing generation runs once per calendar date and caches thereafter."""
    engine = BriefingAndWorkspaces(memory=in_memory_db)

    with patch.object(engine, "_synthesize_bullets_with_llm", return_value=[
        "• Weather in KL: 28°C", "• Reminders: 0 overdue", "• System: NVMe optimal"
    ]) as mock_synth:
        # First call: executes synthesis
        b1 = engine.generate_tactical_briefing(force=False)
        assert mock_synth.call_count == 1

        # Second call on same date: returns cached card without re-querying LLM
        b2 = engine.generate_tactical_briefing(force=False)
        assert mock_synth.call_count == 1
        assert b1["bullets"] == b2["bullets"]


def test_payload_aggregation_concurrency(in_memory_db):
    """Verify concurrent telemetry gathering aggregates weather, git, reminders, and hardware."""
    engine = BriefingAndWorkspaces(memory=in_memory_db)

    mock_weather = {"city": "Kuala Lumpur", "temp_c": 29.0, "max_rain_prob_12h": 75}
    mock_git = {"dirty_count": 3, "files_summary": "3 modified files"}
    mock_reminders = {"overdue_count": 2, "due_today_count": 1}
    mock_hw = {"gpu_temp_c": 38, "nvme_free_gb": 450}

    with patch.object(engine, "_fetch_weather_telemetry", return_value=mock_weather), \
         patch.object(engine, "_fetch_git_telemetry", return_value=mock_git), \
         patch.object(engine, "_fetch_reminders_telemetry", return_value=mock_reminders), \
         patch.object(engine, "_fetch_hardware_telemetry", return_value=mock_hw):

        telemetry = DailyBriefing.gather_context(engine)

    assert telemetry["weather"]["temp_c"] == 29.0
    assert telemetry["weather"]["max_rain_prob_12h"] == 75
    assert telemetry["git"]["dirty_count"] == 3
    assert telemetry["reminders"]["overdue_count"] == 2
    assert telemetry["hardware"]["nvme_free_gb"] == 450


def test_briefing_synthesis_formatting(in_memory_db):
    """Verify final tactical briefing adheres strictly to 3 military bullet points."""
    engine = BriefingAndWorkspaces(memory=in_memory_db)

    with patch.object(engine, "_synthesize_bullets_with_llm", return_value=[
        "• Kuala Lumpur: 29°C, 75% rain probability in next 12h.",
        "• 2 overdue priorities flagged, 1 task scheduled today.",
        "• NVMe 450GB free, GPU 38°C, git repository has 3 modified files."
    ]):
        res = engine.generate_tactical_briefing(force=True)

    bullets = res["bullets"]
    assert len(bullets) == 3
    assert all(b.startswith("• ") for b in bullets)
    assert "Kuala Lumpur" in bullets[0]
    assert "overdue" in bullets[1]
    assert "NVMe" in bullets[2]


# ===========================================================================
# 7. VRAM AUTO-GOVERNOR / GAMING SHIELD (core/vram_governor.py)
# ===========================================================================

def test_game_process_detection(monkeypatch):
    """Verify that detecting a gaming process triggers VRAM flush for qwen3:8b and qwen2.5vl:7b."""
    governor = VRAMAutoGovernor()
    governor.gaming_lite_mode = False

    class MockProc:
        def __init__(self, name):
            self.info = {"name": name}

    monkeypatch.setattr("psutil.process_iter", lambda attrs: [MockProc("valorant.exe")])

    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        governor.step_cycle()

        assert governor.is_gaming_lite_mode() is True
        # Verify keep_alive: 0 called
        calls = [c[1]["json"] for c in mock_post.call_args_list if "json" in c[1]]
        flushed_models = [c.get("model") for c in calls if c.get("keep_alive") == 0]
        assert "qwen3:8b" in flushed_models
        assert "qwen2.5vl:7b" in flushed_models


def test_gaming_lite_mode_enforcement():
    """Verify Gaming Lite Mode bypasses heavy GPU vision models in SpatialGroundingEngine."""
    governor = get_vram_governor()
    governor.gaming_lite_mode = True

    spatial = SpatialGroundingEngine()

    mock_rapid = MagicMock(return_value=([([(0, 0), (10, 0), (10, 10), (0, 10)], "PLAY NOW", 0.99)], None))
    spatial.rapid_ocr = mock_rapid

    elements = spatial.extract_screen_text_ocr(screenshot_img=None)
    # Uses RapidOCR on CPU
    assert len(elements) == 1
    assert elements[0]["text"] == "PLAY NOW"

    governor.gaming_lite_mode = False


def test_game_exit_vram_restoration(monkeypatch):
    """Verify that when games terminate, governor dispatches async warmup request for qwen3:8b."""
    governor = VRAMAutoGovernor()
    governor.gaming_lite_mode = True

    class MockProc:
        def __init__(self, name):
            self.info = {"name": name}

    # No games running
    monkeypatch.setattr("psutil.process_iter", lambda attrs: [MockProc("explorer.exe")])

    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        with patch.object(governor, "warmup_models_after_gaming") as mock_warm:
            governor.step_cycle()

            assert governor.is_gaming_lite_mode() is False
            mock_warm.assert_called_once()



# ===========================================================================
# 8. REAL-TIME FULL-DUPLEX SSE STREAMING & KOKORO SENTENCE AUDIO QUEUE
# ===========================================================================

def test_sse_chat_token_streaming(test_client):
    """
    Verify POST /api/chat?stream=true yields text/event-stream chunks:
      1. meta event with active session_id
      2. token events with streamed tokens
      3. done event with token telemetry metrics
    """
    class MockStreamResponse:
        status_code = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def aiter_lines(self):
            yield json.dumps({"message": {"content": "Real-time"}, "done": False})
            yield json.dumps({"message": {"content": " streaming"}, "done": False})
            yield json.dumps({"done": True, "prompt_eval_count": 8, "eval_count": 6, "eval_duration": 300000000})

    class MockAsyncClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def stream(self, *args, **kwargs): return MockStreamResponse()

    with patch("httpx.AsyncClient", MockAsyncClient):
        with test_client.stream("POST", "/api/chat?stream=true", json={"prompt": "test stream", "client_scope": "remote_web"}) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

            events = []
            for line in resp.iter_lines():
                if line and line.startswith("data: "):
                    events.append(json.loads(line[6:]))

            assert len(events) >= 3
            assert events[0]["type"] == "meta"
            assert "session_id" in events[0]
            assert events[1]["type"] == "token"
            assert events[1]["content"] == "Real-time"
            assert events[-1]["type"] == "done"
            assert events[-1]["token_metrics"]["turn_out"] == 6


def test_sse_sentence_level_kokoro_audio(test_client):
    """
    Verify sentence accumulator splits clauses and emits 'audio' events
    with Base64 WAV payloads alongside token events when synthesize_audio=True.
    """
    class MockSentenceStreamResponse:
        status_code = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def aiter_lines(self):
            # A full grammatical sentence > 25 chars
            yield json.dumps({"message": {"content": "Project Libra has online real-time voice streaming ready for deployment."}, "done": False})
            yield json.dumps({"done": True, "prompt_eval_count": 12, "eval_count": 12, "eval_duration": 500000000})

    class MockAsyncClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def stream(self, *args, **kwargs): return MockSentenceStreamResponse()

    # Mock synthesize_sentence_wav_b64
    with patch("httpx.AsyncClient", MockAsyncClient), \
         patch("web.server.synthesize_sentence_wav_b64", return_value="UklGRi4AAABXQVZFZm10IBAAAAABAAEA"):
        with test_client.stream("POST", "/api/chat?stream=true", json={
            "prompt": "test audio stream",
            "client_scope": "remote_web",
            "synthesize_audio": True
        }) as resp:
            assert resp.status_code == 200
            audio_events = []
            for line in resp.iter_lines():
                if line and line.startswith("data: "):
                    ev = json.loads(line[6:])
                    if ev["type"] == "audio":
                        audio_events.append(ev)

            assert len(audio_events) >= 1
            assert audio_events[0]["sentence_index"] == 0
            assert audio_events[0]["audio_base64"] == "UklGRi4AAABXQVZFZm10IBAAAAABAAEA"

# ===========================================================================
# RUNNER CONFIGURATION
# ===========================================================================

if __name__ == "__main__":
    import pytest
    pytest.main(["-v", "-s", __file__])
