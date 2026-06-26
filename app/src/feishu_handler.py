"""Feishu event callback handler and shared message-processing logic."""

from __future__ import annotations

import json
import logging

import db
from adapters.feishu_adapter import FeishuAdapter
from app_settings import get_setting
from feishu_bootstrap import feishu_team_id
from flask import Blueprint, jsonify, request
from state import state_store

logger = logging.getLogger(__name__)
feishu_bp = Blueprint("feishu", __name__)

_MOOD_QUESTION = "🎭 今天状态怎么样？（很好 / 正常 / 有点累，或直接写任何内容）"
_DEFAULT_QUESTIONS = [
    "昨天完成了什么？",
    "今天计划做什么？",
    "有什么阻塞？没有就回复“无”。",
]


@feishu_bp.route("/feishu/events", methods=["POST"])
def feishu_events():
    payload = request.get_json(silent=True) or {}
    if payload.get("encrypt"):
        logger.warning("Encrypted Feishu callbacks are not supported; disable Encrypt Key for this endpoint")
        return jsonify({"error": "encrypted callbacks are not supported"}), 400

    if payload.get("type") == "url_verification":
        if not _verify_token(payload):
            return jsonify({"error": "invalid token"}), 403
        return jsonify({"challenge": payload.get("challenge", "")})

    if not _verify_token(payload):
        return jsonify({"error": "invalid token"}), 403

    header = payload.get("header", {})
    if header.get("event_type") != "im.message.receive_v1":
        return jsonify({}), 200

    try:
        _handle_message(payload)
    except Exception as exc:
        logger.error("Unhandled Feishu message event error: %s", exc)
    return jsonify({}), 200


def _verify_token(payload: dict) -> bool:
    expected = get_setting("FEISHU_VERIFICATION_TOKEN")
    if not expected:
        return True
    token = payload.get("token") or payload.get("header", {}).get("token")
    return token == expected


def _handle_message(payload: dict) -> None:
    event = payload.get("event", {})
    sender = event.get("sender", {})
    sender_type = sender.get("sender_type", "")
    if sender_type == "app":
        return

    message = event.get("message", {})
    if message.get("message_type") != "text":
        return

    user_id = (
        sender.get("sender_id", {}).get("open_id")
        or sender.get("sender_id", {}).get("user_id")
        or sender.get("sender_id", {}).get("union_id")
    )
    if not user_id:
        logger.warning("Feishu message without sender open_id: %s", payload)
        return

    chat_id = message.get("chat_id", "")
    chat_type = message.get("chat_type", "")
    text = _extract_text(message).strip()
    handle_feishu_text_message(user_id=user_id, text=text, chat_id=chat_id, chat_type=chat_type)


def _extract_text(message: dict) -> str:
    content = message.get("content") or "{}"
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return ""
    return data.get("text", "")


def _is_private_chat(chat_type: str) -> bool:
    return (chat_type or "").strip().lower() in {"p2p", "private"}


def handle_feishu_text_message(*, user_id: str, text: str, chat_id: str = "", chat_type: str = "") -> None:
    team_id = feishu_team_id()
    normalized = (text or "").strip().lower()
    adapter = FeishuAdapter()
    cache_key = f"{team_id}:{user_id}"

    _upsert_feishu_member(adapter, team_id, user_id)

    if normalized in {"standup", "/standup", "开始", "开始站会", "站会"}:
        _start_feishu_standup(adapter, team_id, user_id, fallback_channel=chat_id)
        return

    if normalized in {"skip", "/skip", "跳过", "请假"}:
        db.skip_today(team_id, user_id)
        adapter.send_dm(user_id, "今天已跳过。")
        return

    if normalized in {"help", "/help", "帮助"}:
        adapter.send_dm(user_id, "回复“站会”开始填写；回复“跳过”跳过今天。")
        return

    session = state_store.get(cache_key)
    if not session:
        return

    if not _is_private_chat(chat_type):
        logger.info("Ignoring Feishu non-private reply for active session %s in chat %s", cache_key, chat_id or "<unknown>")
        return

    if session.response_chat_id and chat_id != session.response_chat_id:
        logger.info(
            "Ignoring Feishu reply from unexpected chat for active session %s: expected %s got %s",
            cache_key,
            session.response_chat_id,
            chat_id or "<unknown>",
        )
        return

    if not session.response_chat_id and chat_id:
        session = state_store.bind_response_chat(cache_key, chat_id) or session

    session = state_store.record_answer(cache_key, text)
    if session is None:
        adapter.send_dm(user_id, "会话已失效，请回复“站会”重新开始。")
        return

    n_questions = len(session.questions)
    if session.step < n_questions:
        adapter.send_dm(user_id, session.questions[session.step])
    elif session.step == n_questions:
        adapter.send_dm(user_id, _MOOD_QUESTION)
    else:
        _complete_feishu_standup(adapter, user_id, session)


def _start_feishu_standup(
    adapter: FeishuAdapter,
    team_id: str,
    user_id: str,
    *,
    fallback_channel: str = "",
    schedule_id: int | None = None,
) -> None:
    cache_key = f"{team_id}:{user_id}"
    if state_store.is_active(cache_key):
        state_store.clear(cache_key)

    channel_id = fallback_channel
    questions: list[str] | None = None
    standup_name = "团队站会"
    resolved_schedule_id = schedule_id

    sched = None
    if schedule_id is not None:
        sched = db.get_standup_schedule(team_id, schedule_id)
    if sched is None:
        sched = db.get_schedule_for_user(team_id, user_id)
    if sched:
        channel_id = sched.get("channel_id") or channel_id
        questions = _questions_from_config(sched.get("questions"))
        standup_name = sched.get("name") or standup_name
        resolved_schedule_id = sched.get("id")
    else:
        config = db.get_workspace_config(team_id) or {}
        channel_id = config.get("channel_id") or channel_id
        questions = _questions_from_config(config.get("questions"))

    active_questions = questions or list(_DEFAULT_QUESTIONS)
    state_store.start(
        cache_key,
        channel_id,
        team_id=team_id,
        questions=active_questions,
        standup_name=standup_name,
        schedule_id=resolved_schedule_id,
    )
    adapter.send_dm(user_id, f"{standup_name}\n\n{active_questions[0]}")


def _complete_feishu_standup(adapter: FeishuAdapter, user_id: str, session) -> None:
    n_questions = len(session.questions)
    answers = session.answers[:n_questions]
    mood = session.answers[n_questions] if len(session.answers) > n_questions else None

    db.save_standup(
        team_id=session.team_id,
        user_id=user_id,
        yesterday=answers[0] if len(answers) > 0 else "",
        today=answers[1] if len(answers) > 1 else "",
        blockers=answers[2] if len(answers) > 2 else "",
        mood=mood,
    )
    _upsert_feishu_member(adapter, session.team_id, user_id)
    confirmation = "已提交。将在汇总时间统一发到群里。" if session.channel else "已提交。"
    adapter.send_dm(user_id, confirmation)
    state_store.clear(f"{session.team_id}:{user_id}")


def _questions_from_config(raw) -> list[str] | None:
    if not raw:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    return [str(q) for q in raw if str(q).strip()] or None


def _upsert_feishu_member(adapter: FeishuAdapter, team_id: str, user_id: str) -> None:
    try:
        info = adapter.get_user_info(user_id)
        db.upsert_member(
            team_id=team_id,
            user_id=user_id,
            real_name=info.get("name") or user_id,
            email=info.get("email", ""),
            tz=info.get("tz") or "Asia/Shanghai",
        )
    except Exception as exc:
        logger.debug("Could not upsert Feishu member %s/%s: %s", team_id, user_id, exc)
