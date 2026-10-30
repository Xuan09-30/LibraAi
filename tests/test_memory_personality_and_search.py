import os
import pytest
from core.memory import MemoryCore
from core.llm import LocalLLM
from core.persona import PersonaEngine
from tools.search_agent import search_live_web


def test_get_session_messages_chronological_last_n(tmp_path):
    """Verify that get_session_messages(limit=N) returns the most recent N messages in chronological order."""
    db_file = str(tmp_path / "test_memory.db")
    mem = MemoryCore(db_path=db_file)
    sid = "test_session_chronology"

    # Add 10 messages (5 turns)
    for i in range(1, 11):
        role = "user" if i % 2 != 0 else "assistant"
        mem.add_session_message(session_id=sid, role=role, content=f"Message {i}")

    # Fetch last 4 messages
    recent_4 = mem.get_session_messages(sid, limit=4)
    assert len(recent_4) == 4

    # Must be messages 7, 8, 9, 10 in ascending chronological order!
    assert [m["content"] for m in recent_4] == ["Message 7", "Message 8", "Message 9", "Message 10"]

    # Fetch last 6 messages
    recent_6 = mem.get_session_messages(sid, limit=6)
    assert len(recent_6) == 6
    assert [m["content"] for m in recent_6] == ["Message 5", "Message 6", "Message 7", "Message 8", "Message 9", "Message 10"]


def test_creator_and_identity_inquiries():
    """Verify that Libra knows her creator is Chuah Chen Xuan (Chen Xuan) and knows her own identity."""
    llm = LocalLLM()
    llm.memory = MemoryCore(db_path=":memory:")

    # Creator inquiries
    res_creator = llm.plan("Who is your creator?", dry_run=True)
    assert res_creator["action"] == "chat"
    resp_text = res_creator["voice_response"]
    assert "Chuah Chen Xuan" in resp_text or "Chen Xuan" in resp_text

    res_dev = llm.plan("Who created you?", dry_run=True)
    assert "Chuah Chen Xuan" in res_dev["voice_response"] or "Chen Xuan" in res_dev["voice_response"]

    # Self-identity inquiry
    res_identity = llm.plan("Who are you?", dry_run=True)
    assert "Project Libra" in res_identity["voice_response"]
    assert "Chuah Chen Xuan" in res_identity["voice_response"] or "Chen Xuan" in res_identity["voice_response"]


def test_persona_engine_soul_addon():
    """Verify that PersonaEngine system prompt addon embeds creator Chuah Chen Xuan and cybernetic identity."""
    persona = PersonaEngine()
    addon = persona.get_system_prompt_addon()
    assert "Chuah Chen Xuan" in addon
    assert "Project Libra" in addon
    assert "chenxuanchuah@gmail.com" in addon


def test_relational_entity_tracking_and_pronoun_resolution():
    """Verify that standalone entity names are tracked and pronouns are resolved."""
    llm = LocalLLM()
    llm.memory = MemoryCore(db_path=":memory:")

    # Turn 1: User says a name
    ent = llm._extract_and_cache_entity("Anthony Edwards")
    assert ent == "Anthony Edwards"
    assert llm.session_state.get("last_entity") == "Anthony Edwards"

    # Turn 2: User asks follow-up with pronoun "he"
    resolved = llm.resolve_relational_query("did he get injured today?")
    assert "Anthony Edwards" in resolved
    assert "did Anthony Edwards get injured today?" in resolved


def test_search_live_web_returns_results():
    """Verify that search_live_web queries DuckDuckGo and returns real snippets."""
    res = search_live_web("Anthony Edwards NBA", max_results=2)
    assert isinstance(res, str)
    assert len(res) > 20
    assert "Anthony Edwards" in res or "Timberwolves" in res or "NBA" in res
