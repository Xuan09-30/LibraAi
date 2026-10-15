import os
import sys
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.wakeword_booster import WakeWordBooster
from tools.media_controller import VK_MEDIA_NEXT_TRACK, VK_VOLUME_DOWN
from core.llm import LocalLLM


def test_wakeword_booster():
    print("[RUNNING] Test 1: Wake-Word Booster 1280-Sample Slicing, AGC & Follow-Up Window...")
    booster = WakeWordBooster(default_threshold=0.50, vad_assisted_threshold=0.32)

    # 1. Feed three 512-sample chunks (1536 samples total)
    chunk1 = np.ones(512, dtype=np.int16) * 500
    chunk2 = np.ones(512, dtype=np.int16) * 500
    chunk3 = np.ones(512, dtype=np.int16) * 500

    frames1 = booster.process_chunk(chunk1)
    assert len(frames1) == 0, f"Expected 0 frames after 512 samples, got {len(frames1)}"
    assert len(booster.remainder_buffer) == 512, f"Expected 512 in remainder, got {len(booster.remainder_buffer)}"

    frames2 = booster.process_chunk(chunk2)
    assert len(frames2) == 0, f"Expected 0 frames after 1024 samples, got {len(frames2)}"
    assert len(booster.remainder_buffer) == 1024, f"Expected 1024 in remainder, got {len(booster.remainder_buffer)}"

    frames3 = booster.process_chunk(chunk3)
    assert len(frames3) == 1, f"Expected exactly 1 frame after 1536 samples, got {len(frames3)}"
    assert len(frames3[0]) == 1280, f"Expected 1280 samples in emitted frame, got {len(frames3[0])}"
    assert len(booster.remainder_buffer) == 256, f"Expected 256 samples in remainder buffer, got {len(booster.remainder_buffer)}"
    print("  [PASS] 1280-sample frame alignment verified: 1 emitted frame, 256 samples retained in remainder buffer.")

    # 2. Verify Software AGC on quiet speech signal (peak = 3000, rms > 150)
    quiet_frame = np.full(1280, 2000, dtype=np.int16)
    quiet_frame[0] = 3000
    amplified = booster.apply_agc(quiet_frame)
    amp_peak = int(np.max(np.abs(amplified)))
    assert amp_peak > 3000, f"Expected amplified peak > 3000, got {amp_peak}"
    assert np.max(amplified) <= 32767 and np.min(amplified) >= -32768, "AGC output clipped outside int16 bounds"
    print(f"  [PASS] Software AGC verified: quiet signal amplified from peak 3000 to {amp_peak} without clipping.")

    # 3. Verify VAD-assisted adaptive threshold
    assert booster.get_threshold(vad_prob=0.10) == 0.50, "Expected default threshold 0.50 without active VAD"
    assert booster.get_threshold(vad_prob=0.45) == 0.32, "Expected lowered threshold 0.32 with active VAD"
    print("  [PASS] VAD-assisted adaptive thresholding verified (0.50 -> 0.32).")

    # 4. Verify 6-second continuous follow-up window
    booster.set_followup_window(6.0)
    assert booster.is_in_followup_window() is True, "Expected follow-up window to be active"
    booster.clear_followup_window()
    assert booster.is_in_followup_window() is False, "Expected follow-up window to be cleared"
    print("  [PASS] 6.0-second continuous follow-up window verified.")


def test_clipboard_and_media_routes():
    print("\n[RUNNING] Test 2: Clipboard Copilot & Media Controller Routing in Dry-Run...")
    llm = LocalLLM()

    # 1. Clipboard Assist routing
    clip_plan = llm.plan("Explain the error in my clipboard", dry_run=True)
    assert clip_plan.get("action") == "clipboard_assist", f"Expected action 'clipboard_assist', got {clip_plan.get('action')}"
    print(f"  [PASS] 'Explain the error in my clipboard' -> action='{clip_plan.get('action')}'")

    # 2. Skip this track routing & VK_MEDIA_NEXT_TRACK (0xB0)
    skip_plan = llm.plan("Skip this track", dry_run=True)
    assert skip_plan.get("action") == "media_control", f"Expected 'media_control', got {skip_plan.get('action')}"
    assert skip_plan.get("vk_code") == VK_MEDIA_NEXT_TRACK, f"Expected vk_code 0x{VK_MEDIA_NEXT_TRACK:X}, got {skip_plan.get('vk_code')}"
    print(f"  [PASS] 'Skip this track' -> action='media_control', vk_code=0x{skip_plan.get('vk_code'):X}")

    # 3. Lower the volume routing & VK_VOLUME_DOWN (0xAE)
    vol_plan = llm.plan("Lower the volume", dry_run=True)
    assert vol_plan.get("action") == "media_control", f"Expected 'media_control', got {vol_plan.get('action')}"
    assert vol_plan.get("vk_code") == VK_VOLUME_DOWN, f"Expected vk_code 0x{VK_VOLUME_DOWN:X}, got {vol_plan.get('vk_code')}"
    print(f"  [PASS] 'Lower the volume' -> action='media_control', vk_code=0x{vol_plan.get('vk_code'):X}")


def test_briefing_and_workspace_routes():
    print("\n[RUNNING] Test 3: Daily Briefing & Workspace Macro Routing in Dry-Run...")
    llm = LocalLLM()

    # 1. Daily Briefing routing
    briefing_plan = llm.plan("Good morning Libra, give me my briefing", dry_run=True)
    assert briefing_plan.get("action") == "daily_briefing", f"Expected 'daily_briefing', got {briefing_plan.get('action')}"
    voice = briefing_plan.get("voice_response", "")
    assert any(w in voice for w in ["Celsius", "degrees", "forecast", "weather"]), f"Weather missing from briefing: {voice}"
    assert any(w in voice for w in ["reminder", "schedule"]), f"Reminders missing from briefing: {voice}"
    assert any(w in voice for w in ["CPU", "RAM", "GPU", "system"]), f"System telemetry missing from briefing: {voice}"
    print(f"  [PASS] 'Good morning Libra, give me my briefing' -> action='daily_briefing'")
    print(f"         Briefing Synthesis: \"{voice[:120]}...\"")

    # 2. Start coding mode routing
    code_plan = llm.plan("Start coding mode", dry_run=True)
    assert code_plan.get("action") == "launch_workspace", f"Expected 'launch_workspace', got {code_plan.get('action')}"
    assert code_plan.get("mode") == "coding", f"Expected mode 'coding', got {code_plan.get('mode')}"
    assert "Coding workspace active" in code_plan.get("voice_response", "")
    print(f"  [PASS] 'Start coding mode' -> action='launch_workspace', mode='{code_plan.get('mode')}'")


def run_all():
    print("=" * 65)
    print("   LIBRA AI - WAKEWORD BOOSTER & PRODUCTIVITY SUITE TESTS")
    print("=" * 65 + "\n")

    test_wakeword_booster()
    test_clipboard_and_media_routes()
    test_briefing_and_workspace_routes()

    print("\n" + "=" * 65)
    print("Wakeword Booster & Productivity Suite: 3/3 Passed (100.0%)")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    run_all()
