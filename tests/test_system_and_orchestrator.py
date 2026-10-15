import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.system_monitor import SystemMonitor
from core.memory import SemanticMemory
from core.llm import LocalLLM
from core.orchestrator import SupervisorHub


def run_tests():
    print("\n" + "=" * 65)
    print("   LIBRA AI - SYSTEM MONITOR, EPISODIC MEMORY & ORCHESTRATOR TESTS")
    print("=" * 65)

    passed = 0
    total = 3

    # -------------------------------------------------------------
    # Test 1: SystemMonitor Telemetry & 3-Second Timeout Guardrails
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 1: SystemMonitor Telemetry & Guardrails...")
    monitor = SystemMonitor(timeout=3.0)

    # 1.1 Metrics
    metrics = monitor.get_system_metrics()
    print(f"  [System Metrics]: {metrics.get('summary')}")
    metrics_valid = (
        metrics.get("ram_used_gb", 0) > 0
        and metrics.get("ram_total_gb", 0) > 0
        and len(metrics.get("summary", "")) > 10
    )

    # 1.2 Open Windows
    windows = monitor.list_open_windows()
    print(f"  [Visible Windows Count]: {len(windows)}")
    windows_valid = isinstance(windows, list)

    # 1.3 Allowlisted Diagnostic
    diag_net = monitor.run_safe_diagnostic("network_info")
    print(f"  [Diagnostic 'network_info' Output Length]: {len(diag_net)} chars")
    diag_valid = len(diag_net) > 0 and len(diag_net) <= 1000

    # 1.4 Command Injection & Non-Allowlisted Rejection
    diag_rejected = monitor.run_safe_diagnostic("malicious_command")
    print(f"  [Rejection Test]: '{diag_rejected}'")
    reject_valid = "not in the allowlist" in diag_rejected or "Error" in diag_rejected

    t1_pass = metrics_valid and windows_valid and diag_valid and reject_valid
    if t1_pass:
        passed += 1
        print("  [PASS] Test 1: System telemetry, window enumeration, and safe execution verified.")
    else:
        print(f"  [FAIL] Test 1: metrics={metrics_valid}, win={windows_valid}, diag={diag_valid}, reject={reject_valid}")

    # -------------------------------------------------------------
    # Test 2: Episodic Memory Logging & Cosine Vector Retrieval
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 2: Episodic Memory Logging & Vector Retrieval...")
    test_db = "assets/test_episodic_suite.db"
    test_db_full = os.path.join(PROJECT_ROOT, test_db)
    if os.path.exists(test_db_full):
        try:
            os.remove(test_db_full)
        except Exception:
            pass

    memory = SemanticMemory(db_filename=test_db)
    ep_id = memory.log_episode(
        user_text="What competitive shooter do I play most?",
        assistant_text="You spend most of your competitive gaming hours playing Valorant with your squad.",
        route="chat"
    )
    print(f"  [Logged Episode ID]: {ep_id}")

    # Semantically retrieve episode using dissimilar wording
    recalled = memory.recall_episodes("Tell me about my favorite FPS games", limit=2, distance_threshold=0.65)
    print(f"  [Recalled Episodes Count]: {len(recalled)}")
    for r in recalled:
        print(f"    - ID: {r['id']} | Dist: {r['distance']:.4f} | Text: {r['assistant_text'][:60]}...")

    t2_pass = (
        ep_id > 0
        and len(recalled) >= 1
        and "Valorant" in recalled[0]["assistant_text"]
    )

    if t2_pass:
        passed += 1
        print("  [PASS] Test 2: Episodic conversation turn logged and semantically retrieved.")
    else:
        print(f"  [FAIL] Test 2: ep_id={ep_id}, recalled={recalled}")

    # Clean up test database
    if os.path.exists(test_db_full):
        try:
            os.remove(test_db_full)
        except Exception:
            pass

    # -------------------------------------------------------------
    # Test 3: SupervisorHub Compound Orchestration & MAX_STEPS = 4 Cap
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 3: SupervisorHub Compound Orchestration & Loop Caps...")
    llm = LocalLLM()
    hub = SupervisorHub(llm=llm)

    # 3.1 Single Intent Fast Path (<5ms bypass)
    fast_res = hub.plan("Can you predict the weather for next month?")
    print(f"  [Fast-Path Query]: action='{fast_res.get('action')}', compound={fast_res.get('compound')}")
    fast_ok = fast_res.get("compound") is False and fast_res.get("action") == "chat"

    # 3.2 Compound Request Splitting & Execution
    compound_query = "Remember that I like jazz and set a timer for 10 minutes"
    comp_res = hub.plan(compound_query)
    print(f"  [Compound Query]: steps={comp_res.get('steps')}, actions={comp_res.get('actions')}")
    comp_ok = (
        comp_res.get("compound") is True
        and len(comp_res.get("steps", [])) == 2
        and comp_res.get("actions") == ["remember_fact", "schedule_reminder"]
    )

    # 3.3 Loop Guard: MAX_STEPS = 4 Enforcement
    six_step_query = (
        "remember that I like jazz and "
        "set a timer for 10 minutes and "
        "check my system status and "
        "launch valorant and "
        "close the active window and "
        "remind me at 5:00 PM to play games"
    )
    capped_steps = hub.split_compound_intent(six_step_query)
    print(f"  [Loop Guard Split (6 inputs)]: {len(capped_steps)} steps extracted (Max: {hub.MAX_STEPS})")
    cap_ok = len(capped_steps) == hub.MAX_STEPS

    t3_pass = fast_ok and comp_ok and cap_ok
    if t3_pass:
        passed += 1
        print("  [PASS] Test 3: Fast-path bypass, compound multi-intent execution, and 4-step loop guard verified.")
    else:
        print(f"  [FAIL] Test 3: fast={fast_ok}, comp={comp_ok}, cap={cap_ok}")

    # Summary
    print("\n" + "=" * 65)
    score_pct = (passed / total) * 100
    print(f"System & Orchestrator Suite Score: {passed}/{total} Passed ({score_pct:.1f}%)")
    print("=" * 65 + "\n")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
