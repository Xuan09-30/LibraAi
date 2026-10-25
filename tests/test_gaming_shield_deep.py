import os
import sys
import re
import numpy as np
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.wakeword_booster import WakeWordBooster
from core.vram_governor import VRAMAutoGovernor
from tools.window_context import ActiveWindowEngine


def test_gaming_shield_wakeword_thresholds_and_agc():
    booster = WakeWordBooster(default_threshold=0.58, vad_assisted_threshold=0.46, gaming_threshold=0.78)

    # 1. Desktop Mode Thresholds
    booster.set_game_mode(False)
    assert booster.get_threshold(vad_prob=0.1) == 0.58
    assert booster.get_threshold(vad_prob=0.4) == 0.46

    # 2. Gaming Mode Threshold
    booster.set_game_mode(True)
    assert booster.get_threshold(vad_prob=0.1) == 0.78
    assert booster.get_threshold(vad_prob=0.9) == 0.78  # VAD does not lower gaming threshold

    # 3. Software AGC bypass in gaming mode
    quiet_frame = np.full(1280, 2000, dtype=np.int16)
    quiet_frame[0] = 3000

    booster.set_game_mode(False)
    amplified_desktop = booster.apply_agc(quiet_frame.copy())
    assert np.max(np.abs(amplified_desktop)) > 3000, "Expected AGC amplification on desktop"

    booster.set_game_mode(True)
    amplified_gaming = booster.apply_agc(quiet_frame.copy())
    assert np.array_equal(amplified_gaming, quiet_frame), "Expected raw audio without AGC gain in gaming mode"


def test_gaming_shield_consecutive_hit_verification():
    booster = WakeWordBooster(default_threshold=0.58, vad_assisted_threshold=0.46, gaming_threshold=0.78)
    booster.set_game_mode(True)

    # Transient phonetic spike from normal speech (0.50 - 0.75) -> REJECTED
    assert not booster.is_wakeword_triggered(score=0.62)
    assert not booster.is_wakeword_triggered(score=0.74)

    # Single hit at 0.80 -> REJECTED (needs 2 consecutive hits)
    assert not booster.is_wakeword_triggered(score=0.80)
    # Second consecutive hit at 0.81 -> ACCEPTED
    assert booster.is_wakeword_triggered(score=0.81)

    # Broken sequence (hit then miss then hit) -> REJECTED
    assert not booster.is_wakeword_triggered(score=0.80)
    assert not booster.is_wakeword_triggered(score=0.40)  # Reset
    assert not booster.is_wakeword_triggered(score=0.80)  # Only 1st hit again

    # Definitive high spike (>= 0.88) -> ACCEPTED immediately
    assert booster.is_wakeword_triggered(score=0.91)


def test_gaming_shield_post_stt_address_filter():
    def gaming_shield_filter(user_text: str, is_game_active: bool, in_followup: bool) -> bool:
        """Simulates the Gaming Shield post-STT check in gui.py."""
        if is_game_active and not in_followup:
            text_lower = user_text.lower()
            has_wake_address = bool(re.search(r"\b(?:hey\s+)?libra\b", text_lower)) or "libra" in text_lower
            return has_wake_address
        return True

    # In-game ambient chatter / callouts -> MUST BE DISCARDED (return False)
    assert not gaming_shield_filter("push B site", is_game_active=True, in_followup=False)
    assert not gaming_shield_filter("can you drop me a heal", is_game_active=True, in_followup=False)
    assert not gaming_shield_filter("bro look at my ping", is_game_active=True, in_followup=False)
    assert not gaming_shield_filter("nice shot man", is_game_active=True, in_followup=False)
    assert not gaming_shield_filter("lib", is_game_active=True, in_followup=False)

    # Genuine user commands addressing Libra in-game -> MUST BE ALLOWED (return True)
    assert gaming_shield_filter("Hey Libra what time is it", is_game_active=True, in_followup=False)
    assert gaming_shield_filter("Libra set a timer for 10 minutes", is_game_active=True, in_followup=False)
    assert gaming_shield_filter("libra lower volume", is_game_active=True, in_followup=False)
    assert gaming_shield_filter("hey libra", is_game_active=True, in_followup=False)

    # When NOT in game -> all spoken inputs pass through
    assert gaming_shield_filter("what is the weather today", is_game_active=False, in_followup=False)


def test_game_process_recognition():
    gov = VRAMAutoGovernor()
    window_eng = ActiveWindowEngine()

    test_games = [
        "valorant-win64-shipping.exe",
        "overwatch 2.exe",
        "genshinimpact.exe",
        "starrail.exe",
        "minecraft.exe",
        "eldenring.exe",
        "cyberpunk2077.exe",
        "cs2.exe",
        "dota2.exe",
        "league of legends.exe"
    ]

    for game in test_games:
        assert game in gov.TARGET_GAMES, f"{game} should be in VRAMAutoGovernor.TARGET_GAMES"

    # Auto-categorization of *-shipping.exe and containing 'game'
    info_shipping = {"process_name": "UnrealGame-Win64-Shipping.exe", "window_title": "Game Window", "app_category": "general"}
    window_eng._enrich_parsed_metadata(info_shipping)
    assert info_shipping["app_category"] == "game"

    info_game = {"process_name": "mygame.exe", "window_title": "Cool Game", "app_category": "general"}
    window_eng._enrich_parsed_metadata(info_game)
    assert info_game["app_category"] == "game"


def test_valorant_recognition_and_audio_ducker_shield():
    from core.audio_capture import AudioDucker

    assert AudioDucker._is_game_process("VALORANT-Win64-Shipping.exe")
    assert AudioDucker._is_game_process("valorant.exe")
    assert AudioDucker._is_game_process("cs2.exe")
    assert not AudioDucker._is_game_process("chrome.exe")

    window_eng = ActiveWindowEngine()
    window_eng.set_mock_window({
        "hwnd": 1181278,
        "pid": 14636,
        "process_name": "VALORANT-Win64-Shipping.exe",
        "app_label": "Valorant",
        "app_category": "game",
        "window_title": "VALORANT",
        "memory_mb": 3004.0,
    })
    res = window_eng.handle_contextual_query("Do you know what game I am playing?")
    assert "Valorant" in res["voice_response"]
    assert "League of Legends" not in res["voice_response"]
    window_eng.set_mock_window(None)


def test_phase12_web_gaming_and_export_endpoints():
    from fastapi.testclient import TestClient
    from web.server import create_app, load_web_config

    cfg = load_web_config()
    token = cfg.get("access_token", "libra_access_token_phase10_secure")
    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Gaming status endpoint
    r_status = client.get("/api/gaming/status", headers=headers)
    assert r_status.status_code == 200
    data = r_status.json()
    assert data["status"] == "online"
    assert "gaming_shield_active" in data
    assert "audio_sessions" in data

    # 2. Heal audio endpoint
    r_heal = client.post("/api/gaming/heal-audio", headers=headers)
    assert r_heal.status_code == 200
    assert r_heal.json()["status"] == "success"

    # 3. Session Markdown export endpoint
    r_new = client.post("/api/sessions/new", json={"title": "Phase 12 Export Test"}, headers=headers)
    assert r_new.status_code == 200
    sid = r_new.json()["session_id"]

    r_exp = client.get(f"/api/sessions/{sid}/export", headers=headers)
    assert r_exp.status_code == 200
    assert "# Project Libra // Phase 12 Export Test" in r_exp.text


