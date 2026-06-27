"""Tests for Feishu event handling helpers."""

from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

db_mock = MagicMock()
sys.modules["db"] = db_mock

import feishu_handler  # noqa: E402


@pytest.fixture()
def app():
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.register_blueprint(feishu_handler.feishu_bp)
    return flask_app


def test_url_verification_returns_challenge(app, monkeypatch):
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "token-1")
    resp = app.test_client().post(
        "/feishu/events",
        json={"type": "url_verification", "token": "token-1", "challenge": "abc"},
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"challenge": "abc"}


def test_url_verification_rejects_wrong_token(app, monkeypatch):
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "token-1")
    resp = app.test_client().post(
        "/feishu/events",
        json={"type": "url_verification", "token": "wrong", "challenge": "abc"},
    )

    assert resp.status_code == 403


def test_extract_text_from_message_content():
    assert feishu_handler._extract_text({"content": json.dumps({"text": "进度"})}) == "进度"


def test_message_event_starts_progress_collection(monkeypatch):
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "")
    monkeypatch.setenv("FEISHU_TEAM_ID", "feishu")
    adapter = MagicMock()

    with patch.object(feishu_handler, "FeishuAdapter", return_value=adapter):
        with patch.object(feishu_handler, "_start_progress_collection") as start_mock:
            feishu_handler._handle_message(
                {
                    "header": {"event_type": "im.message.receive_v1", "tenant_key": "tenant"},
                    "event": {
                        "sender": {"sender_type": "user", "sender_id": {"open_id": "ou_1"}},
                        "message": {
                            "message_type": "text",
                            "chat_id": "oc_1",
                            "content": json.dumps({"text": "进度"}),
                        },
                    },
                }
            )

    start_mock.assert_called_once()
    assert start_mock.call_args.args[1:3] == ("feishu", "ou_1")


def test_handle_text_message_starts_progress_collection(monkeypatch):
    monkeypatch.setenv("FEISHU_TEAM_ID", "feishu")
    adapter = MagicMock()

    with patch.object(feishu_handler, "FeishuAdapter", return_value=adapter):
        with patch.object(feishu_handler, "_start_progress_collection") as start_mock:
            feishu_handler.handle_feishu_text_message(user_id="ou_1", text="进度", chat_id="oc_1")

    start_mock.assert_called_once()
    assert start_mock.call_args.args[1:3] == ("feishu", "ou_1")


def test_group_message_is_not_recorded_for_active_session(monkeypatch):
    monkeypatch.setenv("FEISHU_TEAM_ID", "feishu")
    adapter = MagicMock()
    session = SimpleNamespace(response_chat_id="")

    with patch.object(feishu_handler, "FeishuAdapter", return_value=adapter):
        with patch.object(feishu_handler.state_store, "get", return_value=session):
            with patch.object(feishu_handler.state_store, "record_answer") as record_mock:
                feishu_handler.handle_feishu_text_message(
                    user_id="ou_1",
                    text="这是一条群消息",
                    chat_id="oc_group",
                    chat_type="group",
                )

    record_mock.assert_not_called()


def test_private_message_binds_reply_chat_before_recording(monkeypatch):
    monkeypatch.setenv("FEISHU_TEAM_ID", "feishu")
    adapter = MagicMock()
    session = SimpleNamespace(response_chat_id="", questions=["Q1"], step=0, phase="answering")
    recorded = SimpleNamespace(
        response_chat_id="oc_dm",
        team_id="feishu",
        collection_id=None,
        questions=["Q1"],
        step=1,
        phase="answering",
        answers=["我的第一条回复"],
        messages=[{"role": "user", "content": "我的第一条回复"}],
    )

    with patch.object(feishu_handler, "FeishuAdapter", return_value=adapter):
        with patch.object(feishu_handler.state_store, "get", return_value=session):
            with patch.object(feishu_handler.state_store, "bind_response_chat", return_value=session) as bind_mock:
                with patch.object(feishu_handler.state_store, "record_answer", return_value=recorded) as record_mock:
                    feishu_handler.handle_feishu_text_message(
                        user_id="ou_1",
                        text="我的第一条回复",
                        chat_id="oc_dm",
                        chat_type="p2p",
                    )

    bind_mock.assert_called_once_with("feishu:ou_1", "oc_dm")
    record_mock.assert_called_once_with("feishu:ou_1", "我的第一条回复")


def test_message_from_wrong_private_chat_is_ignored(monkeypatch):
    monkeypatch.setenv("FEISHU_TEAM_ID", "feishu")
    adapter = MagicMock()
    session = SimpleNamespace(response_chat_id="oc_dm_expected")

    with patch.object(feishu_handler, "FeishuAdapter", return_value=adapter):
        with patch.object(feishu_handler.state_store, "get", return_value=session):
            with patch.object(feishu_handler.state_store, "record_answer") as record_mock:
                feishu_handler.handle_feishu_text_message(
                    user_id="ou_1",
                    text="串线回复",
                    chat_id="oc_other",
                    chat_type="p2p",
                )

    record_mock.assert_not_called()


def test_confirmed_progress_saves_record_and_confirms_in_dm():
    db_mock.reset_mock()
    adapter = MagicMock()
    session = SimpleNamespace(
        team_id="feishu",
        channel="oc_1",
        collection_id=7,
        questions=["Q1", "Q2", "Q3"],
        answers=["昨天完成", "今天继续", "无"],
        pending_progress={
            "project_name": "未归属项目",
            "role": "后端",
            "content": "项目：未归属项目\n进度：昨天完成，今天继续。",
        },
    )

    with patch.object(feishu_handler, "_upsert_feishu_member") as upsert_mock:
        with patch.object(feishu_handler.state_store, "clear") as clear_mock:
            feishu_handler._save_confirmed_progress(adapter, "ou_1", session)

    db_mock.save_progress_entry.assert_called_once_with(
        team_id="feishu",
        collection_id=7,
        user_id="ou_1",
        project_id=None,
        role="后端",
        content="项目：未归属项目\n进度：昨天完成，今天继续。",
    )
    upsert_mock.assert_called_once_with(adapter, "feishu", "ou_1")
    adapter.post_to_channel.assert_not_called()
    adapter.send_dm.assert_called_once_with("ou_1", "已保存。")
    clear_mock.assert_called_once_with("feishu:ou_1")


def test_format_progress_confirmation_shows_parsed_fields():
    message = feishu_handler._format_progress_confirmation(
        {
            "project_name": "晨序",
            "role": "后端",
            "content": "完成飞书长连接收集。\n下一步验证 Dashboard。",
        }
    )

    assert "项目：晨序" in message
    assert "岗位：后端" in message
    assert "进度：\n完成飞书长连接收集。\n下一步验证 Dashboard。" in message
    assert "回复“确认”" in message
    assert "project_name" not in message


def test_resolve_project_id_does_not_create_unknown_project():
    db_mock.reset_mock()
    db_mock.get_projects.return_value = [{"id": 9, "name": "已有项目"}]

    assert feishu_handler._resolve_project_id("feishu", "不存在的项目") is None

    db_mock.upsert_project.assert_not_called()


def test_needs_revision_cannot_be_confirmed(monkeypatch):
    monkeypatch.setenv("FEISHU_TEAM_ID", "feishu")
    db_mock.reset_mock()
    adapter = MagicMock()
    session = SimpleNamespace(
        response_chat_id="oc_dm",
        phase="needs_revision",
        pending_progress={},
    )

    with patch.object(feishu_handler, "FeishuAdapter", return_value=adapter):
        with patch.object(feishu_handler.state_store, "get", return_value=session):
            feishu_handler.handle_feishu_text_message(
                user_id="ou_1",
                text="确认",
                chat_id="oc_dm",
                chat_type="p2p",
            )

    db_mock.save_progress_entry.assert_not_called()
    adapter.send_dm.assert_called_once_with("ou_1", "当前进度还没有通过格式校验，请先补充项目和进度内容。")
