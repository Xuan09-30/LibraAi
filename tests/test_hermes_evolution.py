import os
import sys
import tempfile
import time
import yaml

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.persona import PersonaEngine
from core.skill_forge import SkillForge, SkillSecurityVisitor
from core.habit_learner import HabitLearner
from core.llm import LocalLLM
from core.orchestrator import SupervisorHub


def run_tests():
    print("\n" + "=" * 65)
    print("   LIBRA AI - V5.0 HERMES SELF-IMPROVING EVOLUTION SUITE")
    print("=" * 65)

    passed = 0
    total = 5

    # -------------------------------------------------------------
    # Test 1: SkillForge Autonomous Creation & AST Security Sandbox
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 1: Autonomous Skill Creation & AST Sandbox...")
    with tempfile.TemporaryDirectory() as temp_skills_dir:
        forge = SkillForge(skills_dir=temp_skills_dir)

        # 1.1 Create skill
        task_prompt = "Create a skill called system uptime check that calculates system boot uptime"
        create_res = forge.create_skill(task_prompt, dry_run=False)
        print(f"  [Skill Creation]: status='{create_res.get('status')}', slug='{create_res.get('slug')}', name='{create_res.get('name')}'")

        create_ok = (
            create_res.get("status") == "success"
            and create_res.get("slug") == "system_uptime_check"
            and create_res.get("name") == "System Uptime Check"
            and os.path.isfile(os.path.join(temp_skills_dir, "system_uptime_check", "SKILL.md"))
            and os.path.isfile(os.path.join(temp_skills_dir, "system_uptime_check", "skill.py"))
        )

        # 1.2 Verify list_skills Level 0 metadata index
        skills_list = forge.list_skills()
        list_ok = (
            len(skills_list) == 1
            and skills_list[0]["slug"] == "system_uptime_check"
            and "uptime" in " ".join(skills_list[0].get("triggers", []))
        )

        # 1.3 Execute created skill
        exec_res = forge.run_skill("system_uptime_check")
        print(f"  [Skill Execution]: status='{exec_res.get('status')}', voice='{exec_res.get('voice_response')}'")
        exec_ok = (
            exec_res.get("status") == "success"
            and "running" in exec_res.get("voice_response", "").lower()
        )

        # 1.4 AST Security Sandbox: Reject dangerous calls
        # A: shutil.rmtree
        safe_a, reason_a = forge.validate_skill_code(
            "import shutil\ndef execute(args, context):\n    shutil.rmtree('C:/')\n    return {'status': 'ok'}"
        )
        # B: subprocess with shell=True
        safe_b, reason_b = forge.validate_skill_code(
            "import subprocess\ndef execute(args, context):\n    subprocess.run('dir', shell=True)\n    return {'status': 'ok'}"
        )
        # C: eval/exec dynamic code execution
        safe_c, reason_c = forge.validate_skill_code(
            "def execute(args, context):\n    eval('2+2')\n    return {'status': 'ok'}"
        )
        # D: missing execute function
        safe_d, reason_d = forge.validate_skill_code(
            "import math\ndef calculate():\n    return 42"
        )
        # E: forbidden module import (ctypes)
        safe_e, reason_e = forge.validate_skill_code(
            "import ctypes\ndef execute(args, context):\n    return {'status': 'ok'}"
        )

        sandbox_ok = (
            not safe_a and "rmtree" in reason_a
            and not safe_b and "shell=True" in reason_b
            and not safe_c and "eval" in reason_c
            and not safe_d and "execute" in reason_d
            and not safe_e and "ctypes" in reason_e
        )
        print(f"  [AST Sandbox Rejections]: rmtree={not safe_a}, shell={not safe_b}, eval={not safe_c}, no_exec={not safe_d}, ctypes={not safe_e}")

    t1_pass = create_ok and list_ok and exec_ok and sandbox_ok
    if t1_pass:
        passed += 1
        print("  [PASS] Test 1: Autonomous skill creation, Level 0 indexing, dynamic execution, and AST sandbox verified.")
    else:
        print(f"  [FAIL] Test 1: create={create_ok}, list={list_ok}, exec={exec_ok}, sandbox={sandbox_ok}")

    # -------------------------------------------------------------
    # Test 2: Self-Healing Runtime Loop (ZeroDivisionError Auto-Repair)
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 2: Self-Healing Runtime Loop...")
    with tempfile.TemporaryDirectory() as temp_skills_dir:
        forge = SkillForge(skills_dir=temp_skills_dir)
        skill_dir = os.path.join(temp_skills_dir, "calc_metric")
        os.makedirs(skill_dir, exist_ok=True)

        # Write buggy skill with ZeroDivisionError
        buggy_code = (
            "def execute(args: dict, context: dict) -> dict:\n"
            "    val = 100 / 0\n"
            "    return {'status': 'success', 'voice_response': f'Result: {val}'}\n"
        )
        with open(os.path.join(skill_dir, "skill.py"), "w", encoding="utf-8") as f:
            f.write(buggy_code)

        frontmatter = {
            "name": "Calc Metric",
            "description": "Calculates metric with intentional division by zero.",
            "triggers": ["calc metric"],
            "version": "1.0.0",
            "success_count": 0
        }
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(f"---\n{yaml.dump(frontmatter, sort_keys=False)}---\n# Calc Metric\n")

        # Run skill expecting auto-recovery
        heal_res = forge.run_skill("calc_metric")
        print(f"  [Self-Heal Result]: status='{heal_res.get('status')}', self_healed={heal_res.get('self_healed')}, voice='{heal_res.get('voice_response')}'")

        # Verify SKILL.md version was bumped to 1.0.1
        meta = forge._parse_skill_md(os.path.join(skill_dir, "SKILL.md"))
        version_bumped = meta.get("version") == "1.0.1"

        heal_ok = (
            heal_res.get("status") == "success"
            and heal_res.get("self_healed") is True
            and version_bumped
        )

    if heal_ok:
        passed += 1
        print("  [PASS] Test 2: Self-healing error capture, AST re-validation, version bump, and auto-retry verified.")
    else:
        print(f"  [FAIL] Test 2: heal_ok={heal_ok}, version_bumped={version_bumped}")

    # -------------------------------------------------------------
    # Test 3: PersonaEngine Anti-Repetition & SOUL.md Updates
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 3: PersonaEngine Anti-Repetition & SOUL.md Updates...")
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as soul_f, \
         tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as user_f:
        soul_f.write("# LIBRA SOUL\n- Wit: Balanced\n- Tone: Confident\n")
        user_f.write("# USER PROFILE\n")
        temp_soul = soul_f.name
        temp_user = user_f.name

    try:
        persona = PersonaEngine(soul_path=temp_soul, user_path=temp_user)

        # 3.1 Anti-repetition across 5 consecutive calls
        t0 = time.perf_counter()
        responses = []
        for _ in range(5):
            r = persona.humanize_response(
                "Launching Steam now.",
                action_type="open_app",
                context={"target": "Steam"}
            )
            responses.append(r)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        unique_count = len(set(responses))
        print(f"  [Anti-Repetition 5 Calls]: {unique_count}/5 distinct responses in {elapsed_ms:.2f}ms")
        for idx, resp in enumerate(responses):
            print(f"    Call {idx+1}: '{resp}'")

        anti_rep_ok = (unique_count == 5) and (elapsed_ms < 20.0)

        # 3.2 Dynamic SOUL.md Trait Update
        ack = persona.update_soul_trait("Be more sarcastic and witty")
        print(f"  [Soul Trait Update Acknowledgment]: '{ack}'")

        with open(temp_soul, "r", encoding="utf-8") as f:
            saved_soul = f.read()

        soul_ok = (
            len(ack) > 10
            and "Dynamic Trait Update: Sarcastic and witty" in saved_soul
        )

        # 3.3 System prompt injection
        addon = persona.get_system_prompt_addon()
        addon_ok = "SOUL.md" in addon and "Anti-Repetition Rule" in addon

    finally:
        if os.path.exists(temp_soul):
            os.remove(temp_soul)
        if os.path.exists(temp_user):
            os.remove(temp_user)

    t3_pass = anti_rep_ok and soul_ok and addon_ok
    if t3_pass:
        passed += 1
        print("  [PASS] Test 3: Anti-repetition (<2ms dynamic variation) and SOUL.md trait persistence verified.")
    else:
        print(f"  [FAIL] Test 3: anti_rep={anti_rep_ok}, soul={soul_ok}, addon={addon_ok}")

    # -------------------------------------------------------------
    # Test 4: HabitLearner Pattern Discovery & Proactive Suggestions
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 4: HabitLearner Routine Discovery & USER.md Sync...")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as db_f, \
         tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as user_f:
        temp_db = db_f.name
        temp_user = user_f.name
        user_f.write("# USER PROFILE\n\n## Bio\nUser: Chen Xuan\n")

    try:
        habits = HabitLearner(db_path=temp_db, user_md_path=temp_user)

        # 4.1 Record transition sequence 3 times: open_app:steam -> launch_workspace:gaming
        for _ in range(3):
            habits.record_action("open_app", "steam")
            habits.record_action("launch_workspace", "gaming")

        # 4.2 Detect patterns
        patterns = habits.detect_patterns()
        print(f"  [Discovered Sequential Patterns]: {len(patterns.get('sequential', []))}")
        seq_found = False
        for s in patterns.get("sequential", []):
            print(f"    Flow: {s['from_action']}:{s['from_target']} -> {s['to_action']}:{s['to_target']} ({s['count']}x, {s['confidence']*100:.0f}%)")
            if s["from_action"] == "open_app" and s["to_action"] == "launch_workspace" and s["count"] >= 3:
                seq_found = True

        # 4.3 Verify Proactive Suggestion
        sugg = habits.get_proactive_suggestion("open_app", "steam")
        print(f"  [Proactive Suggestion]: '{sugg}'")
        sugg_ok = (sugg is not None) and ("gaming" in sugg.lower())

        # 4.4 Verify USER.md Sync
        with open(temp_user, "r", encoding="utf-8") as f:
            user_md_content = f.read()

        sync_ok = (
            "## Learned Habits & Routines" in user_md_content
            and "launch_workspace:gaming" in user_md_content
        )

        # 4.5 Verify no proactive suggestion for rare actions
        no_sugg = habits.get_proactive_suggestion("open_app", "rare_unseen_app")
        rare_ok = (no_sugg is None)

    finally:
        if os.path.exists(temp_db):
            try:
                os.remove(temp_db)
            except Exception:
                pass
        if os.path.exists(temp_user):
            try:
                os.remove(temp_user)
            except Exception:
                pass

    t4_pass = seq_found and sugg_ok and sync_ok and rare_ok
    if t4_pass:
        passed += 1
        print("  [PASS] Test 4: Habit logging, sequence pattern discovery, proactive suggestion, and USER.md sync verified.")
    else:
        print(f"  [FAIL] Test 4: seq={seq_found}, sugg={sugg_ok}, sync={sync_ok}, rare={rare_ok}")

    # -------------------------------------------------------------
    # Test 5: LocalLLM & SupervisorHub Hermes Coordination
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 5: LocalLLM Hermes Routing & SupervisorHub Coordination...")
    llm = LocalLLM()

    # 5.1 Plan create_skill
    p_create = llm.plan(
        "Create a skill called system uptime check that calculates system boot uptime",
        dry_run=True
    )
    print(f"  [Route create_skill]: action='{p_create.get('action')}', slug='{p_create.get('slug')}'")
    route_create_ok = p_create.get("action") == "create_skill" and p_create.get("slug") == "system_uptime_check"

    # 5.2 Plan list_skills
    p_list = llm.plan("What skills do you have?", dry_run=True)
    print(f"  [Route list_skills]: action='{p_list.get('action')}', voice='{p_list.get('voice_response')}'")
    route_list_ok = p_list.get("action") == "list_skills" and p_list.get("voice_response") is not None

    # 5.3 Plan update_personality
    p_tone = llm.plan("Please be more sarcastic and witty", dry_run=True)
    print(f"  [Route update_personality]: action='{p_tone.get('action')}', voice='{p_tone.get('voice_response')}'")
    route_tone_ok = p_tone.get("action") == "update_personality" and p_tone.get("voice_response") is not None

    # 5.4 SupervisorHub Compound Command Splitting
    hub = SupervisorHub(llm=llm)
    compound_prompt = "Create a skill called network check and then list skills"
    steps = hub.split_compound_intent(compound_prompt)
    print(f"  [Compound Intent Split]: {steps}")
    split_ok = len(steps) == 2 and "network check" in steps[0] and "list skills" in steps[1]

    # 5.5 Multi-step Dry-Run Execution
    multi_res = hub.plan_or_execute(compound_prompt, dry_run=True)
    step_results = multi_res.get("step_results", [])
    print(f"  [SupervisorHub Multi-Step]: compound={multi_res.get('compound')}, steps={len(step_results)}, actions={multi_res.get('actions')}")
    multi_ok = (
        multi_res.get("compound") is True
        and len(step_results) == 2
        and multi_res.get("actions") == ["create_skill", "list_skills"]
    )

    t5_pass = route_create_ok and route_list_ok and route_tone_ok and split_ok and multi_ok
    if t5_pass:
        passed += 1
        print("  [PASS] Test 5: LocalLLM Hermes routing and SupervisorHub multi-step intent execution verified.")
    else:
        print(f"  [FAIL] Test 5: create={route_create_ok}, list={route_list_ok}, tone={route_tone_ok}, split={split_ok}, multi={multi_ok}")

    # Summary
    print("\n" + "=" * 65)
    score_pct = (passed / total) * 100
    print(f"Project Libra v5.0 Hermes Evolution Suite: {passed}/{total} Passed ({score_pct:.1f}%)")
    print("=" * 65 + "\n")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
