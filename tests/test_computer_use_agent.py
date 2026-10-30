import os
import sys
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.computer_use_agent import AutonomousComputerUseAgent
from core.vram_governor import get_vram_governor


def test_computer_use_prompt_detection():
    # Multi-step computer use requests
    p1 = "Open my chrome and then cinejoy.pk, find and search hannibal and click resume"
    p2 = "open chrome and then youtube.com, search for lofi beats and click play"
    p3 = "go to cinejoy.pk then search breaking bad and click resume"

    assert AutonomousComputerUseAgent.is_computer_use_prompt(p1) is True
    assert AutonomousComputerUseAgent.is_computer_use_prompt(p2) is True
    assert AutonomousComputerUseAgent.is_computer_use_prompt(p3) is True

    # Standard simple chat or single app queries should not trigger computer-use agent
    assert AutonomousComputerUseAgent.is_computer_use_prompt("What is the weather today?") is False
    assert AutonomousComputerUseAgent.is_computer_use_prompt("open notepad") is False
    assert AutonomousComputerUseAgent.is_computer_use_prompt("search for LeBron James on Google") is False


def test_parse_navigation_goal():
    agent = AutonomousComputerUseAgent(gui_control=None, spatial=None)
    goal = agent.parse_navigation_goal("Open my chrome and then cinejoy.pk, find and search hannibal and click resume")

    assert goal["browser"] == "chrome"
    assert goal["domain"] == "cinejoy.pk"
    assert goal["search_query"] == "hannibal"
    assert goal["click_target"] == "resume"


def test_popup_guard_and_step_execution():
    agent = AutonomousComputerUseAgent(gui_control=None, spatial=None)
    res = agent.execute_task("Open my chrome and then cinejoy.pk, find and search hannibal and click resume", dry_run=True)

    assert res["status"] == "success"
    assert res["action"] == "computer_use_agent"
    assert res["domain"] == "cinejoy.pk"
    assert res["search_query"] == "hannibal"
    assert res["click_target"] == "resume"

    trace = res["agent_trace"]
    assert len(trace) >= 12

    # Verify structured fields in steps
    step1 = trace[0]
    assert step1["step"] == 1
    assert step1["action"] == "click"
    assert "thought" in step1
    assert "x" in step1 and "y" in step1

    # Verify key actions
    actions = [s["action"] for s in trace]
    assert "click" in actions
    assert "press" in actions
    assert "type" in actions
    assert "done" in actions
    assert trace[-1]["action"] == "done"


def test_anticheat_guard_prevents_automation(monkeypatch):
    gov = get_vram_governor()
    monkeypatch.setattr(gov, "is_gaming_lite_mode", lambda: True)

    agent = AutonomousComputerUseAgent(gui_control=None, spatial=None)
    res = agent.execute_task("Open my chrome and then cinejoy.pk, find and search hannibal and click resume", dry_run=False)

    assert res["status"] == "paused_for_anticheat"
    assert res["agent_trace"][0]["action"] == "aborted_for_anticheat"
    assert "Anti-Cheat Safe Mode" in res["voice_response"]
