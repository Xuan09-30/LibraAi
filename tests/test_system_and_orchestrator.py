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
    memory.close()
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





def test_router_30_labeled_queries_accuracy():
    """
    Tier 1 & Tier 2 Router Accuracy Test Table (30 labeled queries across chitchat, real-time, and mixed):
    - Real-time signals must be checked FIRST.
    - Chitchat is only matched when the query is short (<= 8 words) and has NO real-time signal.
    """
    llm = LocalLLM()
    # Stub call_ollama so router test is deterministic and fast when falling through to LLM classifier
    llm.call_ollama = lambda *a, **kw: '{"action": "chat", "query": ""}'

    labeled_table = [
        # --- 10 Chitchat Queries (<= 8 words, no real-time signal -> 'chat') ---
        ("how you feeling today?", "chitchat", "chat"),
        ("how are you doing", "chitchat", "chat"),
        ("hey libra", "chitchat", "chat"),
        ("are you okay", "chitchat", "chat"),
        ("what are you up to", "chitchat", "chat"),
        ("tell me a joke", "chitchat", "chat"),
        ("how was your day", "chitchat", "chat"),
        ("are you awake", "chitchat", "chat"),
        ("hello there", "chitchat", "chat"),
        ("any fun stuff we can do?", "chitchat", "chat"),

        # --- 10 Real-time Queries (real-time signal -> 'web_search') ---
        ("latest news on AI benchmarks", "real-time", "web_search"),
        ("what is the bitcoin price", "real-time", "web_search"),
        ("breaking news headlines", "real-time", "web_search"),
        ("who won the game", "real-time", "web_search"),
        ("premier league standings", "real-time", "web_search"),
        ("f1 match score", "real-time", "web_search"),
        ("stock price of nvidia", "real-time", "web_search"),
        ("top news updates today", "real-time", "web_search"),
        ("what happened today in tech", "real-time", "web_search"),
        ("crypto price updates today", "real-time", "web_search"),

        # --- 10 Mixed Queries (chitchat greeting + real-time signal or >8 words) ---
        ("hey how are you doing what is the latest news", "mixed", "web_search"),
        ("hello libra how is your day and check breaking news", "mixed", "web_search"),
        ("hi how you feeling today what is the bitcoin price", "mixed", "web_search"),
        ("hey there what is up with the nba playoff standings", "mixed", "web_search"),
        ("yo are you awake tell me today's headlines", "mixed", "web_search"),
        ("how is it going can you check premier league standings", "mixed", "web_search"),
        ("greetings libra what happened today in formula 1", "mixed", "web_search"),
        ("hey are you okay what is the stock price", "mixed", "web_search"),
        ("hi what are you doing check live score", "mixed", "web_search"),
        ("how are you doing today can you explain why the sky appears blue during daytime", "mixed", "chat"),
    ]

    correct = 0
    mismatches = []
    for query, category, expected_action in labeled_table:
        res = llm.plan(query, dry_run=True)
        actual_action = res.get("action")
        if actual_action == expected_action:
            correct += 1
        else:
            mismatches.append((query, category, expected_action, actual_action))

    accuracy = (correct / len(labeled_table)) * 100.0
    print(f"\n[Router Test Table] Accuracy: {correct}/{len(labeled_table)} ({accuracy:.1f}%)")
    assert len(mismatches) == 0, f"Router accuracy {correct}/{len(labeled_table)} ({accuracy:.1f}%). Mismatches: {mismatches}"


def test_suite():
    run_tests()

if __name__ == "__main__":
    run_tests()
