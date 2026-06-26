"""Feishu long-connection event transport."""

from __future__ import annotations

import asyncio
import atexit
import logging
import threading

from app_settings import get_setting
from feishu_bootstrap import feishu_enabled
from feishu_handler import handle_feishu_text_message

logger = logging.getLogger(__name__)


def feishu_event_mode() -> str:
    mode = (get_setting("FEISHU_EVENT_MODE", "ws") or "ws").strip().lower()
    return mode if mode in {"ws", "webhook"} else "ws"


def feishu_uses_long_connection() -> bool:
    return feishu_enabled() and feishu_event_mode() == "ws"


class FeishuLongConnectionService:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._channel = None
        self._started = False

    def start(self) -> None:
        if self._started or not feishu_uses_long_connection():
            return
        self._started = True
        self._thread = threading.Thread(
            target=self._run,
            name="feishu-long-connection",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5) -> None:
        if not self._started:
            return
        self._started = False
        if self._channel:
            try:
                self._channel.stop(join_timeout=timeout)
            except Exception as exc:
                logger.debug("Feishu long connection stop error: %s", exc)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        try:
            self._serve()
        except Exception as exc:
            logger.error("Feishu long connection crashed: %s", exc)
        finally:
            self._channel = None
            self._started = False

    def _serve(self) -> None:
        try:
            from lark_channel import FeishuChannel, SecurityConfig
        except ImportError as exc:
            logger.warning("Feishu long connection unavailable: install lark-channel-sdk (%s)", exc)
            return

        self._channel = FeishuChannel(
            app_id=get_setting("FEISHU_APP_ID"),
            app_secret=get_setting("FEISHU_APP_SECRET"),
            security=SecurityConfig(mode="compat"),
        )
        self._channel.on("message", self._dispatch_message)
        self._channel.on("error", self._on_error)
        logger.info("Starting Feishu long connection")
        self._channel.start()

    async def _dispatch_message(self, msg) -> None:
        user_id = getattr(msg, "sender_id", "")
        text = (getattr(msg, "content_text", "") or "").strip()
        chat_id = getattr(msg, "chat_id", "")
        chat_type = getattr(msg, "chat_type", "")
        if not user_id or not text:
            return
        await asyncio.to_thread(
            handle_feishu_text_message,
            user_id=user_id,
            text=text,
            chat_id=chat_id,
            chat_type=chat_type,
        )

    async def _on_error(self, err) -> None:
        logger.warning("Feishu long connection error: %s", err)


feishu_longconn_service = FeishuLongConnectionService()
atexit.register(feishu_longconn_service.stop)
