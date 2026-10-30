import pytest
import json
import asyncio
from httpx import AsyncClient, ASGITransport
from web.server import create_app
from core.orchestrator import SupervisorHub
from core.llm import LocalLLM
from core.memory import MemoryCore


@pytest.fixture
def test_app(tmp_path):
    db_file = str(tmp_path / "test_server_mem.db")
    memory = MemoryCore(db_path=db_file)
    llm = LocalLLM()
    llm.memory = memory
    supervisor = SupervisorHub(llm)
    app = create_app(hub=supervisor, config_path="config.json")
    return app, supervisor, memory


@pytest.mark.anyio
async def test_server_streaming_chat_multi_turn_and_creator(test_app):
    app, supervisor, memory = test_app
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Mock auth header for host
        headers = {"X-Libra-Email": "chenxuanchuah@gmail.com"}

        # 1. Creator Query
        resp1 = await client.post(
            "/api/chat?stream=true",
            json={"prompt": "Who is your creator?", "session_id": "test_sess_1", "synthesize_audio": False},
            headers=headers
        )
        assert resp1.status_code == 200
        text1 = resp1.text
        assert "Chuah Chen Xuan" in text1 or "Chen Xuan" in text1

        # 2. Add prior turn to memory about Anthony Edwards
        memory.add_session_message(
            session_id="test_sess_1",
            role="user",
            content="Tell me about Anthony Edwards the basketball player."
        )
        memory.add_session_message(
            session_id="test_sess_1",
            role="assistant",
            content="Anthony Edwards is an NBA All-Star shooting guard for the Minnesota Timberwolves."
        )

        # 3. Follow-up query about injuries with pronoun 'he'
        resp2 = await client.post(
            "/api/chat?stream=true",
            json={"prompt": "i mean today i saw he got injuries, is that true?", "session_id": "test_sess_1", "synthesize_audio": False},
            headers=headers
        )
        assert resp2.status_code == 200
        text2 = resp2.text

        # Verify that it did not lazily refuse with 'I don't have access to external information'
        assert "don't have access to external" not in text2.lower()
        assert "no record of injuries" not in text2.lower()

        # Check that session messages are recorded in memory
        recent = memory.get_session_messages("test_sess_1", limit=10)
        assert len(recent) >= 4
