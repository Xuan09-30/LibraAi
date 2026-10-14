import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.dispatcher import SafeOSDispatcher
from core.text_cleaner import normalize_for_tts


def run_dispatcher_and_normalizer_tests():
    print("\n" + "=" * 60)
    print("   LIBRA AI - SAFE OS DISPATCHER & PRE-TTS NORMALIZER TESTS")
    print("=" * 60)

    passed = 0
    total = 2
    dispatcher = SafeOSDispatcher()

    # -------------------------------------------------------------
    # Test 1: Safe OS Dispatcher Boundaries
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 1: Safe OS Dispatcher Boundaries...")
    # 1. Valorant spec check
    val_spec = dispatcher.get_launch_spec("valorant")
    print(f"  [Valorant Launch Spec]: {val_spec}")
    val_valid = (
        val_spec is not None
        and val_spec.get("args") == ["--launch-product=valorant", "--launch-patchline=live"]
        and val_spec.get("keystrokes_injected") is False
        and "RiotClientServices.exe" in val_spec.get("executable", "")
    )

    # 2. Steam spec check
    steam_spec = dispatcher.get_launch_spec("steam")
    print(f"  [Steam Launch Spec]: {steam_spec}")
    steam_valid = (
        steam_spec is not None
        and steam_spec.get("uri") == "steam://open/main"
        and steam_spec.get("keystrokes_injected") is False
    )

    # 3. Unallowlisted app rejection check
    malicious_res = dispatcher.launch_app("malicious_app.exe", dry_run=True)
    print(f"  [Unallowlisted App Test]: 'malicious_app.exe' -> {malicious_res}")
    malicious_rejected = (
        malicious_res[0] is False
        and "not in the approved safety allowlist" in malicious_res[1]
    )

    # 4. Destructive action shutdown confirmation check
    shutdown_unconfirmed = dispatcher.request_shutdown(confirmed=False, dry_run=True)
    print(f"  [Shutdown Unconfirmed Test]: {shutdown_unconfirmed}")
    shutdown_guarded = (
        shutdown_unconfirmed[0] is False
        and "Confirmation required: Are you sure you want to shut down your PC?" in shutdown_unconfirmed[1]
    )

    shutdown_confirmed = dispatcher.request_shutdown(confirmed=True, dry_run=True)
    print(f"  [Shutdown Confirmed Test]: {shutdown_confirmed}")
    shutdown_confirmed_valid = (shutdown_confirmed[0] is True)

    test1_pass = (
        val_valid
        and steam_valid
        and malicious_rejected
        and shutdown_guarded
        and shutdown_confirmed_valid
    )

    if test1_pass:
        passed += 1
        print("  [PASS] Test 1: Safe OS Dispatcher verified. Allowlisted process arguments exact, keystrokes absent, unallowlisted apps rejected, and shutdown guarded.")
    else:
        print(f"  [FAIL] Test 1: Safe OS Dispatcher failed boundaries check (val={val_valid}, steam={steam_valid}, mal_rej={malicious_rejected}, shut_guard={shutdown_guarded})")

    # -------------------------------------------------------------
    # Test 2: Text Normalizer Conversions
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 2: Text Normalizer Conversions...")
    raw_input = "The temperature in KL is 33°C with 85% humidity. Check https://weather.com for RM50."
    normalized = normalize_for_tts(raw_input)
    print(f"  [Input]:  \"{raw_input}\"")
    print(f"  [Output]: \"{normalized}\"")

    expected_fragments = [
        "33 degrees Celsius",
        "85 percent",
        "link",
        "50 ringgit"
    ]

    has_fragments = all(frag.lower() in normalized.lower() for frag in expected_fragments)
    forbidden_symbols = ["°", "%", "RM", "http", "$", "&", "@", "#", "*", "`"]
    no_raw_symbols = not any(sym in normalized for sym in forbidden_symbols)

    test2_pass = has_fragments and no_raw_symbols

    if test2_pass:
        passed += 1
        print("  [PASS] Test 2: Text normalizer conversions verified. Expanded temperature, percent, link, and currency with zero raw symbols or markdown artifacts.")
    else:
        print(f"  [FAIL] Test 2: Normalizer output failed criteria! has_fragments={has_fragments}, no_raw_symbols={no_raw_symbols}")

    # Summary
    print("\n" + "=" * 60)
    score_pct = (passed / total) * 100
    print(f"Dispatcher & Normalizer Suite Score: {passed}/{total} Passed ({score_pct:.1f}%)")
    print("=" * 60 + "\n")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_dispatcher_and_normalizer_tests()
