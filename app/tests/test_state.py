"""Tests for active progress collection conversation state."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))


@pytest.fixture(autouse=True)
def reset_session_store(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    import session_store

    session_store._redis = None
    session_store._memory.clear()
    yield
    session_store._redis = None
    session_store._memory.clear()


def test_session_records_conversation_messages():
    from state import StateStore

    store = StateStore()
    store.start("feishu:ou_1", "oc_1", team_id="feishu", questions=["Q1"])
    store.record_assistant_message("feishu:ou_1", "Q1")
    store.record_answer("feishu:ou_1", "A1")
    store.set_pending_progress("feishu:ou_1", {"valid": True, "content": "整理后的内容"})
    store.record_assistant_message("feishu:ou_1", "请确认")
    store.record_feedback("feishu:ou_1", "补充说明")

    session = store.get("feishu:ou_1")

    assert session is not None
    assert session.messages == [
        {"role": "assistant", "content": "Q1"},
        {"role": "user", "content": "A1"},
        {"role": "assistant", "content": "请确认"},
        {"role": "user", "content": "补充说明"},
    ]
    assert session.answers == ["A1", "补充说明"]
