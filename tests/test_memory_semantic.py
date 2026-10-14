import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.memory import SemanticMemory


def run_semantic_memory_tests():
    print("\n" + "=" * 60)
    print("   LIBRA AI - SEMANTIC MEMORY & SQLITE-VEC BENCHMARKS")
    print("=" * 60)

    # Use a dedicated isolated test database to prevent test pollution
    test_db = "assets/test_semantic_memory.db"
    test_db_full_path = os.path.join(PROJECT_ROOT, test_db)
    if os.path.exists(test_db_full_path):
        try:
            os.remove(test_db_full_path)
        except Exception:
            pass

    memory = SemanticMemory(db_filename=test_db)
    passed = 0
    total = 3

    # -------------------------------------------------------------
    # Test 1: Semantic Match without Keyword Overlap
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 1: Semantic Match without Keyword Overlap...")
    fact_text = "The user drives a silver Honda Civic."
    fid = memory.remember_fact(fact_text)
    print(f"  [Stored Fact]: ID={fid}, Content='{fact_text}'")

    query = "What vehicle do I own?"
    results = memory.recall_relevant(query, limit=3, distance_threshold=0.75)
    print(f"  [Query]: '{query}' -> Retrieved {len(results)} matches:")
    for idx, r in enumerate(results, 1):
        print(f"    {idx}. '{r['content']}' (distance: {r['distance']:.4f})")

    retrieved_contents = [r["content"] for r in results]
    test1_pass = any("Honda Civic" in c for c in retrieved_contents)

    if test1_pass:
        passed += 1
        print("  [PASS] Test 1: Semantic match verified. Retrieved 'Honda Civic' without keyword overlap.")
    else:
        print(f"  [FAIL] Test 1: Failed to retrieve 'Honda Civic' for query '{query}'")

    # -------------------------------------------------------------
    # Test 2: Targeted Forget
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 2: Targeted Forget...")
    forget_query = "my vehicle"
    purged_record = memory.forget_fact(forget_query, distance_threshold=0.75)
    print(f"  [Forget Call]: query='{forget_query}' -> Purged='{purged_record}'")

    # Verify Civic cannot be recalled
    recalled_after_forget = memory.recall_relevant(query, limit=3, distance_threshold=0.75)
    print(f"  [Verify Post-Forget Recall]: Results count={len(recalled_after_forget)}")

    test2_pass = (
        purged_record is not None
        and "Honda Civic" in purged_record
        and not any("Honda Civic" in r["content"] for r in recalled_after_forget)
    )

    if test2_pass:
        passed += 1
        print("  [PASS] Test 2: Targeted forget verified. Record was successfully purged from both tables.")
    else:
        print(f"  [FAIL] Test 2: Forget failed! Purged='{purged_record}', Post-recall={recalled_after_forget}")

    # -------------------------------------------------------------
    # Test 3: Profile Dump
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 3: Profile Dump...")
    fact_a = "User prefers dark mode UI and high-contrast text."
    fact_b = "User lives in Kepong, Kuala Lumpur."
    memory.remember_fact(fact_a)
    memory.remember_fact(fact_b)

    profile = memory.get_profile_summary(limit=10)
    print(f"  [Profile Summary ({len(profile)} items)]:")
    for item in profile:
        print(f"    - {item}")

    test3_pass = (
        any("dark mode" in p for p in profile)
        and any("Kepong" in p for p in profile)
    )

    if test3_pass:
        passed += 1
        print("  [PASS] Test 3: Profile dump verified. Stored facts successfully returned by get_profile_summary().")
    else:
        print(f"  [FAIL] Test 3: Profile dump failed to contain expected facts.")

    # Clean up test database
    if os.path.exists(test_db_full_path):
        try:
            os.remove(test_db_full_path)
        except Exception:
            pass

    # Summary
    print("\n" + "=" * 60)
    score_pct = (passed / total) * 100
    print(f"Semantic Memory Suite Score: {passed}/{total} Passed ({score_pct:.1f}%)")
    print("=" * 60 + "\n")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_semantic_memory_tests()
