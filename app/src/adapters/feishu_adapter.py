"""Feishu/Lark adapter for internal standup bot deployments."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import requests
from adapters.base import PlatformAdapter
from app_settings import get_setting

logger = logging.getLogger(__name__)

FEISHU_API = "https://open.feishu.cn/open-apis"


class FeishuAPIError(RuntimeError):
    """Raised when Feishu returns a non-zero application code."""


class FeishuAdapter(PlatformAdapter):
    """Minimal Feishu bot adapter using tenant_access_token.

    This is intentionally scoped to a company-internal custom app. It does not
    implement marketplace install flows or user OAuth.
    """

    def __init__(self, app_id: str | None = None, app_secret: str | None = None):
        self.app_id = app_id or get_setting("FEISHU_APP_ID")
        self.app_secret = app_secret or get_setting("FEISHU_APP_SECRET")
        if not self.app_id or not self.app_secret:
            raise ValueError("FEISHU_APP_ID and FEISHU_APP_SECRET are required")
        self._token = ""
        self._token_expiry = 0

    def _get_token(self) -> str:
        now = int(time.time())
        if self._token and now < self._token_expiry - 60:
            return self._token

        resp = requests.post(
            f"{FEISHU_API}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code", 0) != 0:
            raise FeishuAPIError(f"tenant_access_token failed: {data.get('msg') or data}")
        self._token = data["tenant_access_token"]
        self._token_expiry = now + int(data.get("expire", 7200))
        return self._token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resp = requests.request(
            method,
            f"{FEISHU_API}{path}",
            params=params,
            json=payload,
            headers=self._headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code", 0) != 0:
            raise FeishuAPIError(f"{method} {path} failed: {data.get('msg') or data}")
        return data

    def send_message(self, receive_id: str, receive_id_type: str, text: str) -> dict[str, Any]:
        content = json.dumps({"text": _to_plain_text(text)}, ensure_ascii=False)
        return self._request(
            "POST",
            "/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            payload={"receive_id": receive_id, "msg_type": "text", "content": content},
        )

    def send_dm(self, user_id: str, text: str, blocks=None) -> None:
        self.send_message(user_id, "open_id", text)

    def post_to_channel(self, channel_id: str, text: str, blocks=None) -> None:
        self.send_message(channel_id, "chat_id", text)

    def get_user_info(self, user_id: str) -> dict:
        try:
            data = self._request(
                "GET",
                f"/contact/v3/users/{user_id}",
                params={"user_id_type": "open_id"},
            )
            user = data.get("data", {}).get("user", {})
            return {
                "id": user_id,
                "name": user.get("name") or user.get("en_name") or user_id,
                "email": user.get("email", ""),
                "tz": user.get("city", "") or "Asia/Shanghai",
            }
        except Exception as exc:
            logger.debug("Could not fetch Feishu user info for %s: %s", user_id, exc)
            return {"id": user_id, "name": user_id, "email": "", "tz": "Asia/Shanghai"}

    def list_chat_members(self, chat_id: str) -> list[dict]:
        members: list[dict] = []
        page_token = ""
        while True:
            params = {"member_id_type": "open_id", "page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", f"/im/v1/chats/{chat_id}/members", params=params)
            body = data.get("data", {})
            members.extend(body.get("items", []))
            if not body.get("has_more"):
                return members
            page_token = body.get("page_token", "")

    def list_chats(self) -> list[dict]:
        chats: list[dict] = []
        page_token = ""
        while True:
            params = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", "/im/v1/chats", params=params)
            body = data.get("data", {})
            chats.extend(body.get("items", []))
            if not body.get("has_more"):
                return chats
            page_token = body.get("page_token", "")

    def get_platform(self) -> str:
        return "feishu"


def _to_plain_text(text: str) -> str:
    """Convert Slack-ish mrkdwn into readable Feishu text."""
    text = re.sub(r"<@([^>]+)>", r"\1", text or "")
    text = re.sub(r"<#([^>|]+)(?:\|[^>]+)?>", r"\1", text)
    text = re.sub(r"<(https?://[^>|]+)\|([^>]+)>", r"\2 (\1)", text)
    text = text.replace("*", "")
    text = text.replace("_", "")
    text = text.replace("`", "")
    return text.strip()
