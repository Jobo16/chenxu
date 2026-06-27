"""Dashboard Flask blueprint — workspace configuration UI and API."""

from __future__ import annotations

import csv
import io
import ipaddress
import json
import logging
import os
import secrets
import zipfile
from functools import wraps
from urllib.parse import urlparse

import db
from app_settings import get_setting
from flask import (
    Blueprint,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from oauth import verify_login_token

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__, template_folder="templates")

_CLIENT_ID = os.environ.get("SLACK_CLIENT_ID", "")
_SCOPES = "channels:read,commands,groups:read,chat:write,im:history,im:read,im:write,users:read,users:read.email"

_SETTING_KEYS = {
    "APP_URL",
    "DASHBOARD_AUTH",
    "DASHBOARD_ADMIN_KEY",
    "FEISHU_EVENT_MODE",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_VERIFICATION_TOKEN",
    "FEISHU_TEAM_ID",
    "FEISHU_TEAM_NAME",
    "FEISHU_DEFAULT_CHAT_ID",
    "FEISHU_DEFAULT_CHAT_NAME",
    "FEISHU_CHANNELS",
    "FEISHU_ADMIN_OPEN_ID",
    "FEISHU_STANDUP_MEMBERS",
    "FEISHU_SCHEDULE_TIME",
    "FEISHU_SCHEDULE_TZ",
    "FEISHU_SCHEDULE_DAYS",
    "FEISHU_QUESTIONS_JSON",
    "FEISHU_AI_SUMMARY_ENABLED",
    "FEISHU_AI_PROVIDER",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
}
_SECRET_SETTING_KEYS = {
    "DASHBOARD_ADMIN_KEY",
    "FEISHU_APP_SECRET",
    "FEISHU_VERIFICATION_TOKEN",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
}
_SETTING_DEFAULTS = {
    "APP_URL": "http://localhost:3000",
    "DASHBOARD_AUTH": "none",
    "FEISHU_EVENT_MODE": "ws",
    "FEISHU_TEAM_ID": "feishu",
    "FEISHU_TEAM_NAME": "飞书工作区",
    "FEISHU_DEFAULT_CHAT_NAME": "进度群",
    "FEISHU_SCHEDULE_TIME": "09:30",
    "FEISHU_SCHEDULE_TZ": "Asia/Shanghai",
    "FEISHU_SCHEDULE_DAYS": "mon,tue,wed,thu,fri",
    "FEISHU_AI_SUMMARY_ENABLED": "false",
    "FEISHU_AI_PROVIDER": "openai",
    "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    "DEEPSEEK_MODEL": "deepseek-chat",
}

_FEISHU_TRANSPORT_KEYS = {
    "FEISHU_EVENT_MODE",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_VERIFICATION_TOKEN",
}

_SKILLS_PACKAGE_VERSION = "0.1.0"
_SKILLS_PACKAGE_FILENAME = f"chenxu-skills-{_SKILLS_PACKAGE_VERSION}.zip"


def _is_placeholder_feishu_chat_id(chat_id: str | None) -> bool:
    value = (chat_id or "").strip().lower()
    return not value or value == "oc_demo"


def _is_placeholder_feishu_member_id(user_id: str | None) -> bool:
    return (user_id or "").strip().lower() == "admin"


def _is_dashboard_system_user_id(user_id: str | None) -> bool:
    return _is_placeholder_feishu_member_id(user_id)


def _without_dashboard_system_users(rows: list[dict]) -> list[dict]:
    return [row for row in rows if not _is_dashboard_system_user_id(row.get("user_id"))]


def _add_feishu_channel(channels: dict[str, dict], chat_id: str | None, name: str | None = None) -> None:
    if _is_placeholder_feishu_chat_id(chat_id):
        return
    normalized_id = chat_id.strip()
    candidate_name = (name or normalized_id).strip() or normalized_id
    existing = channels.get(normalized_id)
    if existing:
        existing_name = (existing.get("name") or normalized_id).strip() or normalized_id
        if existing_name != normalized_id and candidate_name == normalized_id:
            return
        if existing_name != normalized_id and candidate_name != normalized_id:
            return
    channels[normalized_id] = {"id": normalized_id, "name": candidate_name}


def _is_safe_webhook_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname or ""
        if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False
        try:
            addr = ipaddress.ip_address(host)
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                return False
        except ValueError:
            pass  # hostname, not IP — allow it (DNS resolution at request time)
        return True
    except Exception:
        return False


def _is_feishu_enabled() -> bool:
    return bool(get_setting("FEISHU_APP_ID") and get_setting("FEISHU_APP_SECRET"))


def _feishu_team_id() -> str:
    return get_setting("FEISHU_TEAM_ID") or get_setting("FEISHU_TENANT_KEY") or "feishu"


def _is_feishu_session() -> bool:
    return _is_feishu_enabled() and session.get("team_id") == _feishu_team_id()


def _db_members_payload(team_id: str) -> list[dict]:
    rows = db.get_active_members(team_id)
    return [
        {
            "id": r["user_id"],
            "name": r.get("display_name_override") or r.get("real_name", "") or r["user_id"],
            "display_name": r.get("display_name_override") or r.get("real_name", "") or r["user_id"],
            "raw_name": r.get("real_name", "") or r["user_id"],
            "avatar": "",
            "email": r.get("email", ""),
            "tz": r.get("tz", "UTC"),
            "role": r.get("role", "member"),
            "tags": r.get("tags") or [],
        }
        for r in rows
    ]


def _normalise_member_tags(raw_tags) -> list[str]:
    if raw_tags is None:
        return []
    if isinstance(raw_tags, str):
        parts = raw_tags.replace("，", ",").split(",")
    elif isinstance(raw_tags, list):
        parts = raw_tags
    else:
        return []
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        value = str(part or "").strip()
        if not value:
            continue
        folded = value.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        deduped.append(value)
    return deduped[:12]


def _json_safe(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


def _progress_collection_request(data: dict) -> dict:
    days = data.get("schedule_days", ["mon", "tue", "wed", "thu", "fri"])
    return {
        "name": data.get("name") or "每日进度收集",
        "channel_id": data.get("channel_id") or "",
        "schedule_time": data.get("schedule_time") or "09:30",
        "schedule_tz": data.get("schedule_tz") or "Asia/Shanghai",
        "schedule_days": days,
        "questions": data.get(
            "questions",
            ["请按“项目 + 已完成/正在做 + 下一步 + 风险阻塞”的格式提交进度。"],
        ),
        "participants": data.get("participants") or [],
        "reminder_minutes": int(data.get("reminder_minutes") or 0),
        "active": bool(data.get("active", True)),
    }


def _publish_job_request(data: dict) -> dict:
    return {
        "name": data.get("name") or "定时发布",
        "destination_type": data.get("destination_type") or "feishu_channel",
        "destination": data.get("destination") or "",
        "schedule_time": data.get("schedule_time") or "18:00",
        "schedule_tz": data.get("schedule_tz") or "Asia/Shanghai",
        "schedule_days": data.get("schedule_days") or ["mon", "tue", "wed", "thu", "fri"],
        "range_days": int(data.get("range_days") or 1),
        "member_ids": data.get("member_ids") or [],
        "project_ids": data.get("project_ids") or [],
        "ai_summary_enabled": bool(data.get("ai_summary_enabled", True)),
        "ai_provider": data.get("ai_provider") or "deepseek",
        "ai_prompt": data.get("ai_prompt") or "",
        "active": bool(data.get("active", True)),
    }


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("team_id"):
            if _dashboard_auth_disabled():
                _login_internal_dashboard()
                return f(*args, **kwargs)
            if request.path.startswith("/dashboard/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("dashboard.login"))
        return f(*args, **kwargs)

    return wrapper


def _admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        team_id = session.get("team_id")
        user_id = session.get("user_id")
        if not team_id:
            return jsonify({"error": "Unauthorized"}), 401
        try:
            role = db.get_member_role(team_id, user_id or "")
            if role != "admin":
                return jsonify({"error": "Admin required"}), 403
        except Exception as exc:
            logger.warning("_admin_required DB error: %s", exc)
            return jsonify({"error": "Service unavailable"}), 503
        return f(*args, **kwargs)

    return wrapper


def _get_bot_token() -> str | None:
    team_id = session.get("team_id")
    if not team_id:
        return None
    try:
        inst = db.get_installation(team_id)
        return inst["bot_token"] if inst else None
    except Exception as exc:
        logger.warning("Could not get bot token: %s", exc)
        return None


def _normalise_setting_value(key: str, value) -> str:
    if key in {"FEISHU_AI_SUMMARY_ENABLED"}:
        return "true" if bool(value) and str(value).lower() not in {"false", "0", "off", "no"} else "false"
    return str(value or "").strip()


def _read_app_settings_payload() -> dict:
    try:
        saved = db.get_app_settings()
    except Exception:
        saved = {}

    values = {}
    secret_state = {}
    for key in sorted(_SETTING_KEYS):
        default = _SETTING_DEFAULTS.get(key, "")
        raw_value = saved[key] if key in saved else os.environ.get(key, default)
        if key in _SECRET_SETTING_KEYS:
            values[key] = ""
            secret_state[key] = bool(raw_value)
        else:
            values[key] = raw_value
    return {"values": values, "secret_set": secret_state}


def _refresh_feishu_transport(settings: dict[str, str]) -> None:
    if not any(key in _FEISHU_TRANSPORT_KEYS for key in settings):
        return
    try:
        from feishu_longconn import feishu_event_mode, feishu_longconn_service  # noqa: PLC0415

        feishu_longconn_service.stop()
        if _is_feishu_enabled() and feishu_event_mode() == "ws":
            feishu_longconn_service.start()
    except Exception as exc:
        logger.warning("Could not refresh Feishu transport: %s", exc)


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------


@dashboard_bp.route("/dashboard")
def dashboard():
    key = request.args.get("key", "")
    if key and _try_dashboard_key_login(key):
        return redirect(url_for("dashboard.dashboard"))

    # Accept one-time login token from OAuth redirect to bootstrap session
    token = request.args.get("t")
    if token:
        result = verify_login_token(token)
        if result:
            team_id, user_id = result
            session["team_id"] = team_id
            session["user_id"] = user_id
            try:
                inst = db.get_installation(team_id)
                session["team_name"] = inst["team_name"] if inst else team_id
            except Exception:
                session["team_name"] = team_id
            return redirect(url_for("dashboard.dashboard"))

    if not session.get("team_id"):
        if _dashboard_auth_disabled():
            _login_internal_dashboard()
        else:
            return redirect(url_for("dashboard.login"))

    if not session.get("team_id"):
        return redirect(url_for("dashboard.login"))

    team_id = session["team_id"]
    try:
        inst = db.get_installation(team_id)
        team_name = inst["team_name"] if inst else team_id
    except Exception:
        team_name = team_id
    return render_template("dashboard.html", team_name=team_name, team_id=team_id)


@dashboard_bp.route("/dashboard/login")
def login():
    if session.get("team_id"):
        return redirect(url_for("dashboard.dashboard"))
    if _dashboard_auth_disabled():
        _login_internal_dashboard()
        return redirect(url_for("dashboard.dashboard"))
    key = request.args.get("key", "")
    if key and _try_dashboard_key_login(key):
        return redirect(url_for("dashboard.dashboard"))
    if _dashboard_admin_key():
        return (
            "<h3>晨序 Dashboard 登录</h3>"
            "<p>打开 <code>/dashboard/login?key=你的访问密钥</code> 进入。</p>"
        )
    # Use /install which generates a proper HMAC state
    return redirect(url_for("oauth.install"))


@dashboard_bp.route("/dashboard/logout")
def logout():
    session.clear()
    return redirect(url_for("dashboard.login"))


def _dashboard_auth_disabled() -> bool:
    return get_setting("DASHBOARD_AUTH", "none").strip().lower() in {"", "none", "off", "false", "0"}


def _dashboard_admin_key() -> str:
    return get_setting("DASHBOARD_ADMIN_KEY") or get_setting("FEISHU_DASHBOARD_ADMIN_KEY")


def _try_dashboard_key_login(key: str) -> bool:
    expected = _dashboard_admin_key()
    if not expected or not secrets.compare_digest(key, expected):
        return False
    _login_internal_dashboard()
    return True


def _login_internal_dashboard() -> None:
    team_id = _feishu_team_id()
    user_id = get_setting("FEISHU_ADMIN_OPEN_ID", "").strip() or "admin"
    session["team_id"] = team_id
    session["user_id"] = user_id
    try:
        if _is_feishu_enabled():
            from feishu_bootstrap import ensure_feishu_workspace  # noqa: PLC0415

            ensure_feishu_workspace()
        inst = db.get_installation(team_id)
        session["team_name"] = inst["team_name"] if inst else get_setting("FEISHU_TEAM_NAME", team_id)
        db.ensure_admin(team_id, user_id)
    except Exception:
        session["team_name"] = get_setting("FEISHU_TEAM_NAME", team_id)


def _refresh_schedule_job(team_id: str, schedule: dict | None) -> None:
    if not schedule:
        return
    try:
        from scheduler import get_scheduler, register_schedule_job  # noqa: PLC0415

        inst = db.get_installation(team_id)
        sched_obj = get_scheduler()
        if not inst or not sched_obj:
            return
        if schedule.get("active", True):
            sched_with_token = dict(schedule)
            sched_with_token["bot_token"] = inst["bot_token"]
            register_schedule_job(sched_obj, sched_with_token)
        else:
            _remove_schedule_jobs(team_id, int(schedule["id"]))
    except Exception as exc:
        logger.warning("Could not refresh schedule job: %s", exc)


def _remove_schedule_jobs(team_id: str, schedule_id: int) -> None:
    try:
        from scheduler import get_scheduler  # noqa: PLC0415

        sched_obj = get_scheduler()
        if not sched_obj:
            return
        for prefix in ("schedule_", "reminder_schedule_", "weekend_reminder_schedule_", "report_schedule_"):
            try:
                sched_obj.remove_job(f"{prefix}{team_id}_{schedule_id}")
            except Exception:
                pass
    except Exception as exc:
        logger.warning("Could not remove schedule jobs: %s", exc)


# ---------------------------------------------------------------------------
# Standup config API
# Each standup_schedules row is one "standup".
# ---------------------------------------------------------------------------


def _schedule_to_standup(row: dict) -> dict:
    """Normalise a standup_schedules row into a standup API object."""
    questions = row.get("questions") or []
    if isinstance(questions, str):
        try:
            questions = json.loads(questions)
        except Exception:
            questions = []

    participants = row.get("participants") or []
    if isinstance(participants, str):
        try:
            participants = json.loads(participants)
        except Exception:
            participants = []

    raw_days = row.get("schedule_days") or "mon,tue,wed,thu,fri"
    schedule_days = raw_days.split(",") if isinstance(raw_days, str) else raw_days

    return {
        "id": row["id"],
        "name": row.get("name") or "Morning Standup",
        "channel_id": row.get("channel_id") or "",
        "schedule_time": row.get("schedule_time") or "09:00",
        "schedule_tz": row.get("schedule_tz") or "UTC",
        "schedule_days": schedule_days,
        "questions": questions,
        "active": row.get("active", True),
        "participants": participants,
        "reminder_minutes": int(row.get("reminder_minutes") or 0),
        # Extended fields — may not be present in all rows
        "report_channel": row.get("report_channel") or "",
        "report_time": row.get("report_time") or "",
        "group_by": row.get("group_by") or "member",
        "post_as": row.get("post_as") or "combined",
        "sort_order": row.get("sort_order") or "chronological",
        "edit_window": row.get("edit_window") or "report",
        "display_avatar": bool(row.get("display_avatar", True)),
        "jira_base_url": row.get("jira_base_url") or "",
        "zendesk_base_url": row.get("zendesk_base_url") or "",
        "github_repo": row.get("github_repo") or "",
        "linear_team": row.get("linear_team") or "",
        "ai_summary_enabled": bool(row.get("ai_summary_enabled", False)),
        "ai_provider": row.get("ai_provider") or "openai",
        "feed_token": row.get("feed_token") or "",
        "feed_public": bool(row.get("feed_public", False)),
        "manager_email": row.get("manager_email") or "",
        "manager_digest_enabled": bool(row.get("manager_digest_enabled", False)),
        "post_to_thread": bool(row.get("post_to_thread", False)),
        "notify_on_report": bool(row.get("notify_on_report", True)),
        "post_summary": bool(row.get("post_summary", False)),
    }


@dashboard_bp.route("/dashboard/api/standups", methods=["GET"])
@_login_required
def api_list_standups():
    team_id = session["team_id"]
    try:
        rows = db.get_standup_schedules(team_id)
        return jsonify([_schedule_to_standup(r) for r in rows])
    except Exception as exc:
        logger.error("api_list_standups error: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/standups", methods=["POST"])
@_login_required
def api_create_standup():
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    try:
        days = data.get("schedule_days", ["mon", "tue", "wed", "thu", "fri"])
        if isinstance(days, list):
            days = ",".join(days)
        row = db.create_standup_schedule(
            team_id,
            name=data.get("name", "Morning Standup"),
            channel_id=data.get("channel_id", ""),
            schedule_time=data.get("schedule_time", "09:00"),
            schedule_tz=data.get("schedule_tz", "UTC"),
            schedule_days=days,
            questions=data.get(
                "questions", ["What did you do yesterday?", "What are you doing today?", "Any blockers?"]
            ),
            participants=data.get("participants", []),
            active=data.get("active", True),
            reminder_minutes=int(data.get("reminder_minutes") or 0),
            post_to_thread=bool(data.get("post_to_thread", False)),
            notify_on_report=bool(data.get("notify_on_report", True)),
            post_summary=bool(data.get("post_summary", data.get("ai_summary_enabled", True))),
            report_time=data.get("report_time") or None,
            group_by=data.get("group_by", "member"),
            ai_summary_enabled=bool(data.get("ai_summary_enabled", False)),
            ai_provider=data.get("ai_provider", "openai"),
        )
        _refresh_schedule_job(team_id, row)
        return jsonify(_schedule_to_standup(row)), 201
    except Exception as exc:
        logger.error("api_create_standup error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/standups/<standup_id>", methods=["PUT"])
@_login_required
def api_update_standup(standup_id: str):
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    try:
        kwargs: dict = {}
        for field in (
            "name",
            "channel_id",
            "schedule_time",
            "schedule_tz",
            "questions",
            "participants",
            "active",
            "report_channel",
            "report_time",
            "group_by",
            "post_as",
            "sort_order",
            "edit_window",
            "display_avatar",
            "jira_base_url",
            "zendesk_base_url",
            "github_repo",
            "linear_team",
            "ai_provider",
            "feed_token",
            "feed_public",
            "manager_email",
        ):
            if field in data:
                kwargs[field] = data[field]
        if "schedule_days" in data:
            days = data["schedule_days"]
            kwargs["schedule_days"] = ",".join(days) if isinstance(days, list) else days
        if "reminder_minutes" in data:
            kwargs["reminder_minutes"] = int(data.get("reminder_minutes") or 0)
        if "ai_summary_enabled" in data:
            kwargs["ai_summary_enabled"] = bool(data["ai_summary_enabled"])
            kwargs.setdefault("post_summary", True)
        if "manager_digest_enabled" in data:
            kwargs["manager_digest_enabled"] = bool(data["manager_digest_enabled"])
        if "post_to_thread" in data:
            kwargs["post_to_thread"] = bool(data["post_to_thread"])
        if "notify_on_report" in data:
            kwargs["notify_on_report"] = bool(data["notify_on_report"])
        if "post_summary" in data:
            kwargs["post_summary"] = bool(data["post_summary"])
        row = db.update_standup_schedule(team_id, int(standup_id), **kwargs)
        if row:
            _refresh_schedule_job(team_id, row)
        return jsonify(_schedule_to_standup(row))
    except Exception as exc:
        logger.error("api_update_standup error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/standups/<standup_id>", methods=["DELETE"])
@_login_required
def api_delete_standup(standup_id: str):
    team_id = session["team_id"]
    try:
        db.delete_standup_schedule(team_id, int(standup_id))
        _remove_schedule_jobs(team_id, int(standup_id))
        return jsonify({"ok": True})
    except Exception as exc:
        logger.error("api_delete_standup error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Me / Role API
# ---------------------------------------------------------------------------


@dashboard_bp.route("/dashboard/api/me", methods=["GET"])
@_login_required
def api_me():
    team_id = session["team_id"]
    user_id = session.get("user_id", "")
    try:
        role = db.get_member_role(team_id, user_id)
    except Exception:
        role = "member"
    return jsonify(
        {
            "team_id": team_id,
            "user_id": user_id,
            "team_name": session.get("team_name", ""),
            "role": role,
        }
    )


@dashboard_bp.route("/dashboard/api/settings", methods=["GET"])
@_login_required
def api_get_settings():
    return jsonify(_read_app_settings_payload())


@dashboard_bp.route("/dashboard/api/settings", methods=["PUT"])
@_login_required
def api_update_settings():
    data = request.get_json(force=True) or {}
    incoming = data.get("settings", data)
    if not isinstance(incoming, dict):
        return jsonify({"error": "settings must be an object"}), 400

    settings: dict[str, str] = {}
    for key, value in incoming.items():
        if key not in _SETTING_KEYS:
            continue
        if key in _SECRET_SETTING_KEYS and value == "":
            continue
        settings[key] = _normalise_setting_value(key, value)

    clear_secrets = data.get("clear_secrets", [])
    if isinstance(clear_secrets, list):
        for key in clear_secrets:
            if key in _SECRET_SETTING_KEYS:
                settings[key] = ""

    try:
        db.set_app_settings(settings)
        if _is_feishu_enabled():
            from feishu_bootstrap import ensure_feishu_workspace  # noqa: PLC0415

            ensure_feishu_workspace()
        _refresh_feishu_transport(settings)
        return jsonify(_read_app_settings_payload())
    except Exception as exc:
        logger.error("api_update_settings error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/skills-package", methods=["GET"])
@_login_required
def api_skills_package():
    return jsonify(
        {
            "version": _SKILLS_PACKAGE_VERSION,
            "filename": _SKILLS_PACKAGE_FILENAME,
            "download_url": url_for("dashboard.api_download_skills_package"),
        }
    )


@dashboard_bp.route("/dashboard/api/skills-package/download", methods=["GET"])
@_login_required
def api_download_skills_package():
    manifest = {
        "name": "chenxu-progress",
        "version": _SKILLS_PACKAGE_VERSION,
        "description": "通过晨序控制台读取团队进度和数据看板。",
        "mcp_server": "/mcp",
    }
    skill_md = f"""# 晨序进度 Skill

版本：{_SKILLS_PACKAGE_VERSION}

这个包用于连接晨序控制台的 MCP 接口，让 AI 助手读取团队进度、成员和看板数据。

## 配置

1. 在晨序控制台配置飞书和 AI。
2. 使用控制台地址作为服务地址。
3. 使用管理员提供的访问凭证连接 MCP 服务。

## 能力

- 查询指定日期或时间范围内的进度记录。
- 查看项目、成员和数据看板汇总。
- 读取已确认入库的规范化进度内容。
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("chenxu-progress/manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("chenxu-progress/SKILL.md", skill_md)
    buffer.seek(0)
    return Response(
        buffer.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f"attachment; filename={_SKILLS_PACKAGE_FILENAME}"},
    )


# ---------------------------------------------------------------------------
# Progress product API
# ---------------------------------------------------------------------------


@dashboard_bp.route("/dashboard/api/data-board", methods=["GET"])
@_login_required
def api_data_board():
    team_id = session["team_id"]
    days = int(request.args.get("days", 7))
    try:
        return jsonify(_json_safe(db.get_data_board(team_id, days)))
    except Exception as exc:
        logger.error("api_data_board error: %s", exc)
        return jsonify(
            {
                "total_entries": 0,
                "active_members": 0,
                "active_projects": 0,
                "updated_today": 0,
                "by_project": [],
                "by_member": [],
                "by_date": [],
                "recent_entries": [],
            }
        )


@dashboard_bp.route("/dashboard/api/collections", methods=["GET"])
@_login_required
def api_list_collections():
    team_id = session["team_id"]
    try:
        return jsonify(_json_safe(db.get_progress_collections(team_id)))
    except Exception as exc:
        logger.error("api_list_collections error: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/collections", methods=["POST"])
@_login_required
def api_create_collection():
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    try:
        row = db.create_progress_collection(team_id, **_progress_collection_request(data))
        _refresh_schedule_job(team_id, {"team_id": team_id, **row})
        return jsonify(_json_safe(row)), 201
    except Exception as exc:
        logger.error("api_create_collection error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/collections/<int:collection_id>", methods=["PUT"])
@_login_required
def api_update_collection(collection_id: int):
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    try:
        row = db.update_progress_collection(team_id, collection_id, **_progress_collection_request(data))
        if not row:
            return jsonify({"error": "Not found"}), 404
        _refresh_schedule_job(team_id, {"team_id": team_id, **row})
        return jsonify(_json_safe(row))
    except Exception as exc:
        logger.error("api_update_collection error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/collections/<int:collection_id>", methods=["DELETE"])
@_login_required
def api_delete_collection(collection_id: int):
    team_id = session["team_id"]
    try:
        db.delete_progress_collection(team_id, collection_id)
        _remove_schedule_jobs(team_id, collection_id)
        return jsonify({"ok": True})
    except Exception as exc:
        logger.error("api_delete_collection error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/projects", methods=["GET"])
@_login_required
def api_list_projects():
    team_id = session["team_id"]
    try:
        return jsonify(_json_safe(db.get_projects(team_id)))
    except Exception as exc:
        logger.error("api_list_projects error: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/projects", methods=["POST"])
@_login_required
def api_create_project():
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "项目名称不能为空"}), 400
    try:
        return jsonify(_json_safe(db.upsert_project(team_id, name, data.get("description", ""), data.get("status", "active")))), 201
    except Exception as exc:
        logger.error("api_create_project error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/projects/<int:project_id>", methods=["PUT"])
@_login_required
def api_update_project(project_id: int):
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "项目名称不能为空"}), 400
    try:
        row = db.update_project(team_id, project_id, name, data.get("description", ""), data.get("status", "active"))
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(_json_safe(row))
    except Exception as exc:
        logger.error("api_update_project error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/progress", methods=["GET"])
@_login_required
def api_list_progress():
    team_id = session["team_id"]
    try:
        rows = db.get_progress_entries(
            team_id,
            from_date=request.args.get("date_from") or None,
            to_date=request.args.get("date_to") or None,
            user_id=request.args.get("user_id") or None,
            project_id=int(request.args["project_id"]) if request.args.get("project_id") else None,
        )
        return jsonify(_json_safe(rows))
    except Exception as exc:
        logger.error("api_list_progress error: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/progress", methods=["POST"])
@_login_required
def api_create_progress():
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    user_id = data.get("user_id") or session.get("user_id", "")
    if not user_id:
        return jsonify({"error": "成员不能为空"}), 400
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "进度内容不能为空"}), 400
    try:
        entry_id = db.save_progress_entry(
            team_id=team_id,
            user_id=user_id,
            project_id=data.get("project_id"),
            role=data.get("role") or "",
            progress_date=data.get("progress_date") or None,
            content=content,
            source="dashboard",
        )
        return jsonify(_json_safe(db.get_progress_entry(team_id, int(entry_id)))), 201
    except Exception as exc:
        logger.error("api_create_progress error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/progress/<int:entry_id>", methods=["PUT"])
@_login_required
def api_update_progress(entry_id: int):
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    try:
        row = db.update_progress_entry(team_id, entry_id, created_by=session.get("user_id", ""), **data)
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(_json_safe(row))
    except Exception as exc:
        logger.error("api_update_progress error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/progress/<int:entry_id>/snapshots", methods=["GET"])
@_login_required
def api_progress_snapshots(entry_id: int):
    team_id = session["team_id"]
    try:
        return jsonify(_json_safe(db.get_progress_snapshots(team_id, entry_id)))
    except Exception as exc:
        logger.error("api_progress_snapshots error: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/publish-jobs", methods=["GET"])
@_login_required
def api_list_publish_jobs():
    team_id = session["team_id"]
    try:
        return jsonify(_json_safe(db.get_publish_jobs(team_id)))
    except Exception as exc:
        logger.error("api_list_publish_jobs error: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/publish-jobs", methods=["POST"])
@_login_required
def api_create_publish_job():
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    try:
        return jsonify(_json_safe(db.create_publish_job(team_id, **_publish_job_request(data)))), 201
    except Exception as exc:
        logger.error("api_create_publish_job error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/publish-jobs/<int:job_id>", methods=["PUT"])
@_login_required
def api_update_publish_job(job_id: int):
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    try:
        row = db.update_publish_job(team_id, job_id, **_publish_job_request(data))
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(_json_safe(row))
    except Exception as exc:
        logger.error("api_update_publish_job error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/publish-jobs/<int:job_id>", methods=["DELETE"])
@_login_required
def api_delete_publish_job(job_id: int):
    team_id = session["team_id"]
    try:
        db.delete_publish_job(team_id, job_id)
        return jsonify({"ok": True})
    except Exception as exc:
        logger.error("api_delete_publish_job error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/members/<user_id>/role", methods=["PUT"])
@_login_required
@_admin_required
def api_set_member_role(user_id: str):
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    role = data.get("role", "member")
    try:
        db.set_member_role(team_id, user_id, role)
        return jsonify({"ok": True, "user_id": user_id, "role": role})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/members/<user_id>", methods=["PUT"])
@_login_required
@_admin_required
def api_update_member_profile(user_id: str):
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    display_name_override = data.get("display_name_override")
    tags = _normalise_member_tags(data.get("tags"))
    try:
        db.update_member_profile(
            team_id,
            user_id,
            display_name_override="" if display_name_override is None else str(display_name_override),
            tags=tags,
        )
        return jsonify(
            {
                "ok": True,
                "user_id": user_id,
                "display_name_override": str(display_name_override or "").strip(),
                "tags": tags,
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Members API
# ---------------------------------------------------------------------------


@dashboard_bp.route("/dashboard/api/members", methods=["GET"])
@_login_required
def api_members():
    team_id = session["team_id"]
    if _is_feishu_session():
        channel_id = request.args.get("channel_id")
        if not channel_id:
            channel_id = get_setting("FEISHU_DEFAULT_CHAT_ID", "").strip()
        if _is_placeholder_feishu_chat_id(channel_id):
            channel_id = ""
        if channel_id:
            try:
                from adapters.feishu_adapter import FeishuAdapter  # noqa: PLC0415

                adapter = FeishuAdapter()
                for member in adapter.list_chat_members(channel_id):
                    member_id = member.get("member_id") or member.get("open_id") or member.get("user_id")
                    if not member_id:
                        continue
                    db.upsert_member(
                        team_id=team_id,
                        user_id=member_id,
                        real_name=member.get("name") or member.get("member_id") or member_id,
                        tz=get_setting("FEISHU_SCHEDULE_TZ", "Asia/Shanghai"),
                    )
            except Exception as exc:
                logger.warning("Could not sync Feishu channel members for %s: %s", channel_id, exc)
        try:
            members = [member for member in _db_members_payload(team_id) if not _is_placeholder_feishu_member_id(member["id"])]
            return jsonify(members)
        except Exception:
            return jsonify([])

    token = _get_bot_token()
    if not token:
        return jsonify([])

    # Build role map from DB
    role_map: dict[str, str] = {}
    profile_map: dict[str, dict] = {}
    try:
        db_members = db.get_active_members(team_id)
        for r in db_members:
            role_map[r["user_id"]] = r.get("role", "member")
            profile_map[r["user_id"]] = {
                "display_name_override": r.get("display_name_override") or "",
                "real_name": r.get("real_name") or "",
                "tags": r.get("tags") or [],
            }
    except Exception as e:
        logger.warning("Unexpected error in api_members loading role map: %s", e)

    channel_id = request.args.get("channel_id")

    try:
        from slack_sdk import WebClient  # noqa: PLC0415

        client = WebClient(token=token)

        # If channel_id provided, fetch only that channel's members
        channel_member_ids = None
        if channel_id:
            channel_member_ids = set()
            cursor = None
            while True:
                resp = client.conversations_members(channel=channel_id, limit=500, cursor=cursor or "")
                channel_member_ids.update(resp.get("members", []))
                cursor = resp.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

        # Paginate through all workspace users
        all_users = []
        cursor = None
        while True:
            result = client.users_list(limit=200, cursor=cursor or "")
            all_users.extend(result.get("members", []))
            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        members = []
        for u in all_users:
            if u.get("deleted") or u.get("is_bot") or u.get("id") == "USLACKBOT":
                continue
            uid = u["id"]
            if channel_member_ids is not None and uid not in channel_member_ids:
                continue
            profile = u.get("profile", {})
            stored = profile_map.get(uid, {})
            resolved_name = (
                stored.get("display_name_override")
                or profile.get("real_name")
                or u.get("name", "")
                or uid
            )
            members.append(
                {
                    "id": uid,
                    "name": resolved_name,
                    "display_name": resolved_name,
                    "raw_name": profile.get("real_name") or stored.get("real_name") or u.get("name", "") or uid,
                    "avatar": profile.get("image_48", ""),
                    "email": profile.get("email", ""),
                    "tz": u.get("tz", "UTC"),
                    "role": role_map.get(uid, "member"),
                    "tags": stored.get("tags") or [],
                }
            )
        return jsonify(members)
    except Exception as exc:
        logger.error("api_members error: %s", exc)
        # Fall back to DB members
        try:
            return jsonify(_db_members_payload(team_id))
        except Exception:
            return jsonify([])


@dashboard_bp.route("/dashboard/api/members/invite", methods=["POST"])
@_login_required
@_admin_required
def api_invite_admin():
    """Look up or add a user and grant them a role."""
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    user_id = data.get("user_id", "").strip()
    role = data.get("role", "admin")
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    if _is_feishu_session():
        try:
            db.upsert_member(
                team_id=team_id,
                user_id=user_id,
                real_name=data.get("name") or user_id,
                email=data.get("email") or "",
                tz=data.get("tz") or get_setting("FEISHU_SCHEDULE_TZ", "Asia/Shanghai"),
            )
            db.set_member_role(team_id, user_id, role)
            return jsonify({"ok": True, "user_id": user_id, "role": role, "name": data.get("name") or user_id})
        except Exception as exc:
            logger.error("api_invite_admin feishu error: %s", exc)
            return jsonify({"error": str(exc)}), 500

    token = _get_bot_token()
    if not token:
        return jsonify({"error": "No bot token"}), 500
    try:
        from slack_sdk import WebClient  # noqa: PLC0415

        client = WebClient(token=token)
        info = client.users_info(user=user_id)
        u = info["user"]
        profile = u.get("profile", {})
        db.upsert_member(
            team_id=team_id,
            user_id=user_id,
            real_name=profile.get("real_name") or u.get("name", ""),
            email=profile.get("email", ""),
            tz=u.get("tz", "UTC"),
        )
        db.set_member_role(team_id, user_id, role)
        return jsonify(
            {"ok": True, "user_id": user_id, "role": role, "name": profile.get("real_name") or u.get("name", "")}
        )
    except Exception as exc:
        logger.error("api_invite_admin error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Channels API (helper for dropdowns)
# ---------------------------------------------------------------------------


@dashboard_bp.route("/dashboard/api/channels", methods=["GET"])
@_login_required
def api_channels():
    team_id = session.get("team_id", "")
    if _is_feishu_session():
        channels: dict[str, dict] = {}
        try:
            from adapters.feishu_adapter import FeishuAdapter  # noqa: PLC0415

            adapter = FeishuAdapter()
            for chat in adapter.list_chats():
                _add_feishu_channel(channels, chat.get("chat_id"), chat.get("name"))
        except Exception as exc:
            logger.warning("api_channels feishu remote list error: %s", exc)
        default_chat_id = get_setting("FEISHU_DEFAULT_CHAT_ID", "").strip()
        if default_chat_id:
            _add_feishu_channel(channels, default_chat_id, get_setting("FEISHU_DEFAULT_CHAT_NAME", "站会"))
        try:
            from feishu_bootstrap import parse_feishu_channels  # noqa: PLC0415

            for c in parse_feishu_channels():
                _add_feishu_channel(channels, c["id"], c.get("name"))
        except Exception:
            pass
        try:
            config = db.get_workspace_config(team_id) or {}
            if config.get("channel_id"):
                _add_feishu_channel(channels, config["channel_id"], config["channel_id"])
            for sched in db.get_standup_schedules(team_id):
                if sched.get("channel_id"):
                    _add_feishu_channel(channels, sched["channel_id"], sched.get("name") or sched["channel_id"])
                if sched.get("report_channel"):
                    _add_feishu_channel(channels, sched["report_channel"], sched["report_channel"])
        except Exception as exc:
            logger.warning("api_channels feishu DB fallback error: %s", exc)
        return jsonify(sorted(channels.values(), key=lambda c: c["name"]))

    token = _get_bot_token()
    if not token:
        logger.warning("api_channels: no bot token found for team %s", session.get("team_id"))
        return jsonify([])
    try:
        from slack_sdk import WebClient  # noqa: PLC0415

        client = WebClient(token=token)
        channels = []
        cursor = None
        while True:
            kwargs = {"types": "public_channel,private_channel", "exclude_archived": True, "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            result = client.users_conversations(**kwargs)
            for c in result.get("channels", []):
                channels.append({"id": c["id"], "name": c["name"]})
            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        return jsonify(sorted(channels, key=lambda c: c["name"]))
    except Exception as exc:
        logger.error("api_channels error: %s", exc)
        return jsonify([])


# ---------------------------------------------------------------------------
# Stats API
# ---------------------------------------------------------------------------


@dashboard_bp.route("/dashboard/api/stats", methods=["GET"])
@_login_required
def api_stats():
    team_id = session["team_id"]
    try:
        stats = db.get_dashboard_stats(team_id)
        return jsonify(stats)
    except Exception as exc:
        logger.warning("api_stats error: %s", exc)
        return jsonify(
            {
                "completion_rate": 0,
                "active_members": 0,
                "total_responses": 0,
                "responses_this_week": 0,
            }
        )


@dashboard_bp.route("/dashboard/api/reports", methods=["GET"])
@_login_required
def api_reports():
    """Return standup history with participation stats, filterable by date/member."""
    team_id = session["team_id"]
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    user_id_filter = request.args.get("user_id")
    try:
        standups = db.get_standups(
            team_id,
            from_date=date_from or None,
            to_date=date_to or None,
            days=30,
        )
        standups = _without_dashboard_system_users(standups)
        if user_id_filter:
            standups = [s for s in standups if s.get("user_id") == user_id_filter]

        days = 7
        if date_from:
            try:
                from datetime import datetime as _dt

                d = _dt.fromisoformat(date_from)
                days = max(1, (_dt.utcnow() - d).days + 1)
            except Exception as e:
                logger.warning("Unexpected error in api_reports parsing date_from: %s", e)
        participation = _without_dashboard_system_users(db.get_participation_stats(team_id, days=days))
        total_days = days

        member_summary = []
        for p in participation:
            responses = int(p.get("responses") or 0)
            rate = min(5, round((responses / max(1, total_days)) * 5))
            member_summary.append(
                {
                    "user_id": p.get("user_id", ""),
                    "name": p.get("real_name") or p.get("user_id", ""),
                    "responses": responses,
                    "total": total_days,
                    "stars": rate,
                }
            )

        return jsonify(
            {
                "standups": standups,
                "participation": member_summary,
                "total_days": total_days,
            }
        )
    except Exception as exc:
        logger.error("api_reports error: %s", exc)
        return jsonify({"standups": [], "participation": [], "total_days": 7})


# ---------------------------------------------------------------------------
# Webhooks API
# ---------------------------------------------------------------------------


@dashboard_bp.route("/dashboard/api/webhooks", methods=["GET"])
@_login_required
def api_list_webhooks():
    team_id = session["team_id"]
    try:
        hooks = db.get_webhooks(team_id)
        return jsonify(hooks)
    except Exception as exc:
        logger.warning("api_list_webhooks error: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/webhooks", methods=["POST"])
@_login_required
def api_add_webhook():
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    url_val = data.get("url", "").strip()
    if not url_val:
        return jsonify({"error": "url is required"}), 400
    if not _is_safe_webhook_url(url_val):
        return jsonify({"error": "Invalid or unsafe webhook URL"}), 400
    try:
        hook = db.add_webhook(team_id, url_val)
        return jsonify(hook), 201
    except Exception as exc:
        logger.error("api_add_webhook error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/webhooks/<hook_id>", methods=["DELETE"])
@_login_required
def api_delete_webhook(hook_id: str):
    team_id = session["team_id"]
    try:
        db.delete_webhook(team_id, int(hook_id))
        return jsonify({"ok": True})
    except Exception as exc:
        logger.error("api_delete_webhook error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Analytics API
# ---------------------------------------------------------------------------


@dashboard_bp.route("/dashboard/api/analytics", methods=["GET"])
@_login_required
def api_analytics():
    team_id = session["team_id"]
    days = int(request.args.get("days", 7))
    try:
        stats = _without_dashboard_system_users(db.get_participation_stats(team_id, days))
        for row in stats:
            if row.get("last_standup"):
                row["last_standup"] = row["last_standup"].isoformat()
            row["responses"] = int(row.get("responses") or 0)
            row["days_with_blockers"] = int(row.get("days_with_blockers") or 0)
        return jsonify(stats)
    except Exception as exc:
        logger.error("api_analytics error: %s", exc)
        return jsonify([])


# ---------------------------------------------------------------------------
# Kudos API
# ---------------------------------------------------------------------------


@dashboard_bp.route("/dashboard/api/kudos", methods=["GET"])
@_login_required
def api_list_kudos():
    team_id = session["team_id"]
    limit = int(request.args.get("limit", 50))
    try:
        kudos = db.get_kudos(team_id, limit)
        for k in kudos:
            if k.get("created_at"):
                k["created_at"] = k["created_at"].isoformat()
        return jsonify(kudos)
    except Exception as exc:
        logger.warning("api_list_kudos: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/kudos/leaderboard", methods=["GET"])
@_login_required
def api_kudos_leaderboard():
    team_id = session["team_id"]
    days = int(request.args.get("days", 30))
    try:
        board = db.get_kudos_leaderboard(team_id, days)
        for row in board:
            if row.get("last_kudos"):
                row["last_kudos"] = row["last_kudos"].isoformat()
            row["received"] = int(row.get("received") or 0)
        return jsonify(board)
    except Exception as exc:
        logger.warning("api_kudos_leaderboard: %s", exc)
        return jsonify([])


# ---------------------------------------------------------------------------
# CSV Export API
# ---------------------------------------------------------------------------
@dashboard_bp.route("/dashboard/api/export/csv", methods=["GET"])
@_login_required
def api_export_csv():
    team_id = session["team_id"]
    from_date = request.args.get("from")
    to_date = request.args.get("to")
    try:
        rows = db.get_progress_entries(team_id, from_date=from_date, to_date=to_date)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "progress_date",
            "user_id",
            "member_name",
            "project_name",
            "role",
            "content",
            "submitted_at",
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "progress_date": row.get("progress_date", ""),
                "user_id": row.get("user_id", ""),
                "member_name": row.get("member_name", ""),
                "project_name": row.get("project_name", ""),
                "role": row.get("role", ""),
                "content": row.get("content", ""),
                "submitted_at": row.get("submitted_at", ""),
            }
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=progress-{team_id}.csv"},
    )


# ── Templates API ──────────────────────────────────────────────────────────


@dashboard_bp.route("/dashboard/api/templates", methods=["GET"])
@_login_required
def api_templates():
    from templates_library import TEMPLATES  # noqa: PLC0415

    return jsonify(TEMPLATES)


# ── Standup Schedules API ───────────────────────────────────────────────────


@dashboard_bp.route("/dashboard/api/schedules", methods=["GET"])
@_login_required
def api_list_schedules():
    team_id = session["team_id"]
    try:
        schedules = db.get_standup_schedules(team_id)
        return jsonify(schedules)
    except Exception as exc:
        logger.error("api_list_schedules: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/schedules", methods=["POST"])
@_login_required
def api_create_schedule():
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    try:
        days = data.get("schedule_days", ["mon", "tue", "wed", "thu", "fri"])
        if isinstance(days, list):
            days = ",".join(days)
        schedule = db.create_standup_schedule(
            team_id,
            name=data.get("name", "Daily Standup"),
            channel_id=data.get("channel_id", ""),
            schedule_time=data.get("schedule_time", "09:00"),
            schedule_tz=data.get("schedule_tz", "UTC"),
            schedule_days=days,
            questions=data.get(
                "questions", ["What did you complete yesterday?", "What are you working on today?", "Any blockers?"]
            ),
            participants=data.get("participants", []),
            reminder_minutes=int(data.get("reminder_minutes") or 0),
            active=data.get("active", True),
            post_to_thread=bool(data.get("post_to_thread", False)),
            notify_on_report=bool(data.get("notify_on_report", True)),
            weekend_reminder=bool(data.get("weekend_reminder", False)),
            post_summary=bool(data.get("post_summary", data.get("ai_summary_enabled", True))),
            report_channel=data.get("report_channel") or None,
            report_time=data.get("report_time") or None,
            group_by=data.get("group_by", "member"),
            ai_summary_enabled=bool(data.get("ai_summary_enabled", False)),
            ai_provider=data.get("ai_provider", "openai"),
        )
        _refresh_schedule_job(team_id, schedule)
        return jsonify(schedule), 201
    except Exception as exc:
        logger.error("api_create_schedule: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/schedules/<int:schedule_id>", methods=["PUT"])
@_login_required
def api_update_schedule(schedule_id: int):
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    try:
        days = data.get("schedule_days")
        if isinstance(days, list):
            days = ",".join(days)
        kwargs: dict = {}
        for field in (
            "name",
            "channel_id",
            "schedule_time",
            "schedule_tz",
            "reminder_minutes",
            "active",
            "questions",
            "participants",
            "report_channel",
            "report_time",
            "group_by",
            "ai_provider",
        ):
            if field in data:
                kwargs[field] = data[field]
        if days is not None:
            kwargs["schedule_days"] = days
        if "post_to_thread" in data:
            kwargs["post_to_thread"] = bool(data["post_to_thread"])
        if "notify_on_report" in data:
            kwargs["notify_on_report"] = bool(data["notify_on_report"])
        if "weekend_reminder" in data:
            kwargs["weekend_reminder"] = bool(data["weekend_reminder"])
        if "post_summary" in data:
            kwargs["post_summary"] = bool(data["post_summary"])
        if "ai_summary_enabled" in data:
            kwargs["ai_summary_enabled"] = bool(data["ai_summary_enabled"])
            kwargs.setdefault("post_summary", True)
        if "sync_with_channel" in data:
            kwargs["sync_with_channel"] = bool(data["sync_with_channel"])
        schedule = db.update_standup_schedule(team_id, schedule_id, **kwargs)
        if not schedule:
            return jsonify({"error": "Not found"}), 404
        _refresh_schedule_job(team_id, schedule)
        return jsonify(schedule)
    except Exception as exc:
        logger.error("api_update_schedule: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/schedules/<int:schedule_id>", methods=["DELETE"])
@_login_required
def api_delete_schedule(schedule_id: int):
    team_id = session["team_id"]
    try:
        db.delete_standup_schedule(team_id, schedule_id)
        _remove_schedule_jobs(team_id, schedule_id)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Workflow Rules API ──────────────────────────────────────────────────────


@dashboard_bp.route("/dashboard/api/rules", methods=["GET"])
@_login_required
def api_list_rules():
    team_id = session["team_id"]
    try:
        from workflow import get_rules  # noqa: PLC0415

        rules = get_rules(team_id)
        return jsonify(rules)
    except Exception as exc:
        logger.error("api_list_rules: %s", exc)
        return jsonify([])


@dashboard_bp.route("/dashboard/api/rules", methods=["POST"])
@_login_required
def api_create_rule():
    team_id = session["team_id"]
    data = request.get_json(force=True) or {}
    try:
        from workflow import save_rule  # noqa: PLC0415

        rule_id = save_rule(
            team_id=team_id,
            name=data.get("name", ""),
            trigger=data.get("trigger", ""),
            condition_value=data.get("condition_value") or None,
            action=data.get("action", ""),
            action_target=data.get("action_target", ""),
            action_message=data.get("action_message") or None,
        )
        if rule_id is None:
            return jsonify({"error": "Could not save rule"}), 500
        return jsonify({"id": rule_id}), 201
    except Exception as exc:
        logger.error("api_create_rule: %s", exc)
        return jsonify({"error": str(exc)}), 500


@dashboard_bp.route("/dashboard/api/rules/<int:rule_id>", methods=["DELETE"])
@_login_required
def api_delete_rule(rule_id: int):
    team_id = session["team_id"]
    try:
        from workflow import delete_rule  # noqa: PLC0415

        delete_rule(rule_id, team_id)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Public Feed ─────────────────────────────────────────────────────────────


@dashboard_bp.route("/feed/<token>")
def public_feed(token: str):
    from datetime import date  # noqa: PLC0415

    config = db.get_workspace_by_feed_token(token)
    if not config or not config.get("feed_public"):
        return "<h2>Feed not found or not public.</h2>", 404
    team_id = config["team_id"]
    entries = db.get_progress_entries(team_id, days=1)
    today = date.today().strftime("%A, %B %-d, %Y")
    return render_template("feed.html", entries=entries, config=config, today=today)


@dashboard_bp.route("/dashboard/api/feed-token", methods=["POST"])
@_login_required
def api_generate_feed_token():
    team_id = session["team_id"]
    token = secrets.token_urlsafe(24)
    db.upsert_workspace_config(team_id, feed_token=token, feed_public=True)
    app_url = get_setting("APP_URL", "http://localhost:3000")
    return jsonify({"token": token, "url": f"{app_url}/feed/{token}"})


@dashboard_bp.route("/dashboard/api/feed-token", methods=["DELETE"])
@_login_required
def api_disable_feed():
    team_id = session["team_id"]
    db.upsert_workspace_config(team_id, feed_public=False)
    return jsonify({"ok": True})


@dashboard_bp.route("/dashboard/api/mcp-config")
@_login_required
def api_mcp_config():
    team_id = session["team_id"]
    app_url = get_setting("APP_URL", "http://localhost:3000")
    return jsonify(
        {
            "team_id": team_id,
            "app_url": app_url,
            "mcp_server_path": "app/src/mcp_server.py",
            "docs_url": "https://docs.morgenruf.dev/mcp.html",
        }
    )


# ── MCP API Key management ───────────────────────────────────────────────────


@dashboard_bp.route("/dashboard/api/mcp/keys", methods=["GET"])
@_login_required
def api_get_mcp_keys():
    team_id = session["team_id"]
    try:
        keys = db.get_mcp_keys(team_id)
        return jsonify({"keys": keys})
    except Exception as exc:
        logger.warning("api_get_mcp_keys error: %s", exc)
        return jsonify({"keys": []})


@dashboard_bp.route("/dashboard/api/mcp/keys", methods=["POST"])
@_login_required
def api_create_mcp_key():
    team_id = session["team_id"]
    name = request.json.get("name", "Default") if request.json else "Default"
    key = db.generate_mcp_key(team_id, name)
    return jsonify({"key": key, "message": "Save this key — it won't be shown again!"})


@dashboard_bp.route("/dashboard/api/mcp/keys/<int:key_id>", methods=["DELETE"])
@_login_required
def api_revoke_mcp_key(key_id: int):
    team_id = session["team_id"]
    db.revoke_mcp_key(key_id, team_id)
    return jsonify({"ok": True})
