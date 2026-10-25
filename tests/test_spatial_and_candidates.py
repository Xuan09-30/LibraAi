import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.spatial import SpatialGroundingEngine
from core.session import SessionManager
from core.llm import LocalLLM

MOCK_BOOKSTORES = [
    {
        "name": "Kinokuniya KLCC",
        "rating": 4.8,
        "address": "Suria KLCC, Kuala Lumpur",
        "coordinates": (3.1578, 101.7123),
        "snippet": "Massive flagship collection of Japanese manga, English bestsellers, and imported stationery."
    },
    {
        "name": "Tsutaya Pavilion Bukit Jalil",
        "rating": 4.7,
        "address": "Pavilion Bukit Jalil, Kuala Lumpur",
        "coordinates": (3.0514, 101.6698),
        "snippet": "Aesthetic lifestyle concept bookstore with artisanal cafe, curated art books, and lounge areas."
    },
    {
        "name": "MPH Mid Valley",
        "rating": 4.2,
        "address": "Mid Valley Megamall, Kuala Lumpur",
        "coordinates": (3.1177, 101.6775),
        "snippet": "Classic family bookstore with educational revision materials, fiction, and gift items."
    },
    {
        "name": "Popular Sunway Pyramid",
        "rating": 4.1,
        "address": "Sunway Pyramid, Petaling Jaya",
        "coordinates": (3.0733, 101.6074),
        "snippet": "Affordable Chinese literature, stationery, assessment books, and electronic accessories."
    }
]


def run_tests():
    print("\n" + "=" * 65)
    print("   LIBRA AI - SPATIAL GROUNDING & CANDIDATE COMPARISON TESTS")
    print("=" * 65)

    passed = 0
    total = 3

    # -------------------------------------------------------------
    # Test 1: Haversine Precision & Spatial Anchor Grounding
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 1: Haversine Precision & Spatial Anchoring...")
    spatial = SpatialGroundingEngine()

    kepong_coords = (3.2140, 101.6356)
    klcc_coords = (3.1578, 101.7123)

    dist_km = spatial.haversine_distance(kepong_coords, klcc_coords)
    dist_home = spatial.distance_from_home(klcc_coords[0], klcc_coords[1])
    anchor_res = spatial.resolve_anchor("Find the best bookstores near me or around here")

    print(f"  [Haversine Kepong -> KLCC]: {dist_km:.2f} km")
    print(f"  [Distance from Home Anchor]: {dist_home} km")
    print(f"  [Spatial Anchor Resolution]: {anchor_res.get('neighborhood')}, {anchor_res.get('city')} (detected={anchor_res.get('detected')})")

    t1_pass = (
        10.0 <= dist_km <= 11.5
        and dist_home in [10.1, 10.6]
        and anchor_res.get("detected") is True
        and anchor_res.get("neighborhood") in ["Kepong", "Taman Bukit Maluri"]
    )

    if t1_pass:
        passed += 1
        print("  [PASS] Test 1: Haversine precision (~10.56 km) and anchor resolution verified.")
    else:
        print(f"  [FAIL] Test 1: Distance {dist_km:.2f} or anchor resolution {anchor_res} out of expected range!")

    # -------------------------------------------------------------
    # Test 2: Ordinal Extraction & Candidate Indexing
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 2: Candidate Stack & Natural Language Ordinals...")
    session_mgr = SessionManager()
    session_mgr.update_candidates(MOCK_BOOKSTORES)

    # Query A: "compare the first and fourth"
    res_a = session_mgr.resolve_ordinals("compare the first and fourth")
    names_a = [c["name"] for c in res_a]
    print(f"  [Query 'first and fourth']: {names_a}")

    # Query B: "which is better between number 2 and the last one"
    res_b = session_mgr.resolve_ordinals("which is better between number 2 and the last one")
    names_b = [c["name"] for c in res_b]
    print(f"  [Query 'number 2 and the last one']: {names_b}")

    # Query C: "compare both"
    res_c = session_mgr.resolve_ordinals("compare both")
    names_c = [c["name"] for c in res_c]
    print(f"  [Query 'both']: {names_c}")

    t2_pass = (
        names_a == ["Kinokuniya KLCC", "Popular Sunway Pyramid"]
        and names_b == ["Tsutaya Pavilion Bukit Jalil", "Popular Sunway Pyramid"]
        and names_c == ["Kinokuniya KLCC", "Tsutaya Pavilion Bukit Jalil"]
    )

    if t2_pass:
        passed += 1
        print("  [PASS] Test 2: Natural ordinals (first, fourth, number 2, last, both) correctly resolved.")
    else:
        print(f"  [FAIL] Test 2: Ordinal extraction mismatch: A={names_a}, B={names_b}, C={names_c}")

    # -------------------------------------------------------------
    # Test 3: Side-by-Side Comparison Synthesis
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 3: Side-by-Side Comparison Synthesis (dry_run=False)...")
    llm = LocalLLM()
    llm.session_mgr.update_candidates(MOCK_BOOKSTORES)

    plan_res = llm.plan("Which is better between the first and second option?", dry_run=False)
    voice_resp = plan_res.get("voice_response", "")
    print(f"  [Action]: {plan_res.get('action')}")
    print(f"  [Candidates Compared]: {[c['name'] for c in plan_res.get('candidates', [])]}")
    print(f"  [Voice Response]: \"{voice_resp}\"")

    resp_lower = voice_resp.lower()
    t3_pass = (
        plan_res.get("action") == "compare_candidates"
        and len(plan_res.get("candidates", [])) == 2
        and "kinokuniya" in resp_lower
        and "tsutaya" in resp_lower
        and any(attr in resp_lower for attr in ["km", "rating", "star", "distance", "away"])
    )

    if t3_pass:
        passed += 1
        print("  [PASS] Test 3: Side-by-side comparison synthesized with comparative attributes and recommendations.")
    else:
        print(f"  [FAIL] Test 3: Synthesis output did not contain expected comparative tokens: {voice_resp}")

    # Summary
    print("\n" + "=" * 65)
    score_pct = (passed / total) * 100
    print(f"Spatial & Candidate Suite Score: {passed}/{total} Passed ({score_pct:.1f}%)")
    print("=" * 65 + "\n")

    if passed < total:
        sys.exit(1)



def test_suite():
    run_tests()

if __name__ == "__main__":
    run_tests()
