import os
import sys
import shutil
import tempfile

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.file_manager import FileManager
from core.model_manager import ModelManager
from core.llm import LocalLLM
from core.orchestrator import SupervisorHub


def run_tests():
    print("\n" + "=" * 65)
    print("   LIBRA AI - FILES, VRAM SWAPPER & GAME MODE TEST SUITE")
    print("=" * 65)

    passed = 0
    total = 4

    # -------------------------------------------------------------
    # Test 1: Folder Search & Not-Found Handling
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 1: Folder Search & Not-Found Handling...")
    llm = LocalLLM()
    fm = llm.file_mgr

    # 1.1 Found folder
    res_found = llm.plan("Open Program Files folder", dry_run=True)
    print(f"  [Open Program Files]: action='{res_found.get('action')}', status='{res_found.get('status')}', path='{res_found.get('path')}'")
    found_ok = (
        res_found.get("action") == "open_folder"
        and res_found.get("status") == "opened"
        and res_found.get("path") is not None
        and os.path.exists(res_found.get("path"))
    )

    # 1.2 Not-found folder
    res_not_found = llm.plan("Open NonExistentFolder_99999_XYZ folder", dry_run=True)
    print(f"  [Not-Found Query]: action='{res_not_found.get('action')}', status='{res_not_found.get('status')}', voice='{res_not_found.get('voice_response')}'")
    not_found_ok = (
        res_not_found.get("action") == "open_folder"
        and res_not_found.get("status") == "not_found"
        and "couldn't find" in res_not_found.get("voice_response", "").lower()
    )

    t1_pass = found_ok and not_found_ok
    if t1_pass:
        passed += 1
        print("  [PASS] Test 1: File manager search and not-found fallback verified.")
    else:
        print(f"  [FAIL] Test 1: found_ok={found_ok}, not_found_ok={not_found_ok}")

    # -------------------------------------------------------------
    # Test 2: Folder Creation & Path Traversal Guard
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 2: Folder Creation & Path Traversal Guard...")
    temp_dir = tempfile.mkdtemp(prefix="libra_test_folder_")
    try:
        # 2.1 Normal folder creation
        create_res = fm.create_folder("AlphaProject", parent_location=temp_dir, dry_run=False)
        created_path = create_res.get("path")
        print(f"  [Normal Create]: status='{create_res.get('status')}', path='{created_path}'")
        normal_ok = (
            create_res.get("status") == "created"
            and created_path is not None
            and os.path.isdir(created_path)
            and os.path.basename(created_path) == "AlphaProject"
        )

        # 2.2 Path traversal defense: '../../malicious<>:name'
        traversal_res = fm.create_folder("../../malicious<>:name", parent_location=temp_dir, dry_run=False)
        traversal_path = traversal_res.get("path")
        print(f"  [Traversal Guard]: status='{traversal_res.get('status')}', path='{traversal_path}'")
        traversal_ok = (
            traversal_res.get("status") == "created"
            and traversal_path is not None
            and os.path.isdir(traversal_path)
            and traversal_path.startswith(temp_dir)
            and ".." not in os.path.basename(traversal_path)
            and "<" not in os.path.basename(traversal_path)
        )

        t2_pass = normal_ok and traversal_ok
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    if t2_pass:
        passed += 1
        print("  [PASS] Test 2: Folder creation and path traversal sanitization verified.")
    else:
        print(f"  [FAIL] Test 2: normal_ok={normal_ok}, traversal_ok={traversal_ok}")

    # -------------------------------------------------------------
    # Test 3: VRAM Swapper & qwen3:14b Deep Research Routing
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 3: VRAM Swapper & qwen3:14b Deep Research Routing...")
    # Fresh LLM instance
    llm_vram = LocalLLM()
    # Initial state
    assert llm_vram.model_mgr.current_loaded_model == "qwen3:8b"
    initial_evictions = len(llm_vram.model_mgr.eviction_history)

    # Trigger deep research
    research_plan = llm_vram.plan("Do a deep research on solid state batteries", dry_run=True)
    print(f"  [Deep Research Plan]: action='{research_plan.get('action')}', profile='{research_plan.get('profile')}', model='{research_plan.get('model')}'")
    model_spec = research_plan.get("args", {}).get("model_spec", {})
    print(f"  [Model Spec]: requested='{model_spec.get('requested_model')}', think={model_spec.get('think')}")
    print(f"  [Evictions Recorded]: {len(llm_vram.model_mgr.eviction_history)}")

    t3_pass = (
        research_plan.get("action") == "deep_research"
        and research_plan.get("profile") == "heavy_research"
        and research_plan.get("model") == "qwen3:14b"
        and model_spec.get("think") is True
        and len(llm_vram.model_mgr.eviction_history) > initial_evictions
        and llm_vram.model_mgr.eviction_history[-1]["evicted"] == "qwen3:8b"
    )

    if t3_pass:
        passed += 1
        print("  [PASS] Test 3: Deep research routing, qwen3:14b target, think=True, and 8B VRAM eviction verified.")
    else:
        print(f"  [FAIL] Test 3: action={research_plan.get('action')}, model={research_plan.get('model')}, evictions={llm_vram.model_mgr.eviction_history}")

    # -------------------------------------------------------------
    # Test 4: Game Mode Toggle & Valorant Auto-Trigger
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 4: Game Mode Toggle & Valorant Auto-Trigger...")
    llm_gm = LocalLLM()
    assert llm_gm.model_mgr.game_mode_active is False

    # 4.1 Explicit enable
    gm_enable_plan = llm_gm.plan("Enable game mode", dry_run=True)
    print(f"  [Enable Game Mode]: action='{gm_enable_plan.get('action')}', game_mode_active={llm_gm.model_mgr.game_mode_active}")
    enable_ok = (
        gm_enable_plan.get("action") == "toggle_game_mode"
        and gm_enable_plan.get("args", {}).get("enabled") is True
        and llm_gm.model_mgr.game_mode_active is True
    )

    # 4.2 Explicit disable
    gm_disable_plan = llm_gm.plan("Disable game mode", dry_run=True)
    print(f"  [Disable Game Mode]: action='{gm_disable_plan.get('action')}', game_mode_active={llm_gm.model_mgr.game_mode_active}")
    disable_ok = (
        gm_disable_plan.get("action") == "toggle_game_mode"
        and gm_disable_plan.get("args", {}).get("enabled") is False
        and llm_gm.model_mgr.game_mode_active is False
    )

    # 4.3 Auto Game Mode Hook via Launch Valorant
    val_plan = llm_gm.plan("Launch Valorant.", dry_run=True)
    print(f"  [Launch Valorant]: action='{val_plan.get('action')}', game_mode_active={llm_gm.model_mgr.game_mode_active}")
    val_auto_ok = (
        val_plan.get("action") == "open_app"
        and val_plan.get("args", {}).get("app_id") == "valorant"
        and llm_gm.model_mgr.game_mode_active is True
    )

    t4_pass = enable_ok and disable_ok and val_auto_ok
    if t4_pass:
        passed += 1
        print("  [PASS] Test 4: Game mode manual toggle and Valorant auto-trigger verified.")
    else:
        print(f"  [FAIL] Test 4: enable={enable_ok}, disable={disable_ok}, val_auto={val_auto_ok}")

    # Summary
    print("\n" + "=" * 65)
    score_pct = (passed / total) * 100
    print(f"Files & Game Mode Suite Score: {passed}/{total} Passed ({score_pct:.1f}%)")
    print("=" * 65 + "\n")

    if passed < total:
        sys.exit(1)



def test_suite():
    run_tests()

if __name__ == "__main__":
    run_tests()
