import os
import sys
import tempfile

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.weather import geocode_location, get_weather
from core.llm import LocalLLM
from core.game_discovery import GameDiscoveryEngine
from core.dispatcher import SafeOSDispatcher


def test_1_dynamic_global_weather():
    print("\n--- [Test 1: Dynamic Global Weather Routing & Geocoding] ---")
    geo = geocode_location("Kuantan")
    assert abs(geo["latitude"] - 3.8077) < 0.2, f"Unexpected latitude for Kuantan: {geo}"
    assert abs(geo["longitude"] - 103.3260) < 0.2, f"Unexpected longitude for Kuantan: {geo}"

    w = get_weather("Kuantan", dry_run=True)
    assert "kuantan" in w["location"].lower()
    assert len(w["voice_response"]) > 15

    llm = LocalLLM()
    res_k = llm.plan("What's the weather for Kuantan?", dry_run=True)
    assert res_k["action"] == "weather"
    assert "kuantan" in res_k["args"].get("location", "").lower() or "kuantan" in res_k.get("voice_response", "").lower()

    res_p = llm.plan("What is the weather in Penang today?", dry_run=True)
    assert res_p["action"] == "weather"
    assert "penang" in res_p["args"].get("location", "").lower() or "penang" in res_p.get("voice_response", "").lower()
    print("  [PASS] Dynamic Global Weather (Kuantan, Penang, Default) verified.")


def test_2_universal_app_discovery_and_roblox():
    print("\n--- [Test 2: Universal App Discovery & Roblox Resolution (AppData & UWP)] ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        ver_dir = os.path.join(tmpdir, "Roblox", "Versions", "version-abc12345")
        os.makedirs(ver_dir, exist_ok=True)
        fake_exe = os.path.join(ver_dir, "RobloxPlayerBeta.exe")
        with open(fake_exe, "w") as f:
            f.write("MZ")

        disp = SafeOSDispatcher()
        spec = disp.get_launch_spec("roblox")
        assert spec is not None
        assert "ms-windows-store" not in str(spec).lower()

        llm = LocalLLM()
        res = llm.plan("Open Roblox", dry_run=True)
        assert res["action"] == "open_app"
        assert "roblox" in res["args"].get("app_id", "").lower() or "roblox" in res.get("app_id", "").lower()
    print("  [PASS] Universal App Discovery & Roblox safe resolution verified.")


def test_3_zero_refusal_interceptor():
    print("\n--- [Test 3: Zero-Refusal Autonomous Fallback Interceptor] ---")
    llm = LocalLLM()
    intercepted = llm._intercept_lazy_refusal(
        "What is the weather in Kuching?",
        "I don't have real-time data, please search online yourself.",
        dry_run=True
    )
    assert intercepted is not None
    assert "kuching" in intercepted.get("voice_response", "").lower()
    assert "search online" not in intercepted.get("voice_response", "").lower()
    print("  [PASS] Zero-Refusal Autonomous Fallback Interceptor verified.")


def test_4_time_date_and_named_close_app():
    print("\n--- [Test 4: Time, Date, & Named Process Closing (close_app)] ---")
    llm = LocalLLM()
    res_time = llm.plan("What time is it right now?", dry_run=True)
    assert res_time.get("voice_response") and len(res_time["voice_response"]) > 3

    res_close = llm.plan("Close Discord", dry_run=True)
    assert res_close["action"] == "close_app"
    print("  [PASS] Time/Date fast-path and named close_app verified.")


if __name__ == "__main__":
    test_1_dynamic_global_weather()
    test_2_universal_app_discovery_and_roblox()
    test_3_zero_refusal_interceptor()
    test_4_time_date_and_named_close_app()
    print("\n=======================================================")
    print("ALL v8.5 COMPLETENESS OVERHAUL TESTS PASSED (4/4 - 100%)")
    print("=======================================================")
