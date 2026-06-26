"""Tests for Feishu long-connection transport."""

from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

sys.modules.setdefault("db", MagicMock())

import feishu_longconn  # noqa: E402


def test_event_mode_defaults_to_ws(monkeypatch):
    monkeypatch.delenv("FEISHU_EVENT_MODE", raising=False)
    assert feishu_longconn.feishu_event_mode() == "ws"


def test_event_mode_normalizes_invalid_value(monkeypatch):
    monkeypatch.setenv("FEISHU_EVENT_MODE", "invalid")
    assert feishu_longconn.feishu_event_mode() == "ws"


def test_dispatch_message_forwards_text():
    service = feishu_longconn.FeishuLongConnectionService()
    msg = SimpleNamespace(sender_id="ou_1", content_text="站会", chat_id="oc_1", chat_type="p2p")

    with patch.object(feishu_longconn.asyncio, "to_thread", new_callable=AsyncMock) as to_thread:
        asyncio.run(service._dispatch_message(msg))

    to_thread.assert_awaited_once_with(
        feishu_longconn.handle_feishu_text_message,
        user_id="ou_1",
        text="站会",
        chat_id="oc_1",
        chat_type="p2p",
    )
