"""Bootstrap a single internal Feishu workspace from environment variables."""

from __future__ import annotations

import json
import logging

from app_settings import get_setting

logger = logging.getLogger(__name__)


def feishu_enabled() -> bool:
    return bool(get_setting("FEISHU_APP_ID") and get_setting("FEISHU_APP_SECRET"))


def feishu_team_id() -> str:
    return get_setting("FEISHU_TEAM_ID") or get_setting("FEISHU_TENANT_KEY") or "feishu"


def _normalize_chat_id(chat_id: str | None) -> str | None:
    value = (chat_id or "").strip()
    if not value or value.lower() == "oc_demo":
        return None
    return value


def ensure_feishu_workspace() -> None:
    """Create/update the DB rows needed for scheduler startup.

    For internal deployments we do not need a Slack-style OAuth install flow.
    The app credentials and member list are configured via environment.
    """
    if not feishu_enabled():
        return

    try:
        import db  # noqa: PLC0415
    except Exception as exc:
        logger.warning("Feishu bootstrap skipped because DB is unavailable: %s", exc)
        return

    team_id = feishu_team_id()
    app_id = get_setting("FEISHU_APP_ID")
    team_name = get_setting("FEISHU_TEAM_NAME", "飞书工作区")

    try:
        db.save_installation(
            team_id=team_id,
            team_name=team_name,
            bot_token="feishu",
            bot_user_id=app_id,
            app_id=app_id,
            installed_by_user_id=get_setting("FEISHU_ADMIN_OPEN_ID", ""),
        )

        config: dict = {"channel_id": _normalize_chat_id(get_setting("FEISHU_DEFAULT_CHAT_ID"))}
        if get_setting("FEISHU_SCHEDULE_TIME"):
            config["schedule_time"] = get_setting("FEISHU_SCHEDULE_TIME")
        if get_setting("FEISHU_SCHEDULE_TZ"):
            config["schedule_tz"] = get_setting("FEISHU_SCHEDULE_TZ")
        if get_setting("FEISHU_SCHEDULE_DAYS"):
            config["schedule_days"] = get_setting("FEISHU_SCHEDULE_DAYS")
        if get_setting("FEISHU_QUESTIONS_JSON"):
            config["questions"] = json.loads(get_setting("FEISHU_QUESTIONS_JSON"))
        db.upsert_workspace_config(team_id, **config)
        for member in _parse_members(get_setting("FEISHU_STANDUP_MEMBERS", "")):
            db.upsert_member(team_id, **member)
        admin_open_id = get_setting("FEISHU_ADMIN_OPEN_ID", "").strip() or "admin"
        db.ensure_admin(team_id, admin_open_id)
        logger.info("Feishu workspace bootstrapped: %s", team_id)
    except Exception as exc:
        logger.warning("Feishu bootstrap failed: %s", exc)


def _parse_members(raw: str) -> list[dict]:
    """Parse FEISHU_STANDUP_MEMBERS.

    Format:
      ou_xxx
      ou_xxx|Alice
      ou_xxx|Alice|alice@example.com
    Multiple members are comma-separated.
    """
    members = []
    for item in raw.split(","):
        parts = [p.strip() for p in item.split("|")]
        if not parts or not parts[0]:
            continue
        members.append(
            {
                "user_id": parts[0],
                "real_name": parts[1] if len(parts) > 1 and parts[1] else None,
                "email": parts[2] if len(parts) > 2 and parts[2] else None,
                "tz": get_setting("FEISHU_SCHEDULE_TZ", "Asia/Shanghai"),
            }
        )
    return members


def parse_feishu_channels(raw: str | None = None) -> list[dict]:
    """Parse FEISHU_CHANNELS.

    Format:
      oc_xxx|Engineering,oc_yyy|Product
    """
    channels = []
    for item in (raw if raw is not None else get_setting("FEISHU_CHANNELS", "")).split(","):
        parts = [p.strip() for p in item.split("|")]
        chat_id = _normalize_chat_id(parts[0] if parts else "")
        if not chat_id:
            continue
        channels.append({"id": chat_id, "name": parts[1] if len(parts) > 1 and parts[1] else chat_id})
    return channels
