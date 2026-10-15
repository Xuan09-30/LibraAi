import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.places_engine import PlacesDiscoveryEngine
from core.llm import LocalLLM


def run_tests():
    print("\n" + "=" * 65)
    print("   LIBRA AI - AUTONOMOUS PLACES & POI DISCOVERY PIPELINE TESTS")
    print("=" * 65)

    passed = 0
    total = 2

    # -------------------------------------------------------------
    # Test 1: Nominatim Search & Structured POI Parsing
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 1: Nominatim Search & Structured POI Parsing...")
    places_engine = PlacesDiscoveryEngine()
    kepong_coords = (3.2140, 101.6356)

    places = places_engine.search_places("Find bookstores near me", near_coords=kepong_coords, limit=4)
    print(f"  [Discovered Places Count]: {len(places)}")

    all_valid = True
    for idx, p in enumerate(places, 1):
        name = p.get("name")
        coords = p.get("coordinates")
        dist = p.get("distance_km")
        addr = p.get("address")
        print(f"  Option {idx}: '{name}' | Coords: {coords} | Dist: {dist} km | Addr: {addr}")

        if not name or not coords or dist is None:
            all_valid = False
            print(f"  [ERROR] Option {idx} missing essential attributes.")
        if dist > 25.0:
            all_valid = False
            print(f"  [ERROR] Option {idx} distance ({dist} km) exceeds 25.0 km viewbox limit.")

    t1_pass = len(places) >= 2 and all_valid

    if t1_pass:
        passed += 1
        print("  [PASS] Test 1: Nominatim places parsed with coordinates, names, and distance <= 25.0 km.")
    else:
        print("  [FAIL] Test 1: Nominatim parsing failed or returned insufficient places.")

    # -------------------------------------------------------------
    # Test 2: Search to Comparison End-to-End Execution
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 2: Search to Comparison End-to-End Execution...")
    llm = LocalLLM()

    # Verify dry_run isolation
    dry_plan = llm.plan("Find bookstores near me", dry_run=True)
    assert dry_plan.get("action") == "places_search", f"Expected places_search, got {dry_plan.get('action')}"
    print(f"  [Dry Run Check]: action='{dry_plan.get('action')}', place_type='{dry_plan.get('place_type')}' (isolated)")

    # Step A: Discovers places and updates session candidate stack
    print("  [Step A] Executing: 'Find bookstores near me' (live)...")
    res_a = llm.plan_and_respond("Find bookstores near me")
    action_a = res_a.get("action")
    candidates_count = len(llm.session_mgr.candidates)
    voice_a = res_a.get("voice_response", "")

    print(f"  [Step A Action]: {action_a}")
    print(f"  [Step A Candidates Ingested]: {candidates_count}")
    print(f"  [Step A Voice Response]: \"{voice_a}\"")

    step_a_ok = (
        action_a == "places_search"
        and candidates_count >= 2
        and len(voice_a) > 10
    )

    # Step B: Follow-up comparison resolving ordinals from candidate stack
    print("\n  [Step B] Executing follow-up: 'Which is better between the first and second option?'...")
    res_b = llm.plan_and_respond("Which is better between the first and second option?")
    action_b = res_b.get("action")
    compared_candidates = res_b.get("candidates", [])
    voice_b = res_b.get("voice_response", "")

    print(f"  [Step B Action]: {action_b}")
    print(f"  [Step B Compared]: {[c.get('name') for c in compared_candidates]}")
    print(f"  [Step B Voice Response]: \"{voice_b}\"")

    resp_b_lower = voice_b.lower()
    first_name = compared_candidates[0].get("name", "").lower() if len(compared_candidates) >= 1 else ""
    second_name = compared_candidates[1].get("name", "").lower() if len(compared_candidates) >= 2 else ""

    # Check that both places or relevant comparative tokens are in the response
    step_b_ok = (
        action_b == "compare_candidates"
        and len(compared_candidates) == 2
        and any(w in resp_b_lower for w in ["closer", "better", "km", "distance", "recommend", "convenien", "rating"])
    )

    t2_pass = step_a_ok and step_b_ok

    if t2_pass:
        passed += 1
        print("  [PASS] Test 2: End-to-end place search, candidate ingestion, and comparison verified.")
    else:
        print(f"  [FAIL] Test 2: Step A ok={step_a_ok}, Step B ok={step_b_ok}")

    # Summary
    print("\n" + "=" * 65)
    score_pct = (passed / total) * 100
    print(f"Places Discovery Suite Score: {passed}/{total} Passed ({score_pct:.1f}%)")
    print("=" * 65 + "\n")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
