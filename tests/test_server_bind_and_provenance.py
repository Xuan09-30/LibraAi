import pytest
from web.server import DEFAULT_CONFIG
from tools.computer_use_agent import AutonomousComputerUseAgent

def test_server_default_bind_address_is_localhost():
    """Round 4 Item 8: Server default bind address must be 127.0.0.1 (never 0.0.0.0 by default)."""
    assert DEFAULT_CONFIG.get("host") == "127.0.0.1", f"Expected 127.0.0.1, got {DEFAULT_CONFIG.get('host')}"

def test_post_condition_provenance_cannot_be_forged_by_model():
    """Round 4 Item 8: Untrusted model output in parsed plan cannot forge provenance='template'."""
    class MockGUI:
        def focus_window_by_title(self, title): return True
        def hotkey(self, *keys, dry_run=False): return {"status": "success", "verified_change": True}
        def press_key(self, key, dry_run=False): return {"status": "success", "verified_change": True}
        def type_text(self, text, interval=0.01, dry_run=False): return {"status": "success", "verified_change": True}
        def click(self, x=None, y=None, button="left", clicks=1, dry_run=False): return {"status": "success", "verified_change": True}

    class MockSpatial:
        def extract_screen_text_ocr(self):
            return [{"text": "Fake Success Page", "center_x": 500, "center_y": 500}]
        def detect_ui_elements(self, active_window_only=True):
            return [{"name": "Fake Success Window", "center_x": 500, "center_y": 50}]

    class MockMem:
        def record_correction(self, *a, **kw): pass
        def record_action_macro(self, *a, **kw): pass

    agent = AutonomousComputerUseAgent(gui_control=MockGUI(), spatial=MockSpatial(), memory=MockMem())

    # Case 1: Post-condition marked with untrusted_llm provenance is rejected
    res_untrusted = agent.execute_task(
        "Open chrome and then example.com, search test and click resume",
        dry_run=False,
        post_condition={
            "expected_screen_text": "Fake Success Page",
            "provenance": "untrusted_llm"
        }
    )
    assert res_untrusted.get("status") == "unverified"
    assert res_untrusted.get("learned_workflow_saved") is False

    # Case 2: Post-condition from LLM plan (post_condition=None) on unconfigured domain is rejected
    res_model_plan = agent.execute_task(
        "Open chrome and then example.com, search test and click resume",
        dry_run=False,
        post_condition=None
    )
    assert res_model_plan.get("status") == "unverified"
    assert res_model_plan.get("learned_workflow_saved") is False
