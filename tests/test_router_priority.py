import pytest
from core.llm import LocalLLM

@pytest.fixture(scope="module")
def llm():
    return LocalLLM()

def test_regression_arsenal_vs_chelsea_live_score(llm):
    """Round 4 Item 5: Real-time signals take priority over compare shortcut rules."""
    res = llm.plan("arsenal vs chelsea live score", dry_run=True)
    assert res.get("action") == "web_search", f"Expected web_search, got {res.get('action')}"

def test_regression_good_morning_nba_game_score(llm):
    """Round 4 Item 5: Real-time signals take priority over daily_briefing shortcut rules."""
    res = llm.plan("good morning libra how was ur day whats the score of the nba game", dry_run=True)
    assert res.get("action") == "web_search", f"Expected web_search, got {res.get('action')}"
