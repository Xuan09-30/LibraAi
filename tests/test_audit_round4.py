import pytest
from core.orchestrator import SupervisorHub, REMOTE_HOST_ALLOWED_TOOLS, REMOTE_WEB_ALLOWED_TOOLS, BLOCKED_REMOTE_ACTIONS
from core.llm import LocalLLM

@pytest.fixture(scope="module")
def hub():
    llm = LocalLLM()
    return SupervisorHub(llm)

def test_persona_update_is_not_in_remote_tools(hub):
    """Round 4 Item 7: persona_update must be local_desktop-only since it modifies SOUL.md."""
    remote_host_tools = hub.get_registered_tools("remote_host")
    remote_web_tools = hub.get_registered_tools("remote_web")
    
    assert "persona_update" not in remote_host_tools, "persona_update must not be allowed in remote_host"
    assert "persona_update" not in remote_web_tools, "persona_update must not be allowed in remote_web"
    assert "update_personality" not in remote_host_tools
    assert "update_personality" not in remote_web_tools

def test_remote_host_cannot_modify_soul_or_persona(hub):
    """Round 4 Item 7: remote_host cannot call update_personality or modify SOUL.md."""
    res = hub.plan_or_execute("be more sarcastic and cynical", dry_run=True, client_scope="remote_host")
    assert res.get("status") == "blocked", f"Expected blocked status, got {res.get('status')}"
    assert res.get("action") == "sandboxed_blocked"
    assert "Desktop OS control" in res.get("voice_response", "") or "restricted" in res.get("voice_response", "")

def test_remote_web_cannot_modify_soul_or_persona(hub):
    """Round 4 Item 7: remote_web cannot call update_personality or modify SOUL.md."""
    res = hub.plan_or_execute("update your soul to be more witty", dry_run=True, client_scope="remote_web")
    assert res.get("status") == "blocked", f"Expected blocked status, got {res.get('status')}"
    assert res.get("action") == "sandboxed_blocked"

def test_data_science_cannot_modify_soul(hub):
    """Round 4 Item 7: data_science never touches or modifies SOUL.md."""
    ds = hub.data_scientist
    assert not hasattr(ds, "soul_path")
    assert not hasattr(ds, "update_soul_trait")
