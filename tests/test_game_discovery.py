import os
import sys
import tempfile
import shutil

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.game_discovery import GameDiscoveryEngine
from core.dispatcher import SafeOSDispatcher
from core.llm import LocalLLM


def run_tests():
    print("\n" + "=" * 65)
    print("   LIBRA AI - GAME & APP DISCOVERY & CONVERSATIONAL FOLDER TESTS")
    print("=" * 65)

    passed = 0
    total = 5

    # -------------------------------------------------------------
    # Test 1: Steam Manifest & VDF Parsing + App Discovery
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 1: Steam Manifest & VDF Parsing...")
    sample_vdf = """
    "libraryfolders"
    {
        "0"
        {
            "path"      "C:\\\\Program Files (x86)\\\\Steam"
            "apps"
            {
                "2357570"       "0"
            }
        }
        "1"
        {
            "path"      "D:\\\\SteamLibrary"
            "apps"
            {
                "730"       "1000"
            }
        }
    }
    """
    sample_acf = """
    "AppState"
    {
        "appid"     "2357570"
        "name"      "Overwatch®"
        "installdir" "Overwatch"
    }
    """

    parsed_libs = GameDiscoveryEngine.parse_vdf_libraries(sample_vdf)
    parsed_acf = GameDiscoveryEngine.parse_acf_manifest(sample_acf)

    print(f"  [Parsed VDF Libraries]: {parsed_libs}")
    print(f"  [Parsed ACF Manifest]: {parsed_acf}")

    t1_pass = (
        len(parsed_libs) == 2
        and "C:\\Program Files (x86)\\Steam" in parsed_libs
        and "D:\\SteamLibrary" in parsed_libs
        and parsed_acf is not None
        and parsed_acf.get("appid") == "2357570"
        and parsed_acf.get("name") == "Overwatch"
    )

    if t1_pass:
        passed += 1
        print("  [PASS] Test 1: Steam library VDF and ACF manifest parsing verified.")
    else:
        print(f"  [FAIL] Test 1: VDF or ACF parsing failed: libs={parsed_libs}, acf={parsed_acf}")

    # -------------------------------------------------------------
    # Test 2: Game Slang & Acronym Resolution (OW, Overwatch, Valorant)
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 2: Slang & Acronym Resolution (OW, Overwatch, Valorant)...")
    discovery = GameDiscoveryEngine()
    dispatcher = SafeOSDispatcher(discovery=discovery)

    res_ow = discovery.resolve_app("ow")
    res_overwatch = discovery.resolve_app("overwatch")
    res_val = discovery.resolve_app("valo")
    res_valorant = discovery.resolve_app("valorant")

    print(f"  [Resolve 'ow']: {res_ow.get('name') if res_ow else None} -> {res_ow.get('target') if res_ow else None}")
    print(f"  [Resolve 'overwatch']: {res_overwatch.get('name') if res_overwatch else None} -> {res_overwatch.get('target') if res_overwatch else None}")
    print(f"  [Resolve 'valo']: {res_val.get('name') if res_val else None} -> {res_val.get('target') if res_val else None}")
    print(f"  [Resolve 'valorant']: {res_valorant.get('name') if res_valorant else None}")

    # Dispatcher launch checks
    disp_ow = dispatcher.launch_app("ow", dry_run=True)
    disp_val = dispatcher.launch_app("valorant", dry_run=True)
    disp_blocked = dispatcher.launch_app("cmd.exe", dry_run=True)

    print(f"  [Dispatcher Launch 'ow']: {disp_ow}")
    print(f"  [Dispatcher Launch 'valorant']: {disp_val}")
    print(f"  [Dispatcher Security Guard]: {disp_blocked}")

    t2_pass = (
        res_ow is not None and "overwatch" in res_ow.get("name", "").lower()
        and res_overwatch is not None and "overwatch" in res_overwatch.get("name", "").lower()
        and res_val is not None and "valorant" in res_val.get("name", "").lower()
        and res_valorant is not None
        and disp_ow[0] is True
        and disp_val[0] is True
        and disp_blocked[0] is False
    )

    if t2_pass:
        passed += 1
        print("  [PASS] Test 2: Slang resolution, dispatcher dispatch, and security boundaries verified.")
    else:
        print(f"  [FAIL] Test 2: Slang or dispatch check failed.")

    # -------------------------------------------------------------
    # Test 3: Conversational Folder Creation & Pronoun Follow-up
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 3: Conversational Folder Creation & Pronoun Follow-up...")
    llm = LocalLLM()

    # 3.1 Conversational create
    create_q = "Alright, how about you create a folder called LibraTest on my desktop"
    plan_create = llm.plan(create_q, dry_run=True)
    print(f"  [Conversational Create]: action='{plan_create.get('action')}', folder='{plan_create.get('args', {}).get('folder_name')}', parent='{plan_create.get('args', {}).get('parent')}'")
    create_ok = (
        plan_create.get("action") == "create_folder"
        and plan_create.get("args", {}).get("folder_name", "").lower() == "libratest"
        and plan_create.get("args", {}).get("parent") == "desktop"
    )

    # 3.2 Compound clause splitting ("I don't think I created... So can you create...")
    compound_q = "I don't think I created the Libra test folder. So can you create a Libra test folder first?"
    plan_compound = llm.plan(compound_q, dry_run=True)
    print(f"  [Compound Clause Create]: action='{plan_compound.get('action')}', folder='{plan_compound.get('args', {}).get('folder_name')}'")
    compound_ok = (
        plan_compound.get("action") == "create_folder"
        and plan_compound.get("args", {}).get("folder_name", "").lower() == "libra test"
    )

    # 3.3 Whisper mishearing defense ("read a folder called LibraTest")
    misheard_q = "How about try to read a folder called LibraTest on my desktop"
    plan_misheard = llm.plan(misheard_q, dry_run=True)
    print(f"  [Misheard 'read' Create]: action='{plan_misheard.get('action')}', folder='{plan_misheard.get('args', {}).get('folder_name')}'")
    misheard_ok = (
        plan_misheard.get("action") == "create_folder"
        and plan_misheard.get("args", {}).get("folder_name", "").lower() == "libratest"
    )

    # 3.4 Contextual pronoun opening ("Okay now open that folder for me")
    open_pronoun_q = "Okay now open that folder for me"
    plan_pronoun = llm.plan(open_pronoun_q, dry_run=True)
    print(f"  [Pronoun 'open that folder']: action='{plan_pronoun.get('action')}', folder='{plan_pronoun.get('args', {}).get('folder')}', path='{plan_pronoun.get('path')}'")
    pronoun_ok = (
        plan_pronoun.get("action") == "open_folder"
        and plan_pronoun.get("status") == "opened"
        and "libratest" in plan_pronoun.get("args", {}).get("folder", "").lower()
    )

    # 3.5 Contextual pronoun follow-up ("Yeah, open it")
    open_it_q = "Yeah, open it"
    plan_it = llm.plan(open_it_q, dry_run=True)
    print(f"  [Pronoun 'Yeah, open it']: action='{plan_it.get('action')}', folder='{plan_it.get('args', {}).get('folder')}', path='{plan_it.get('path')}'")
    it_ok = (
        plan_it.get("action") == "open_folder"
        and plan_it.get("status") == "opened"
        and "libratest" in plan_it.get("args", {}).get("folder", "").lower()
    )

    # 3.6 Plural system folder
    open_prog_q = "Open programs file folder"
    plan_prog = llm.plan(open_prog_q, dry_run=True)
    print(f"  [Plural 'programs file']: action='{plan_prog.get('action')}', status='{plan_prog.get('status')}', path='{plan_prog.get('path')}'")
    prog_ok = (
        plan_prog.get("action") == "open_folder"
        and plan_prog.get("status") == "opened"
        and plan_prog.get("path") is not None
        and "program files" in plan_prog.get("path", "").lower()
    )

    # 3.7 Conversational 'open that Libra test on here'
    temp_desktop = os.path.join(os.path.expanduser("~"), "Desktop", "LibraTest")
    os.makedirs(temp_desktop, exist_ok=True)
    try:
        open_conv_q = "Okay now how about you open that Libra test on here"
        plan_conv = llm.plan(open_conv_q, dry_run=True)
        print(f"  [Open that Libra test on here]: action='{plan_conv.get('action')}', status='{plan_conv.get('status')}', path='{plan_conv.get('path')}'")
        conv_ok = (
            plan_conv.get("action") == "open_folder"
            and plan_conv.get("status") == "opened"
            and plan_conv.get("path") is not None
            and "libratest" in plan_conv.get("path", "").lower()
        )
    finally:
        if os.path.exists(temp_desktop):
            os.rmdir(temp_desktop)

    t3_pass = create_ok and compound_ok and misheard_ok and pronoun_ok and it_ok and prog_ok and conv_ok
    if t3_pass:
        passed += 1
        print("  [PASS] Test 3: Conversational folder create/open, pronoun resolution, and clause splitting verified.")
    else:
        print(f"  [FAIL] Test 3: create={create_ok}, compound={compound_ok}, misheard={misheard_ok}, pronoun={pronoun_ok}, it={it_ok}, prog={prog_ok}, conv={conv_ok}")

    # -------------------------------------------------------------
    # Test 4: Multi-Turn App Launch Flow & Single-Turn Open-Ended
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 4: Multi-Turn App Launch & Open-Ended Routing...")
    llm_multi = LocalLLM()

    # Step 1: User says incomplete command
    turn1 = llm_multi.plan("Okay now, launch...", dry_run=True)
    print(f"  [Turn 1 Prompt: 'Okay now, launch...']: action='{turn1.get('action')}', status='{turn1.get('status')}', voice='{turn1.get('voice_response')}'")
    turn1_ok = (
        turn1.get("action") == "open_app"
        and turn1.get("status") == "clarification_needed"
        and "what application or game would you like me to launch" in turn1.get("voice_response", "").lower()
    )

    # Step 2: User responds with app name
    turn2 = llm_multi.plan("Overwatch", dry_run=True)
    print(f"  [Turn 2 Prompt: 'Overwatch']: action='{turn2.get('action')}', args={turn2.get('args')}")
    turn2_ok = (
        turn2.get("action") == "open_app"
        and turn2.get("args", {}).get("app_id") == "overwatch"
    )

    # Step 3: Single turn "Launch OW"
    turn_single = llm_multi.plan("Launch OW", dry_run=True)
    print(f"  [Single Turn Prompt: 'Launch OW']: action='{turn_single.get('action')}', args={turn_single.get('args')}")
    single_ok = (
        turn_single.get("action") == "open_app"
        and turn_single.get("args", {}).get("app_id") == "ow"
    )

    t4_pass = turn1_ok and turn2_ok and single_ok
    if t4_pass:
        passed += 1
        print("  [PASS] Test 4: Multi-turn launch flow and open-ended app routing verified.")
    else:
        print(f"  [FAIL] Test 4: turn1_ok={turn1_ok}, turn2_ok={turn2_ok}, single_ok={single_ok}")

    # -------------------------------------------------------------
    # Test 5: EAC-Safe Process Clean Environment Verification
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 5: EAC-Safe Clean Environment Verification...")
    clean_env = SafeOSDispatcher._get_clean_env()
    has_venv_var = "VIRTUAL_ENV" in clean_env
    has_pythonhome = "PYTHONHOME" in clean_env
    has_pythonpath = "PYTHONPATH" in clean_env
    path_entries = clean_env.get("PATH", "").split(os.pathsep)
    venv_in_path = [p for p in path_entries if "venv" in p.lower() or "libraai" in p.lower() or "\\libra\\" in p.lower()]

    print(f"  [Clean Env VIRTUAL_ENV present]: {has_venv_var}")
    print(f"  [Clean Env PYTHONHOME present]: {has_pythonhome}")
    print(f"  [Clean Env PYTHONPATH present]: {has_pythonpath}")
    print(f"  [Clean Env venv entries in PATH]: {len(venv_in_path)}")

    t5_pass = (
        not has_venv_var
        and not has_pythonhome
        and not has_pythonpath
        and len(venv_in_path) == 0
    )

    if t5_pass:
        passed += 1
        print("  [PASS] Test 5: Anti-cheat clean environment and process isolation verified.")
    else:
        print(f"  [FAIL] Test 5: Clean env contains venv or python markers: venv={has_venv_var}, path={venv_in_path}")

    # Summary
    print("\n" + "=" * 65)
    score_pct = (passed / total) * 100
    print(f"Game Discovery & Folder Suite: {passed}/{total} Passed ({score_pct:.1f}%)")
    print("=" * 65 + "\n")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
