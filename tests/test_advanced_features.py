import os
import sys
import tempfile
from typing import Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.clipboard_agent import ClipboardAgent
from tools.document_rag import DocumentRAGEngine
from core.workspaces import WorkspaceManager
from tools.spotify_agent import SpotifyAgent
from core.briefing import BriefingEngine
from core.llm import LocalLLM
from core.orchestrator import SupervisorHub


def test_clipboard_copilot():
    print("[RUNNING] Test 1: Clipboard Copilot & Error Debugger...")
    agent = ClipboardAgent()

    # 1. Test Python traceback diagnosis
    py_err = """Traceback (most recent call last):
  File "train.py", line 42, in <module>
    loss = criterion(outputs, targets)
IndexError: Target 10 is out of bounds."""
    res1 = agent.explain_error(text=py_err, dry_run=True)
    assert res1["status"] == "diagnosed", f"Expected diagnosed status, got {res1['status']}"
    assert res1["error_type"] == "Python Traceback", f"Expected Python Traceback, got {res1['error_type']}"
    assert "IndexError" in res1["error_line"], f"Expected IndexError in {res1['error_line']}"

    # 2. Test C++ compiler error diagnosis
    cpp_err = "main.cpp:18:5: error: use of undeclared identifier 'nullptr_t'"
    res2 = agent.explain_error(text=cpp_err, dry_run=True)
    assert res2["error_type"] == "C/C++ Compiler Error", f"Expected C/C++ Compiler Error, got {res2['error_type']}"

    # 3. Test note saving in dry-run
    res3 = agent.save_clipboard_note(title="Vector DB Optimizations", text="Use cosine distance with float32 vectors.", dry_run=True)
    assert res3["status"] == "saved", f"Expected saved status, got {res3['status']}"
    assert res3["title"] == "Vector DB Optimizations"

    print("  [PASS] Test 1: Clipboard error classification and note persistence verified.")


def test_document_rag():
    print("[RUNNING] Test 2: Local Document RAG ('Chat with Your Files')...")
    # Use in-memory SQLite for isolated test
    rag = DocumentRAGEngine(db_filename=":memory:")

    # Create temporary proposal document
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
        f.write(
            "Project Libra Technical Specification.\n"
            "The system uses Silero VAD with an 800ms speech boundary cutoff.\n"
            "Speech recognition is powered by Faster-Whisper large-v3-turbo running on CUDA.\n"
            "TTS audio is synthesized via the Kokoro 82M neural pipeline at 24kHz.\n"
        )
        temp_file = f.name

    try:
        # Index document
        idx_res = rag.index_file(temp_file, dry_run=True)
        assert idx_res["status"] in ["indexed", "cached"], f"Index status unexpected: {idx_res}"
        assert idx_res["chunk_count"] > 0, "No chunks generated"

        # Query document
        query_res = rag.query_document(temp_file, "What is the TTS pipeline?", dry_run=True)
        assert query_res["status"] == "success", f"Query status failed: {query_res}"
        assert len(query_res["chunks"]) > 0, "No chunks retrieved"
        assert "Kokoro" in query_res["chunks"][0] or "TTS" in query_res["chunks"][0], f"Chunks missing keywords: {query_res['chunks']}"

        # Not-found handling
        nf_res = rag.query_document("nonexistent_proposal_file_999.pdf", "What is the timeline?", dry_run=True)
        assert nf_res["status"] == "not_found", f"Expected not_found, got {nf_res['status']}"
    finally:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

    print("  [PASS] Test 2: Document RAG extraction, chunking, and grounded retrieval verified.")


def test_workspace_profiles():
    print("[RUNNING] Test 3: One-Command Workspace Profiles...")
    wm = WorkspaceManager()

    # 1. Coding Profile
    c_res = wm.activate_profile("coding", dry_run=True)
    assert c_res["status"] == "activated"
    assert c_res["profile"] == "coding"
    assert "launch_editor" in c_res["actions_taken"]

    # 2. Study Profile
    s_res = wm.activate_profile("study", dry_run=True)
    assert s_res["status"] == "activated"
    assert s_res["profile"] == "study"
    assert "schedule_pomodoro_timer" in s_res["actions_taken"]

    # 3. Gaming Profile
    g_res = wm.activate_profile("gaming", dry_run=True)
    assert g_res["status"] == "activated"
    assert g_res["profile"] == "gaming"
    assert "evict_models_vram" in g_res["actions_taken"]
    assert "launch_steam" in g_res["actions_taken"]

    # 4. Reset Profile
    r_res = wm.activate_profile("reset", dry_run=True)
    assert r_res["status"] == "deactivated"
    assert r_res["profile"] == "normal"

    print("  [PASS] Test 3: Coding, Study, Gaming, and Reset workspace profiles verified.")


def test_spotify_media_keys():
    print("[RUNNING] Test 4: Spotify Agent & Hardware Media Keys...")
    agent = SpotifyAgent()

    # Hardware key dispatches in dry-run mode
    p_res = agent.play_pause(dry_run=True)
    assert p_res["status"] == "success"
    assert p_res["action"] == "play_pause"

    n_res = agent.next_track(dry_run=True)
    assert n_res["status"] == "success"
    assert n_res["action"] == "next_track"

    v_res = agent.volume_up(steps=3, dry_run=True)
    assert v_res["status"] == "success"
    assert v_res["action"] == "volume_up"
    assert v_res["steps"] == 3

    m_res = agent.mute(dry_run=True)
    assert m_res["status"] == "success"
    assert m_res["action"] == "mute"

    # Natural language command routing
    cmd1 = agent.handle_media_command("pause the music", dry_run=True)
    assert cmd1["action"] == "play_pause"

    cmd2 = agent.handle_media_command("skip to next track", dry_run=True)
    assert cmd2["action"] == "next_track"

    cmd3 = agent.handle_media_command("turn up the volume", dry_run=True)
    assert cmd3["action"] == "volume_up"

    print("  [PASS] Test 4: Hardware virtual media keys and NL command mappings verified.")


def test_morning_briefing():
    print("[RUNNING] Test 5: Proactive Morning / Boot Briefing...")
    be = BriefingEngine()
    briefing = be.generate_briefing(user_name="Chen", dry_run=True)

    assert briefing["status"] == "success", f"Briefing failed: {briefing}"
    voice = briefing["voice_response"]
    assert "Good morning Chen!" in voice, f"Missing greeting: {voice}"
    assert "Celsius" in voice or "degrees" in voice, f"Missing temperature/weather: {voice}"
    assert "CPU" in voice or "system" in voice.lower(), f"Missing telemetry: {voice}"

    print("  [PASS] Test 5: Composite morning briefing synthesis verified.")


def test_llm_routes_and_supervisor():
    print("[RUNNING] Test 6: LLM Routing & Supervisor Orchestration...")
    llm = LocalLLM()
    hub = SupervisorHub(llm=llm)

    test_routes = [
        ("explain the error on my clipboard", ["clipboard_assist", "clipboard_explain"]),
        ("summarize what I just copied", ["clipboard_assist", "clipboard_summarize"]),
        ("save my clipboard to a note called Project Ideas", ["clipboard_save"]),
        ("read my proposal.txt and answer what is the budget", ["document_rag"]),
        ("switch to coding mode", ["launch_workspace", "workspace_mode"]),
        ("set up study mode", ["launch_workspace", "workspace_mode"]),
        ("prepare for gaming mode", ["launch_workspace", "workspace_mode"]),
        ("pause the music", ["media_control"]),
        ("skip this song", ["media_control"]),
        ("turn up the volume", ["media_control"]),
        ("give me my morning briefing", ["daily_briefing", "morning_briefing"]),
    ]

    for prompt, expected_actions in test_routes:
        res = llm.plan(prompt, dry_run=True)
        assert res.get("action") in expected_actions, f"Prompt '{prompt}' expected {expected_actions}, got {res.get('action')}"
        print(f"  [ROUTE PASS] '{prompt}' -> {res.get('action')}")

    # Test Compound Supervisor Intent Execution (e.g. switch to coding mode and pause the music)
    compound_prompt = "switch to coding mode and then pause the music"
    comp_res = hub.plan(compound_prompt)
    assert comp_res["compound"] is True, f"Expected compound plan, got: {comp_res}"
    assert len(comp_res["steps"]) == 2, f"Expected 2 steps, got: {comp_res['steps']}"
    assert comp_res["actions"] in [["launch_workspace", "media_control"], ["workspace_mode", "media_control"]], f"Expected actions, got: {comp_res['actions']}"
    print(f"  [COMPOUND PASS] '{compound_prompt}' -> {comp_res['actions']}")

    print("  [PASS] Test 6: All new feature routes and compound orchestration verified.")


def run_all_tests():
    print("\n" + "=" * 65)
    print("   LIBRA AI - ADVANCED SYSTEM FEATURES TEST SUITE")
    print("=" * 65 + "\n")

    test_clipboard_copilot()
    test_document_rag()
    test_workspace_profiles()
    test_spotify_media_keys()
    test_morning_briefing()
    test_llm_routes_and_supervisor()

    print("\n" + "=" * 65)
    print("Advanced System Features Suite: 6/6 Passed (100.0%)")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    run_all_tests()
