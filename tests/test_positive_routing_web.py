import pytest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from web.server import create_app, load_web_config
from core.orchestrator import SupervisorHub
from core.llm import LocalLLM
from core.memory import MemoryCore


@pytest.fixture
def web_test_client(tmp_path):
    db_file = str(tmp_path / "test_positive_routing.db")
    memory = MemoryCore(db_path=db_file)
    llm = LocalLLM()
    llm.memory = memory
    supervisor = SupervisorHub(llm)
    app = create_app(hub=supervisor, config_path="config.json")
    client = TestClient(app)
    cfg = load_web_config("config.json")
    token = cfg.get("access_token", "libra_access_token_phase10_secure")
    client.headers = {"Authorization": f"Bearer {token}", "Cookie": f"libra_auth={token}"}
    return client, supervisor


def test_bitcoin_price_positive_routing_triggers_web_search(web_test_client):
    """
    Round 5 Item 2:
    Positive routing test through /api/chat:
    'what's the bitcoin price right now' must trigger web_search and return citations.
    """
    client, supervisor = web_test_client

    # Mock research execution so test is hermetic, fast, and deterministic
    mock_research_data = {
        "status": "success",
        "voice_response": "Bitcoin is currently trading at approximately $68,450 USD according to real-time market data.",
        "sources": [
            {"name": "CoinDesk", "title": "Bitcoin Price Index", "url": "https://www.coindesk.com/price/bitcoin"},
            {"name": "CoinMarketCap", "title": "Bitcoin Price Today", "url": "https://coinmarketcap.com/currencies/bitcoin"}
        ]
    }

    with patch.object(supervisor.llm, "execute_research", return_value=mock_research_data) as mock_exec:
        resp = client.post("/api/chat", json={
            "prompt": "what's the bitcoin price right now",
            "client_scope": "remote_web"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("action") == "web_search"
        assert "CoinDesk" in data.get("reply_text", "") or len(data.get("sources", [])) >= 1
        assert "68,450" in data.get("reply_text", "")
        # Verify citations formatted in markdown
        assert "*Sources:" in data.get("reply_text", "")
        assert "[CoinDesk](https://www.coindesk.com/price/bitcoin)" in data.get("reply_text", "")
        mock_exec.assert_called_once()


def test_weather_in_tokyo_positive_routing_calls_weather_tool(web_test_client):
    """
    Round 5 Item 2:
    'weather in Tokyo' must still call the weather tool and return Tokyo weather.
    """
    client, supervisor = web_test_client

    resp = client.post("/api/chat", json={
        "prompt": "weather in Tokyo",
        "client_scope": "remote_web"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("action") == "weather"
    assert "Tokyo" in data.get("reply_text", "")
    assert "degrees" in data.get("reply_text", "").lower() or "celsius" in data.get("reply_text", "").lower()


def test_bitcoin_streaming_triggers_web_search_and_citations(web_test_client):
    """
    Round 5 Item 2:
    Confirm streaming /api/chat?stream=true also triggers web_search with citations.
    """
    client, supervisor = web_test_client

    mock_research_data = {
        "status": "success",
        "voice_response": "Bitcoin is hovering near $68,000 USD.",
        "sources": [
            {"name": "CoinDesk", "title": "Bitcoin Index", "url": "https://www.coindesk.com/price/bitcoin"}
        ]
    }

    with patch.object(supervisor.llm, "execute_research", return_value=mock_research_data):
        with client.stream("POST", "/api/chat?stream=true", json={
            "prompt": "what's the bitcoin price right now",
            "client_scope": "remote_web"
        }) as resp:
            assert resp.status_code == 200
            events = []
            for line in resp.iter_lines():
                if line and line.startswith("data: "):
                    events.append(json.loads(line[6:]))

            done_events = [e for e in events if e.get("type") == "done"]
            assert len(done_events) >= 1
            reply_text = done_events[0].get("reply_text", "")
            assert "Bitcoin" in reply_text
            assert "*Sources:" in reply_text
            assert "CoinDesk" in reply_text
