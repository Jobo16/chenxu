"""Tests for Feishu adapter request formatting."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))


def _resp(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_send_dm_uses_open_id_receive_type():
    from adapters.feishu_adapter import FeishuAdapter

    adapter = FeishuAdapter("app-id", "secret")

    with patch("adapters.feishu_adapter.requests.post", return_value=_resp({"code": 0, "tenant_access_token": "t"})):
        with patch(
            "adapters.feishu_adapter.requests.request",
            return_value=_resp({"code": 0, "data": {"message_id": "om_x"}}),
        ) as request_mock:
            adapter.send_dm("ou_1", "*hello*")

    _, kwargs = request_mock.call_args
    assert kwargs["params"] == {"receive_id_type": "open_id"}
    assert kwargs["json"]["receive_id"] == "ou_1"
    assert kwargs["json"]["msg_type"] == "text"
    assert json.loads(kwargs["json"]["content"]) == {"text": "hello"}


def test_post_to_channel_uses_chat_id_receive_type():
    from adapters.feishu_adapter import FeishuAdapter

    adapter = FeishuAdapter("app-id", "secret")

    with patch("adapters.feishu_adapter.requests.post", return_value=_resp({"code": 0, "tenant_access_token": "t"})):
        with patch(
            "adapters.feishu_adapter.requests.request",
            return_value=_resp({"code": 0, "data": {"message_id": "om_x"}}),
        ) as request_mock:
            adapter.post_to_channel("oc_1", "summary")

    _, kwargs = request_mock.call_args
    assert kwargs["params"] == {"receive_id_type": "chat_id"}
    assert kwargs["json"]["receive_id"] == "oc_1"


def test_list_chats_paginates():
    from adapters.feishu_adapter import FeishuAdapter

    adapter = FeishuAdapter("app-id", "secret")

    with patch("adapters.feishu_adapter.requests.post", return_value=_resp({"code": 0, "tenant_access_token": "t"})):
        with patch(
            "adapters.feishu_adapter.requests.request",
            side_effect=[
                _resp({"code": 0, "data": {"items": [{"chat_id": "oc_1", "name": "研发群"}], "has_more": True, "page_token": "p2"}}),
                _resp({"code": 0, "data": {"items": [{"chat_id": "oc_2", "name": "产品群"}], "has_more": False}}),
            ],
        ):
            chats = adapter.list_chats()

    assert [c["chat_id"] for c in chats] == ["oc_1", "oc_2"]
