"""Conversation state — tracks each user's active progress collection session.

Per-workspace persistent data lives in PostgreSQL via db.py.
Active DM conversation state is stored in Redis (with in-memory fallback) via
session_store so sessions survive pod restarts.
Cache keys are `team_id:user_id` to support multi-workspace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Optional

import session_store

QUESTIONS = [
    "请说明你当前的项目进展。",
    "今天接下来计划推进什么？",
    "有什么风险或阻塞？没有就回复“无”。",
]


@dataclass
class UserSession:
    cache_key: str  # "team_id:user_id"
    team_id: str
    channel: str  # target channel for the summary post
    response_chat_id: str = ""  # exact Feishu private chat that is allowed to answer this session
    step: int = 0  # 0=sent q1, 1=sent q2, 2=sent q3, 3=mood, 4=done
    answers: list[str] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    questions: list[str] = field(default_factory=lambda: list(QUESTIONS))
    collection_name: str = "进度收集"
    collection_id: Optional[int] = None
    phase: str = "answering"
    pending_progress: dict = field(default_factory=dict)
    standup_name: str = "进度收集"
    schedule_id: Optional[int] = None
    editing_standup_id: Optional[int] = None
    edit_initial_answers: list[str] = field(default_factory=list)  # pre-fill text for each question

    @property
    def user_id(self) -> str:
        return self.cache_key.split(":", 1)[-1]


def _serialize(session: "UserSession") -> dict:
    return {
        "cache_key": session.cache_key,
        "team_id": session.team_id,
        "channel": session.channel,
        "response_chat_id": session.response_chat_id,
        "step": session.step,
        "answers": session.answers,
        "messages": session.messages,
        "questions": session.questions,
        "collection_name": session.collection_name,
        "collection_id": session.collection_id,
        "phase": session.phase,
        "pending_progress": session.pending_progress,
        "standup_name": session.collection_name,
        "schedule_id": session.collection_id,
        "editing_standup_id": session.editing_standup_id,
        "edit_initial_answers": session.edit_initial_answers,
    }


def _deserialize(data: dict) -> "UserSession":
    return UserSession(
        cache_key=data["cache_key"],
        team_id=data.get("team_id", ""),
        channel=data.get("channel", ""),
        response_chat_id=data.get("response_chat_id", ""),
        step=data.get("step", 0),
        answers=data.get("answers", []),
        messages=data.get("messages") or [],
        questions=data.get("questions", list(QUESTIONS)),
        collection_name=data.get("collection_name") or data.get("standup_name", "进度收集"),
        collection_id=data.get("collection_id") or data.get("schedule_id"),
        phase=data.get("phase", "answering"),
        pending_progress=data.get("pending_progress") or {},
        standup_name=data.get("collection_name") or data.get("standup_name", "进度收集"),
        schedule_id=data.get("collection_id") or data.get("schedule_id"),
        editing_standup_id=data.get("editing_standup_id"),
        edit_initial_answers=data.get("edit_initial_answers") or [],
    )


class StateStore:
    """Redis-backed store for active progress DM conversations."""

    def __init__(self) -> None:
        self._lock = Lock()

    def start(
        self,
        cache_key: str,
        channel: str,
        *,
        team_id: str = "",
        response_chat_id: str = "",
        questions: list[str] | None = None,
        collection_name: str = "进度收集",
        collection_id: Optional[int] = None,
        standup_name: str | None = None,
        schedule_id: Optional[int] = None,
        editing_standup_id: Optional[int] = None,
        edit_initial_answers: Optional[list[str]] = None,
    ) -> UserSession:
        """Begin a new progress collection session. cache_key should be 'team_id:user_id'."""
        if not team_id:
            # Derive team_id from cache_key when not provided explicitly
            team_id = cache_key.split(":", 1)[0] if ":" in cache_key else ""
        resolved_name = collection_name or standup_name or "进度收集"
        resolved_id = collection_id if collection_id is not None else schedule_id
        with self._lock:
            session = UserSession(
                cache_key=cache_key,
                team_id=team_id,
                channel=channel,
                response_chat_id=response_chat_id,
                questions=list(questions) if questions is not None else list(QUESTIONS),
                collection_name=resolved_name,
                collection_id=resolved_id,
                standup_name=resolved_name,
                schedule_id=resolved_id,
                editing_standup_id=editing_standup_id,
                edit_initial_answers=list(edit_initial_answers) if edit_initial_answers else [],
            )
            session_store.set_session(cache_key, _serialize(session))
            return session

    def bind_response_chat(self, cache_key: str, response_chat_id: str) -> Optional[UserSession]:
        with self._lock:
            data = session_store.get_session(cache_key)
            if not data:
                return None
            session = _deserialize(data)
            session.response_chat_id = response_chat_id
            session_store.set_session(cache_key, _serialize(session))
            return session

    def get(self, cache_key: str) -> Optional[UserSession]:
        data = session_store.get_session(cache_key)
        return _deserialize(data) if data else None

    def record_answer(self, cache_key: str, answer: str) -> Optional[UserSession]:
        with self._lock:
            data = session_store.get_session(cache_key)
            if not data:
                return None
            session = _deserialize(data)
            session.answers.append(answer)
            session.messages.append({"role": "user", "content": answer})
            session.step += 1
            session_store.set_session(cache_key, _serialize(session))
            return session

    def record_feedback(self, cache_key: str, feedback: str) -> Optional[UserSession]:
        with self._lock:
            data = session_store.get_session(cache_key)
            if not data:
                return None
            session = _deserialize(data)
            session.answers.append(feedback)
            session.messages.append({"role": "user", "content": feedback})
            session_store.set_session(cache_key, _serialize(session))
            return session

    def record_assistant_message(self, cache_key: str, message: str) -> Optional[UserSession]:
        with self._lock:
            data = session_store.get_session(cache_key)
            if not data:
                return None
            session = _deserialize(data)
            session.messages.append({"role": "assistant", "content": message})
            session_store.set_session(cache_key, _serialize(session))
            return session

    def set_pending_progress(self, cache_key: str, pending_progress: dict) -> Optional[UserSession]:
        with self._lock:
            data = session_store.get_session(cache_key)
            if not data:
                return None
            session = _deserialize(data)
            session.phase = "confirming"
            session.pending_progress = pending_progress
            session_store.set_session(cache_key, _serialize(session))
            return session

    def clear_pending_progress(self, cache_key: str) -> Optional[UserSession]:
        with self._lock:
            data = session_store.get_session(cache_key)
            if not data:
                return None
            session = _deserialize(data)
            session.phase = "needs_revision"
            session.pending_progress = {}
            session_store.set_session(cache_key, _serialize(session))
            return session

    def clear(self, cache_key: str) -> None:
        session_store.delete_session(cache_key)

    def is_active(self, cache_key: str) -> bool:
        return session_store.has_session(cache_key)


state_store = StateStore()
