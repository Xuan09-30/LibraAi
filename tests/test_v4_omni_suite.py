import os
import sys
import tempfile
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.security_scanner import SecurityScanner
from tools.document_rag import DocumentRAGEngine
from tools.spotify_agent import SpotifyAgent
from core.llm import LocalLLM
from core.orchestrator import SupervisorHub


def run_tests():
    print("\n" + "=" * 65)
    print("   LIBRA AI - V4.0 OMNI-MODAL & SECURITY VERIFICATION SUITE")
    print("=" * 65)

    passed = 0
    total = 4

    # -------------------------------------------------------------
    # Test 1: Multi-Layer Security Scanner
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 1: Multi-Layer Virus & File Security Scanner...")
    scanner = SecurityScanner()

    # 1.1 Clean file scan
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
        f.write("Project Libra is operational. Safe file content for security test.")
        clean_temp = f.name

    try:
        clean_res = scanner.scan_path(clean_temp, dry_run=True)
        print(f"  [Clean Scan]: status='{clean_res.get('status')}', sha256='{clean_res.get('sha256')[:12]}...', defender='{clean_res.get('defender_status')}'")
        clean_ok = (
            clean_res.get("status") == "clean"
            and clean_res.get("sha256") is not None
            and len(clean_res.get("sha256")) == 64
            and clean_res.get("defender_status") == "clean"
        )
    finally:
        if os.path.exists(clean_temp):
            os.remove(clean_temp)

    # 1.2 Dangerous double-extension simulated file
    double_ext_res = scanner.scan_path("invoice.pdf.exe", dry_run=True)
    print(f"  [Double Extension Check]: status='{double_ext_res.get('status')}', issues={double_ext_res.get('issues')}")
    double_ext_ok = (
        double_ext_res.get("status") == "suspicious"
        and any("double extension" in iss.lower() for iss in double_ext_res.get("issues", []))
    )

    # 1.3 High-risk script pattern scan
    with tempfile.NamedTemporaryFile(suffix=".ps1", mode="w", delete=False, encoding="utf-8") as f:
        f.write("powershell -enc JAB4ACAAPQAgACIAMgAiAA==\nInvoke-Expression $x\n")
        suspicious_temp = f.name

    try:
        script_res = scanner.scan_path(suspicious_temp, dry_run=True)
        print(f"  [High-Risk Script Check]: status='{script_res.get('status')}', issues={script_res.get('issues')}")
        script_ok = (
            script_res.get("status") in ["suspicious", "threat_detected"]
            and len(script_res.get("issues", [])) > 0
        )
    finally:
        if os.path.exists(suspicious_temp):
            os.remove(suspicious_temp)

    # 1.4 LLM Router Intent verification
    llm = LocalLLM()
    plan_scan = llm.plan("Scan my downloads folder for viruses", dry_run=True)
    print(f"  [Virus Scan Route]: action='{plan_scan.get('action')}', target='{plan_scan.get('target')}'")
    route_ok = (
        plan_scan.get("action") == "virus_scan"
        and plan_scan.get("target") is not None
        and "download" in plan_scan.get("target").lower()
    )

    t1_pass = clean_ok and double_ext_ok and script_ok and route_ok
    if t1_pass:
        passed += 1
        print("  [PASS] Test 1: Security scanner, heuristics, double-ext check, and virus_scan route verified.")
    else:
        print(f"  [FAIL] Test 1: clean={clean_ok}, double_ext={double_ext_ok}, script={script_ok}, route={route_ok}")

    # -------------------------------------------------------------
    # Test 2: Document RAG + Auto-Security Gate
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 2: Document RAG with Auto-Security Gate...")
    rag = DocumentRAGEngine(db_filename=":memory:")

    # 2.1 Clean Document Ingestion & Query
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as f:
        f.write(
            "# System Architecture v4.0\n"
            "Project Libra integrates Kokoro-82M neural TTS at 24kHz with low-latency streaming.\n"
            "Multi-layer virus scanning protects local document ingestion.\n"
            "Hardware media keys provide sub-millisecond Spotify control.\n"
        )
        safe_doc = f.name

    try:
        # Route through LocalLLM
        rag_plan = llm.plan(f"Read {os.path.basename(safe_doc)} and tell me what TTS engine is used", dry_run=True)
        print(f"  [RAG Plan]: action='{rag_plan.get('action')}', file='{rag_plan.get('file')}'")

        rag_res = rag.query_document(safe_doc, "What TTS engine is used?", dry_run=True)
        print(f"  [RAG Query]: status='{rag_res.get('status')}', answer='{rag_res.get('answer')}'")

        safe_rag_ok = (
            rag_plan.get("action") == "document_rag"
            and rag_res.get("status") == "success"
            and len(rag_res.get("chunks")) > 0
            and "Kokoro" in rag_res.get("answer")
        )
    finally:
        if os.path.exists(safe_doc):
            os.remove(safe_doc)

    # 2.2 Security Gate Rejection on Threat / Double Extension
    with tempfile.NamedTemporaryFile(suffix=".pdf.exe", mode="w", delete=False, encoding="utf-8") as f:
        f.write("Malicious payload executable disguised as pdf")
        threat_doc = f.name

    try:
        threat_res = rag.query_document(threat_doc, "Summarize this file", dry_run=True)
        print(f"  [Security Gate Rejection]: status='{threat_res.get('status')}', issues={threat_res.get('issues')}")
        threat_blocked_ok = (
            threat_res.get("status") in ["threat_detected", "suspicious"]
            or any("double extension" in iss.lower() for iss in threat_res.get("issues", []))
        )
    finally:
        if os.path.exists(threat_doc):
            os.remove(threat_doc)

    # 2.3 Attached File Colloquial Query (Bug 1 Fix Verification)
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as f:
        f.write("# Project Libra Readme\nThis document describes how to run and configure Libra voice assistant.")
        attached_test_file = f.name

    try:
        llm.attached_file_path = attached_test_file
        attached_plan = llm.plan("what is inside this file, explain to mw", dry_run=True)
        print(f"  [Attached File Plan]: action='{attached_plan.get('action')}', file='{attached_plan.get('file')}'")
        attached_ok = (
            attached_plan.get("action") == "document_rag"
            and attached_plan.get("file") == attached_test_file
        )
    finally:
        llm.attached_file_path = None
        if os.path.exists(attached_test_file):
            os.remove(attached_test_file)

    t2_pass = safe_rag_ok and threat_blocked_ok and attached_ok
    if t2_pass:
        passed += 1
        print("  [PASS] Test 2: Document RAG extraction, grounded answering, attached file routing, and security gate refusal verified.")
    else:
        print(f"  [FAIL] Test 2: safe_rag={safe_rag_ok}, threat_blocked={threat_blocked_ok}, attached_ok={attached_ok}")

    # -------------------------------------------------------------
    # Test 3: Sentence-Level Streaming & Spotify URI Fallback
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 3: Sentence Streaming & Spotify URI Playback...")
    # 3.1 Spotify Agent Play Query
    spotify = SpotifyAgent()
    sp_res = spotify.play_query("Joji", dry_run=True)
    print(f"  [Spotify play_query]: status='{sp_res.get('status')}', voice='{sp_res.get('voice_response')}'")
    sp_query_ok = (
        sp_res.get("status") == "success"
        and "Joji" in sp_res.get("voice_response", "")
    )

    # 3.2 Spotify Direct Routing in LocalLLM
    sp_plan = llm.plan("Play Joji on Spotify", dry_run=True)
    print(f"  [Spotify Route Plan]: action='{sp_plan.get('action')}', query='{sp_plan.get('query')}'")
    sp_plan_open = llm.plan("open spotify", dry_run=True)
    print(f"  [Spotify Open Plan]: action='{sp_plan_open.get('action')}', query='{sp_plan_open.get('query')}'")
    sp_route_ok = (
        sp_plan.get("action") == "spotify_play"
        and sp_plan.get("query", "").lower() == "joji"
        and sp_plan_open.get("action") == "spotify_play"
    )

    # 3.3 Spotify Installation Detection (Bug 2 Fix Verification)
    is_installed = spotify.is_spotify_installed()
    print(f"  [Spotify Installed Detection]: {is_installed} (type={type(is_installed).__name__})")
    sp_detect_ok = isinstance(is_installed, bool)

    # 3.4 Active-Window Cropped Vision Inspection
    vision_res = llm.model_mgr.analyze_screen(prompt="Check active terminal", active_window_only=True, dry_run=True)
    print(f"  [Active Window Vision]: status='{vision_res.get('status')}', scope='{vision_res.get('scope')}'")
    vision_ok = (
        vision_res.get("status") == "analyzed"
        and "active" in vision_res.get("scope", "").lower()
    )

    t3_pass = sp_query_ok and sp_route_ok and sp_detect_ok and vision_ok
    if t3_pass:
        passed += 1
        print("  [PASS] Test 3: Spotify playback, installation detection, direct route, and active-window vision verified.")
    else:
        print(f"  [FAIL] Test 3: sp_query={sp_query_ok}, sp_route={sp_route_ok}, sp_detect={sp_detect_ok}, vision={vision_ok}")

    # -------------------------------------------------------------
    # Test 4: UI Text Command Bar & File Attachment Hooks
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 4: UI Text Submission & File Drop Hooks...")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtWidgets import QApplication
    from ui.gui import FuturisticVoiceAssistantUI

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    ui = FuturisticVoiceAssistantUI(start_worker=False)
    print(f"  [UI acceptDrops]: {ui.acceptDrops()}")
    print(f"  [UI input_box present]: {hasattr(ui, 'input_box') and ui.input_box is not None}")
    print(f"  [UI attach_btn present]: {hasattr(ui, 'attach_btn') and ui.attach_btn is not None}")
    print(f"  [UI mute_btn present]: {hasattr(ui, 'mute_btn') and ui.mute_btn is not None}")
    print(f"  [UI subtitle_label present]: {hasattr(ui, 'subtitle_label') and ui.subtitle_label is not None}")

    # Test text submission simulation
    ui.input_box.setText("What is my system telemetry?")
    ui.submit_typed_text()
    sub_text = ui.subtitle_label.text()
    print(f"  [UI Subtitle after text submit]: '{sub_text}'")

    # Test mute toggle
    ui.toggle_mute(True)
    mute_label = ui.mute_btn.text()
    print(f"  [UI Mute Toggle]: is_muted={'MUTED' in mute_label}")

    # Test safe file ingestion
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
        f.write("Libra dropped document test.")
        drop_temp = f.name

    try:
        ui.handle_file_ingestion(drop_temp)
        attached_path = ui.attached_file_path
        print(f"  [UI Attached File Path]: '{attached_path}'")
        drop_ok = attached_path == drop_temp
    finally:
        if os.path.exists(drop_temp):
            os.remove(drop_temp)

    ui_ok = (
        ui.acceptDrops() is True
        and hasattr(ui, "input_box")
        and hasattr(ui, "attach_btn")
        and hasattr(ui, "mute_btn")
        and "USER:" in sub_text
        and "MUTED" in mute_label
        and drop_ok
    )

    ui.close()

    if ui_ok:
        passed += 1
        print("  [PASS] Test 4: UI text command bar, mute toggle, and drag-and-drop security ingestion verified.")
    else:
        print(f"  [FAIL] Test 4: ui_ok={ui_ok}")

    # Summary
    print("\n" + "=" * 65)
    score_pct = (passed / total) * 100
    print(f"Project Libra v4.0 Omni Suite: {passed}/{total} Passed ({score_pct:.1f}%)")
    print("=" * 65 + "\n")

    if passed < total:
        sys.exit(1)



def test_suite():
    run_tests()

if __name__ == "__main__":
    run_tests()
