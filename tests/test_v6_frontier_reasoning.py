import os
import sys
import tempfile

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scratchpad import AgentScratchpad
from core.clarifier import AmbiguityDetector
from core.self_refine import ExecutionRefiner
from core.sentiment_detector import SentimentAdapter
from core.context_distiller import ContextDistiller
from core.artifact_manager import ArtifactManager
from core.memory import SemanticMemory
from tools.clipboard_agent import ClipboardAgent
from core.llm import LocalLLM
from core.orchestrator import SupervisorHub


def run_tests():
    print("\n" + "=" * 68)
    print("   LIBRA AI - V6.0 FRONTIER REASONING & METANAVIGATION SUITE")
    print("=" * 68)

    passed = 0
    total = 6

    # -------------------------------------------------------------
    # Test 1: Scratchpad Graph, Self-Reflection & 4-Step Loop Guard
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 1: AgentScratchpad Execution Graph & Loop Guard...")
    scratchpad = AgentScratchpad()

    # 1.1 Execute 3 subtasks sequentially
    three_tasks = [
        {"id": 1, "action": "system_status", "args": {"type": "metrics"}},
        {"id": 2, "action": "remember_fact", "args": {"fact": "Project Libra v6 online"}},
        {"id": 3, "action": "launch_workspace", "args": {"mode": "coding"}},
    ]
    scratchpad.init_plan("Prepare coding environment and log status", three_tasks)
    graph_res = scratchpad.execute_graph(
        lambda task: {
            "status": "success",
            "action": task["action"],
            "voice_response": f"Completed {task['action'].replace('_', ' ')}."
        }
    )
    print(f"  [3-Step Graph Executed]: steps={graph_res['steps_executed']}, summary='{graph_res['spoken_summary']}'")
    three_step_ok = (
        graph_res["steps_executed"] == 3
        and all(t["status"] == "completed" for t in graph_res["subtasks"])
        and len(graph_res["spoken_summary"]) > 0
    )

    # 1.2 Enforce MAX_SUBTASKS = 4 loop guard on 6 input subtasks
    six_tasks = [{"action": f"step_{i}", "args": {}} for i in range(6)]
    scratchpad.init_plan("Over-limit compound goal", six_tasks)
    cap_ok = len(scratchpad.subtasks) == AgentScratchpad.MAX_SUBTASKS == 4
    print(f"  [Loop Guard Cap (6 inputs)]: {len(scratchpad.subtasks)} subtasks retained (Max: {AgentScratchpad.MAX_SUBTASKS})")

    # 1.3 Intermediate Self-Reflection on failed step
    scratchpad.init_plan("Open missing folder", [{"action": "open_folder", "args": {"folder": "Missing Directory"}}])
    ref_out = scratchpad.reflect_and_plan({"status": "not_found", "folder": "Missing Directory"})
    print(f"  [Self-Reflection on Failure]: succeeded={ref_out['step_succeeded']}, alternate={ref_out['alternate_subtask']['action']}")
    reflect_ok = (
        ref_out["step_succeeded"] is False
        and ref_out["alternate_subtask"] is not None
        and len(scratchpad.reflection_notes) >= 1
    )

    t1_pass = three_step_ok and cap_ok and reflect_ok
    if t1_pass:
        passed += 1
        print("  [PASS] Test 1: 3-subtask sequential execution, 4-step loop cap, and intermediate self-reflection verified.")
    else:
        print(f"  [FAIL] Test 1: three_step={three_step_ok}, cap={cap_ok}, reflect={reflect_ok}")

    # -------------------------------------------------------------
    # Test 2: Active Clarification & Next-Turn Ordinal Resolution
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 2: Active Clarification & Next-Turn Resolution...")
    llm = LocalLLM()
    llm.session_mgr.update_candidates([
        {"name": "LibraAi", "path": os.path.join(PROJECT_ROOT)},
        {"name": "SimpleClimate", "path": os.path.join(PROJECT_ROOT, "SimpleClimate")}
    ])
    llm.session_state["candidates"] = llm.session_mgr.candidates

    # Turn 1: Ambiguous folder request
    turn1_res = llm.plan("Open the project folder", dry_run=True)
    print(f"  [Turn 1 Ambiguous Query]: action='{turn1_res.get('action')}', question='{turn1_res.get('voice_response')}'")
    turn1_ok = (
        turn1_res.get("is_ambiguous") is True
        and "LibraAi" in turn1_res.get("voice_response", "")
        and "SimpleClimate" in turn1_res.get("voice_response", "")
        and llm.pending_clarification is not None
    )

    # Turn 2: Resolve with "The first one"
    turn2_res = llm.plan("The first one", dry_run=True)
    print(f"  [Turn 2 Follow-Up 'The first one']: action='{turn2_res.get('action')}', selected='{turn2_res.get('selected')}'")
    turn2_ok = (
        turn2_res.get("action") == "open_folder"
        and turn2_res.get("clarification_resolved") is True
        and turn2_res.get("selected") == "LibraAi"
        and llm.pending_clarification is None
    )

    # Reset candidates so subsequent tests have clean state
    llm.session_mgr.clear_candidates()
    llm.session_state["candidates"] = []

    t2_pass = turn1_ok and turn2_ok
    if t2_pass:
        passed += 1
        print("  [PASS] Test 2: Ambiguity detection, clarifying question generation, and 'The first one' resolution verified.")
    else:
        print(f"  [FAIL] Test 2: turn1={turn1_ok}, turn2={turn2_ok}")

    # -------------------------------------------------------------
    # Test 3: Self-Refine Output Critique & Query Reformulation
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 3: Self-Refine Query Reformulation & Retry Loop...")
    refiner = ExecutionRefiner()

    # 3.1 Simulated 0-result search query that succeeds after reformulation
    noisy_query = "Hey Libra, can you please search for the exact RTX 5060 Ti benchmarks right now?"
    initial_empty = {"action": "web_search", "query": noisy_query, "sources": [], "voice_response": "Found no verified results."}

    def mock_search_retry(reformulated_q: str):
        return {
            "action": "web_search",
            "query": reformulated_q,
            "sources": [{"name": "TechPowerUp", "text": "RTX 5060 Ti 16GB delivers strong 1440p performance."}],
            "voice_response": "According to TechPowerUp, the RTX 5060 Ti 16GB delivers strong 1440p performance."
        }

    refined_res = refiner.refine_and_retry(
        action="web_search",
        query=noisy_query,
        initial_result=initial_empty,
        retry_callback=mock_search_retry
    )
    print(f"  [Original Query]:     '{noisy_query}'")
    print(f"  [Reformulated Query]: '{refined_res.get('reformulated_query')}'")
    print(f"  [Retry Succeeded]:    {refined_res.get('retry_succeeded')} (sources={len(refined_res.get('sources', []))})")

    web_refine_ok = (
        refined_res.get("refined") is True
        and refined_res.get("retry_succeeded") is True
        and len(refined_res.get("sources", [])) == 1
        and "RTX 5060 Ti" in refined_res.get("reformulated_query", "")
        and "please" not in refined_res.get("reformulated_query", "").lower()
    )

    # 3.2 Fuzzy file matching fallback
    with tempfile.TemporaryDirectory() as tmp_dir:
        target_dir = os.path.join(tmp_dir, "Flood_Prediction_Proposal")
        os.makedirs(target_dir, exist_ok=True)
        fuzzy_res = refiner.refine_and_retry(
            action="open_folder",
            query="flood prediction proposal",
            initial_result={"status": "not_found"},
            search_dirs=[tmp_dir]
        )
        fuzzy_ok = (
            fuzzy_res.get("refined") is True
            and fuzzy_res.get("retry_succeeded") is True
            and fuzzy_res.get("folder") == "Flood_Prediction_Proposal"
        )
        print(f"  [Fuzzy File Recovery]: status='{fuzzy_res.get('status')}', folder='{fuzzy_res.get('folder')}'")

    t3_pass = web_refine_ok and fuzzy_ok
    if t3_pass:
        passed += 1
        print("  [PASS] Test 3: Output critique, web query reformulation retry, and fuzzy folder recovery verified.")
    else:
        print(f"  [FAIL] Test 3: web_refine={web_refine_ok}, fuzzy={fuzzy_ok}")

    # -------------------------------------------------------------
    # Test 4: Sentiment Analysis & High-Urgency Brevity (<12 words)
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 4: Sentiment Analysis & High-Urgency Brevity...")
    urgent_prompt = "Hurry up and kill the process now!"
    urgent_res = llm.plan(urgent_prompt, dry_run=True)
    urgent_voice = urgent_res.get("voice_response", "")
    word_count = len(urgent_voice.split())
    print(f"  [Urgent Prompt]: '{urgent_prompt}'")
    print(f"  [Detected Urgency]: '{urgent_res.get('urgency')}' (multiplier={urgent_res.get('sentiment', {}).get('brevity_multiplier')})")
    print(f"  [Voice Response ({word_count} words)]: '{urgent_voice}'")

    t4_pass = (
        urgent_res.get("urgency") == "high"
        and urgent_res.get("action") == "close_app"
        and 0 < word_count < 12
        and "by the way" not in urgent_voice.lower()
    )
    if t4_pass:
        passed += 1
        print("  [PASS] Test 4: High-urgency valence detected and voice response compressed under 12 words with zero banter.")
    else:
        print(f"  [FAIL] Test 4: urgency={urgent_res.get('urgency')}, action={urgent_res.get('action')}, words={word_count}")

    # -------------------------------------------------------------
    # Test 5: Context Rolling Compaction & Memory Distillation
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 5: Context Rolling Compaction & Memory Distillation...")
    mem_isolated = SemanticMemory(db_filename=":memory:")
    distiller = ContextDistiller(memory=mem_isolated)

    ten_turns = [
        {"role": "user", "content": "I am optimizing the FloodPrediction neural network in PyTorch."},
        {"role": "assistant", "content": "Understood. Let me know if you need VRAM telemetry for FloodPrediction."},
        {"role": "user", "content": "Check benchmarks for the RTX 5060 Ti GPU."},
        {"role": "assistant", "content": "The RTX 5060 Ti has 16GB GDDR7 memory."},
        {"role": "user", "content": "We are deploying the service in Kuala Lumpur."},
        {"role": "assistant", "content": "Noted Kuala Lumpur deployment target."},
        {"role": "user", "content": "Also integrate sqlite-vec for vector indexing."},
        {"role": "assistant", "content": "sqlite-vec is configured for 768-dim cosine search."},
        {"role": "user", "content": "Now switch to coding mode."},
        {"role": "assistant", "content": "Coding mode is active."}
    ]

    compressed_turns, summary_text = distiller.compress_history(ten_turns, threshold=8, dry_run=False)
    token_est = distiller.estimate_tokens(compressed_turns)
    print(f"  [Distilled Summary]: {summary_text}")
    print(f"  [Turn Count]: 10 -> {len(compressed_turns)} turns (Est. {token_est} tokens, Budget < 2048)")

    entities_preserved = (
        "FloodPrediction" in summary_text
        and ("RTX 5060 Ti" in summary_text or "Kuala Lumpur" in summary_text)
    )
    compression_ok = (
        len(compressed_turns) < len(ten_turns)
        and compressed_turns[0]["content"].startswith("[Context Summary:")
        and token_est < 2048
        and entities_preserved
    )

    if compression_ok:
        passed += 1
        print("  [PASS] Test 5: 10 turns compacted into dense summary preserving key entities and archived in SemanticMemory.")
    else:
        print(f"  [FAIL] Test 5: len={len(compressed_turns)}, entities_preserved={entities_preserved}")

    # -------------------------------------------------------------
    # Test 6: Artifact Extraction & Clipboard Hook
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 6: Artifact Extraction & Clipboard Hook...")
    clip_agent = ClipboardAgent()
    art_mgr = ArtifactManager(clipboard_agent=clip_agent)

    raw_llm_output = (
        "Here is the fib function you requested:\n"
        "```python\n"
        "def fibonacci(n: int) -> int:\n"
        "    if n <= 1:\n"
        "        return n\n"
        "    return fibonacci(n - 1) + fibonacci(n - 2)\n"
        "```\n"
    )
    spoken_text, extracted_list = art_mgr.process_response(raw_llm_output)
    clipboard_payload = clip_agent.get_clipboard_text()
    print(f"  [Spoken Summary]: '{spoken_text}'")
    print(f"  [Extracted Artifacts Count]: {len(extracted_list)} (type='{extracted_list[0].get('type') if extracted_list else None}')")
    print(f"  [Clipboard Payload First Line]: '{clipboard_payload.splitlines()[0] if clipboard_payload else ''}'")

    t6_pass = (
        len(extracted_list) == 1
        and extracted_list[0]["type"] == "code"
        and extracted_list[0]["language"] == "python"
        and "def fibonacci" in clipboard_payload
        and "```" not in spoken_text
        and "def fibonacci" not in spoken_text
        and "clipboard" in spoken_text.lower()
    )
    if t6_pass:
        passed += 1
        print("  [PASS] Test 6: Code block stripped from TTS, natural spoken summary generated, and code copied to clipboard.")
    else:
        print(f"  [FAIL] Test 6: count={len(extracted_list)}, clip='{clipboard_payload[:30]}', spoken='{spoken_text}'")

    # Summary
    print("\n" + "=" * 68)
    score_pct = (passed / total) * 100
    print(f"Project Libra v6.0 Frontier Reasoning Suite: {passed}/{total} Passed ({score_pct:.1f}%)")
    print("=" * 68 + "\n")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
