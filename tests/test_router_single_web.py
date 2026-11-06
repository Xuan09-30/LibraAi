import pytest
from fastapi.testclient import TestClient
from web.server import create_app

def test_how_you_feeling_today_e2e_api_chat():
    """Round 4 Item 4: Web path must use single router and not trigger web search for 'how you feeling today?'."""
    app = create_app()
    client = TestClient(app)
    
    # Non-streaming request with host token (client_scope derived server-side)
    resp = client.post(
        "/api/chat",
        json={"prompt": "how you feeling today?", "session_id": "test_chitchat"},
        headers={"Authorization": "Bearer libra_access_token_phase10_secure"}
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.text

    # Verify no web search tool or citations were emitted
    assert "web_search" not in body
    assert "Sources:" not in body
    assert "Greenwich Time" not in body
    assert "note.com" not in body

def test_how_you_feeling_today_e2e_api_chat_streaming():
    """Round 4 Item 4: Streaming web path must use single router and never treat 'how you feeling today?' as research/tool query."""
    app = create_app()
    client = TestClient(app)
    
    with client.stream(
        "POST",
        "/api/chat?stream=true",
        json={"prompt": "how you feeling today?", "session_id": "test_chitchat_stream"},
        headers={"Authorization": "Bearer libra_access_token_phase10_secure"}
    ) as resp:
        assert resp.status_code == 200
        content = resp.read().decode("utf-8")
        # Must not trigger tool/research self-correction or web intelligence
        assert "Autonomous Tool & Web Intelligence" not in content
        assert "Dispatched 'research'" not in content
        assert "web_search" not in content
        assert "Sources:" not in content
        assert "Greenwich Time" not in content
        assert "note.com" not in content
