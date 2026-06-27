"""Feishu event callback handler and shared progress collection logic."""

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

_DEFAULT_QUESTIONS = [
    "请按“项目 + 已完成/正在做 + 下一步 + 风险阻塞”的格式提交进度。",
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

    if normalized in {"progress", "/progress", "开始", "开始进度", "进度"}:
        _start_progress_collection(adapter, team_id, user_id, fallback_channel=chat_id)
        return

    if normalized in {"skip", "/skip", "跳过", "请假"}:
        db.skip_today(team_id, user_id)
        adapter.send_dm(user_id, "今天已跳过。")
        return

    if normalized in {"help", "/help", "帮助"}:
        adapter.send_dm(user_id, "回复“进度”开始填写；回复“跳过”跳过今天。")
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

    if session.phase in {"confirming", "needs_revision"}:
        if normalized in {"确认", "ok", "okay", "yes", "y"}:
            if session.phase == "confirming" and (session.pending_progress or {}).get("valid"):
                _save_confirmed_progress(adapter, user_id, session)
            else:
                adapter.send_dm(user_id, "当前进度还没有通过格式校验，请先补充项目和进度内容。")
            return
        session = state_store.record_feedback(cache_key, text) or session
        _normalize_and_request_confirmation(adapter, user_id, session, feedback=text)
        return

    session = state_store.record_answer(cache_key, text)
    if session is None:
        adapter.send_dm(user_id, "会话已失效，请回复“进度”重新开始。")
        return

    n_questions = len(session.questions)
    if session.step < n_questions:
        question = session.questions[session.step]
        adapter.send_dm(user_id, question)
        state_store.record_assistant_message(cache_key, question)
    else:
        _normalize_and_request_confirmation(adapter, user_id, session)


def _start_progress_collection(
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
    collection_name = "进度收集"
    resolved_collection_id = schedule_id

    sched = None
    if schedule_id is not None:
        sched = db.get_progress_collection(team_id, schedule_id)
    if sched is None:
        sched = db.get_progress_collection_for_user(team_id, user_id)
    if sched:
        channel_id = sched.get("channel_id") or channel_id
        questions = _questions_from_config(sched.get("questions"))
        collection_name = sched.get("name") or collection_name
        resolved_collection_id = sched.get("id")
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
        collection_name=collection_name,
        collection_id=resolved_collection_id,
    )
    message = f"{collection_name}\n\n{active_questions[0]}"
    adapter.send_dm(user_id, message)
    state_store.record_assistant_message(cache_key, message)


def _normalize_and_request_confirmation(
    adapter: FeishuAdapter,
    user_id: str,
    session,
    *,
    feedback: str = "",
) -> None:
    answers = list(session.answers)
    member = _member_payload(session.team_id, user_id)
    projects = db.get_projects(session.team_id)
    previous = db.get_previous_progress_entry(session.team_id, user_id)

    from ai_progress import normalize_progress  # noqa: PLC0415

    pending = normalize_progress(
        raw_answers=answers,
        conversation=session.messages,
        projects=projects,
        member=member,
        previous_entry=previous,
        feedback=feedback,
    )

    if not pending.get("valid"):
        state_store.clear_pending_progress(f"{session.team_id}:{user_id}")
        errors = "；".join(pending.get("validation_errors") or ["进度格式不完整"])
        message = f"这版进度还不能入库：{errors}。请补充项目和进度内容，我会重新整理。"
        adapter.send_dm(user_id, message)
        state_store.record_assistant_message(f"{session.team_id}:{user_id}", message)
        return

    state_store.set_pending_progress(f"{session.team_id}:{user_id}", pending)
    message = _format_progress_confirmation(pending)
    adapter.send_dm(user_id, message)
    state_store.record_assistant_message(f"{session.team_id}:{user_id}", message)


def _format_progress_confirmation(pending: dict) -> str:
    project_name = (pending.get("project_name") or "未归属项目").strip()
    role = (pending.get("role") or "未填写").strip()
    content = (pending.get("content") or "").strip()
    return (
        "我整理成下面这版进度，请检查项目、岗位和内容。\n"
        "确认无误请回复“确认”；如果不准确，直接继续补充。\n\n"
        f"项目：{project_name}\n"
        f"岗位：{role}\n"
        f"进度：\n{content}"
    )


def _save_confirmed_progress(adapter: FeishuAdapter, user_id: str, session) -> None:
    pending = session.pending_progress or {}
    project_id = pending.get("project_id")
    if project_id is None:
        project_id = _resolve_project_id(session.team_id, pending.get("project_name", ""))

    db.save_progress_entry(
        team_id=session.team_id,
        collection_id=session.collection_id,
        user_id=user_id,
        project_id=project_id,
        role=pending.get("role", ""),
        content=pending.get("content", ""),
    )
    _upsert_feishu_member(adapter, session.team_id, user_id)
    confirmation = "已保存。"
    adapter.send_dm(user_id, confirmation)
    state_store.clear(f"{session.team_id}:{user_id}")


def _member_payload(team_id: str, user_id: str) -> dict:
    for member in db.get_active_members(team_id):
        if member.get("user_id") == user_id:
            return member
    return {"user_id": user_id}


def _resolve_project_id(team_id: str, project_name: str) -> int | None:
    name = (project_name or "").strip()
    if not name or name == "未归属项目":
        return None
    for project in db.get_projects(team_id):
        if (project.get("name") or "").strip() == name:
            return int(project["id"])
    return None


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
