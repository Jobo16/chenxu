"""Database module — PostgreSQL connection pool and query helpers."""

from __future__ import annotations

import json
import logging
import os
import re
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)

_pool = None

try:
    import psycopg2
    import psycopg2.extras
    from psycopg2.pool import ThreadedConnectionPool

    _DATABASE_URL = os.environ.get("DATABASE_URL", "")
    if _DATABASE_URL:
        _pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=_DATABASE_URL)
        logger.info("PostgreSQL connection pool initialised")
    else:
        logger.warning("DATABASE_URL not set — database features disabled")
except ImportError:
    logger.warning("psycopg2 not installed — database features disabled")
except Exception as exc:  # noqa: BLE001
    logger.warning("Could not initialise DB pool: %s", exc)


def get_conn():
    """Borrow a connection from the pool."""
    if _pool is None:
        raise RuntimeError("Database pool not initialised")
    return _pool.getconn()


def release_conn(conn) -> None:
    """Return a connection to the pool."""
    if _pool is not None:
        _pool.putconn(conn)


@contextmanager
def db_conn() -> Generator[Any, None, None]:
    """Context manager that borrows and auto-returns a DB connection."""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_conn(conn)


# ---------------------------------------------------------------------------
# Installations
# ---------------------------------------------------------------------------


def save_installation(
    team_id: str,
    team_name: str,
    bot_token: str,
    bot_user_id: str,
    app_id: str,
    installed_by_user_id: str | None = None,
    bot_refresh_token: str | None = None,
    bot_token_expires_at: str | None = None,
) -> bool:
    """Insert or update an OAuth installation record. Returns True if this is a new installation."""
    sql = """
        INSERT INTO installations (team_id, team_name, bot_token, bot_user_id, app_id,
            installed_by_user_id, bot_refresh_token, bot_token_expires_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (team_id) DO UPDATE SET
            team_name = EXCLUDED.team_name,
            bot_token = EXCLUDED.bot_token,
            bot_user_id = EXCLUDED.bot_user_id,
            app_id = EXCLUDED.app_id,
            installed_by_user_id = EXCLUDED.installed_by_user_id,
            bot_refresh_token = EXCLUDED.bot_refresh_token,
            bot_token_expires_at = EXCLUDED.bot_token_expires_at,
            updated_at = NOW()
        RETURNING (xmax = 0) AS is_new
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    team_id,
                    team_name,
                    bot_token,
                    bot_user_id,
                    app_id,
                    installed_by_user_id,
                    bot_refresh_token,
                    bot_token_expires_at,
                ),
            )
            row = cur.fetchone()
            is_new = bool(row[0]) if row else False
    logger.info("Saved installation for team %s (%s) (new=%s)", team_id, team_name, is_new)
    return is_new


def get_installation(team_id: str) -> dict | None:
    """Return installation row as a dict, or None."""
    sql = "SELECT * FROM installations WHERE team_id = %s"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def get_all_installations() -> list[dict]:
    """Return all installation rows."""
    sql = "SELECT * FROM installations ORDER BY installed_at"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Workspace config
# ---------------------------------------------------------------------------


def upsert_workspace_config(team_id: str, **kwargs: Any) -> None:
    """Insert or update workspace config. Pass only columns you want to set."""
    allowed = {
        "channel_id",
        "schedule_time",
        "schedule_tz",
        "schedule_days",
        "questions",
        "active",
        "reminder_minutes",
        "edit_window_hours",
        "jira_base_url",
        "github_repo",
        "linear_team",
        "ai_summary_enabled",
        "ai_provider",
        "feed_token",
        "feed_public",
        "manager_email",
        "manager_digest_enabled",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    for col in fields:
        if not re.match(r"^[a-z_]+$", col):
            raise ValueError(f"Invalid column name: {col}")

    if not fields:
        # Insert with defaults only
        sql = """
            INSERT INTO workspace_config (team_id) VALUES (%s)
            ON CONFLICT DO NOTHING
        """
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (team_id,))
        return

    set_clause = ", ".join(f"{k} = %s" for k in fields)
    set_clause += ", updated_at = NOW()"
    values = list(fields.values())

    # Serialise questions list to JSON if needed
    if "questions" in fields and isinstance(fields["questions"], list):
        idx = list(fields.keys()).index("questions")
        values[idx] = json.dumps(fields["questions"])

    sql = f"""
        INSERT INTO workspace_config (team_id, {", ".join(fields.keys())}, updated_at)
        VALUES (%s, {", ".join(["%s"] * len(fields))}, NOW())
        ON CONFLICT (team_id) DO UPDATE SET {set_clause}
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [team_id] + values + values)


def get_workspace_config(team_id: str) -> dict | None:
    """Return workspace config row, or None."""
    sql = "SELECT * FROM workspace_config WHERE team_id = %s"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def get_workspace_by_feed_token(token: str) -> dict | None:
    """Return workspace_config row matching feed_token, or None."""
    sql = "SELECT * FROM workspace_config WHERE feed_token = %s"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (token,))
            row = cur.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# App settings
# ---------------------------------------------------------------------------


def get_app_setting(key: str) -> str | None:
    """Return a Dashboard-managed app setting value."""
    sql = "SELECT setting_value FROM app_settings WHERE setting_key = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (key,))
            row = cur.fetchone()
    return row[0] if row else None


def get_app_settings() -> dict[str, str]:
    """Return all Dashboard-managed app settings."""
    sql = "SELECT setting_key, setting_value FROM app_settings ORDER BY setting_key"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return {r["setting_key"]: r["setting_value"] for r in rows}


def set_app_settings(settings: dict[str, str]) -> None:
    """Upsert Dashboard-managed app settings."""
    if not settings:
        return
    sql = """
        INSERT INTO app_settings (setting_key, setting_value, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (setting_key) DO UPDATE SET
            setting_value = EXCLUDED.setting_value,
            updated_at = NOW()
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            for key, value in settings.items():
                cur.execute(sql, (key, value))


def get_standups(
    team_id: str,
    days: int = 1,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """Return standup submissions.

    If *from_date* / *to_date* (YYYY-MM-DD strings) are provided they take
    priority over *days*.  Otherwise the last *days* days are returned.
    """
    if from_date or to_date:
        conditions = ["s.team_id = %s"]
        params: list = [team_id]
        if from_date:
            conditions.append("s.standup_date >= %s")
            params.append(from_date)
        if to_date:
            conditions.append("s.standup_date <= %s")
            params.append(to_date)
        where = " AND ".join(conditions)
        sql = f"""
            SELECT s.*, m.real_name AS user_name
            FROM standups s
            LEFT JOIN members m ON m.team_id = s.team_id AND m.user_id = s.user_id
            WHERE {where}
            ORDER BY s.standup_date DESC, s.submitted_at
        """
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    sql = """
        SELECT s.*, m.real_name AS user_name
        FROM standups s
        LEFT JOIN members m ON m.team_id = s.team_id AND m.user_id = s.user_id
        WHERE s.team_id = %s
          AND s.standup_date >= CURRENT_DATE - ((%s - 1) * INTERVAL '1 day')
        ORDER BY s.standup_date DESC, s.submitted_at
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, days))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


def get_active_members(team_id: str) -> list[dict]:
    """Return active members for a workspace."""
    sql = """
        SELECT * FROM members
        WHERE team_id = %s AND active = TRUE
        ORDER BY COALESCE(NULLIF(display_name_override, ''), NULLIF(real_name, ''), user_id)
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def upsert_member(
    team_id: str,
    user_id: str,
    real_name: str | None = None,
    email: str | None = None,
    tz: str | None = None,
) -> None:
    """Insert or update a member record. Only non-None values overwrite existing ones."""
    sql = """
        INSERT INTO members (team_id, user_id, real_name, email, tz)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (team_id, user_id) DO UPDATE SET
            real_name = COALESCE(EXCLUDED.real_name, members.real_name),
            email = COALESCE(EXCLUDED.email, members.email),
            tz = COALESCE(EXCLUDED.tz, members.tz),
            active = TRUE
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id, real_name, email, tz))


def update_member_profile(
    team_id: str,
    user_id: str,
    *,
    display_name_override: str | None = None,
    tags: list[str] | None = None,
) -> None:
    """Update local member metadata such as display name override and tags."""
    updates: list[str] = []
    values: list[Any] = []

    if display_name_override is not None:
        updates.append("display_name_override = %s")
        values.append(display_name_override.strip() or None)
    if tags is not None:
        updates.append("tags = %s")
        values.append(json.dumps(tags))

    if not updates:
        return

    sql = f"UPDATE members SET {', '.join(updates)} WHERE team_id = %s AND user_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [*values, team_id, user_id])


# ---------------------------------------------------------------------------
# Standups
# ---------------------------------------------------------------------------


def save_standup(
    team_id: str,
    user_id: str,
    yesterday: str,
    today: str,
    blockers: str,
    mood: str | None = None,
) -> int | None:
    """Persist a completed standup. Returns the new standup ID."""
    has_blockers = blockers.strip().lower() not in ("none", "no", "nope", "-", "n/a", "")
    sql = """
        INSERT INTO standups (team_id, user_id, yesterday, today, blockers, has_blockers, mood)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id, yesterday, today, blockers, has_blockers, mood))
            row = cur.fetchone()
    standup_id = row[0] if row else None
    logger.info("Saved standup %s for %s / %s", standup_id, team_id, user_id)
    return standup_id


def get_today_standups(team_id: str) -> list[dict]:
    """Return all standup submissions for today."""
    sql = """
        SELECT * FROM standups
        WHERE team_id = %s AND standup_date = CURRENT_DATE
        ORDER BY submitted_at
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Progress product model
# ---------------------------------------------------------------------------


def _json_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _progress_collection_payload(row: dict) -> dict:
    raw_days = row.get("schedule_days") or "mon,tue,wed,thu,fri"
    return {
        "id": row["id"],
        "name": row.get("name") or "每日进度收集",
        "channel_id": row.get("channel_id") or "",
        "schedule_time": row.get("schedule_time") or "09:30",
        "schedule_tz": row.get("schedule_tz") or "Asia/Shanghai",
        "schedule_days": raw_days.split(",") if isinstance(raw_days, str) else raw_days,
        "questions": _json_list(row.get("questions")),
        "participants": row.get("participants") or [],
        "reminder_minutes": int(row.get("reminder_minutes") or 0),
        "active": bool(row.get("active", True)),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def get_progress_collections(team_id: str) -> list[dict]:
    sql = "SELECT * FROM progress_collections WHERE team_id = %s ORDER BY created_at"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            rows = cur.fetchall()
    return [_progress_collection_payload(dict(r)) for r in rows]


def get_progress_collection(team_id: str, collection_id: int) -> dict | None:
    sql = "SELECT * FROM progress_collections WHERE team_id = %s AND id = %s"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, collection_id))
            row = cur.fetchone()
    return _progress_collection_payload(dict(row)) if row else None


def get_progress_collection_for_user(team_id: str, user_id: str) -> dict | None:
    sql = """
        SELECT * FROM progress_collections
        WHERE team_id = %s
          AND active = TRUE
          AND (%s = ANY(participants) OR COALESCE(array_length(participants, 1), 0) = 0)
        ORDER BY created_at
        LIMIT 1
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return _progress_collection_payload(dict(row)) if row else None


def create_progress_collection(team_id: str, **kwargs: Any) -> dict:
    allowed = {
        "name",
        "channel_id",
        "schedule_time",
        "schedule_tz",
        "schedule_days",
        "questions",
        "participants",
        "reminder_minutes",
        "active",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if "questions" in fields and isinstance(fields["questions"], list):
        fields["questions"] = json.dumps(fields["questions"])
    if "schedule_days" in fields and isinstance(fields["schedule_days"], list):
        fields["schedule_days"] = ",".join(fields["schedule_days"])
    cols = ", ".join(fields.keys())
    placeholders = ", ".join(["%s"] * len(fields))
    sql = f"""
        INSERT INTO progress_collections (team_id, {cols}, updated_at)
        VALUES (%s, {placeholders}, NOW())
        RETURNING *
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, [team_id] + list(fields.values()))
            row = cur.fetchone()
    return _progress_collection_payload(dict(row))


def update_progress_collection(team_id: str, collection_id: int, **kwargs: Any) -> dict | None:
    allowed = {
        "name",
        "channel_id",
        "schedule_time",
        "schedule_tz",
        "schedule_days",
        "questions",
        "participants",
        "reminder_minutes",
        "active",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return get_progress_collection(team_id, collection_id)
    if "questions" in fields and isinstance(fields["questions"], list):
        fields["questions"] = json.dumps(fields["questions"])
    if "schedule_days" in fields and isinstance(fields["schedule_days"], list):
        fields["schedule_days"] = ",".join(fields["schedule_days"])
    set_clause = ", ".join(f"{k} = %s" for k in fields) + ", updated_at = NOW()"
    sql = f"UPDATE progress_collections SET {set_clause} WHERE team_id = %s AND id = %s RETURNING *"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, list(fields.values()) + [team_id, collection_id])
            row = cur.fetchone()
    return _progress_collection_payload(dict(row)) if row else None


def delete_progress_collection(team_id: str, collection_id: int) -> bool:
    sql = "DELETE FROM progress_collections WHERE team_id = %s AND id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, collection_id))
            return cur.rowcount > 0


def get_projects(team_id: str) -> list[dict]:
    sql = "SELECT * FROM projects WHERE team_id = %s ORDER BY status, name"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def upsert_project(team_id: str, name: str, description: str = "", status: str = "active") -> dict:
    sql = """
        INSERT INTO projects (team_id, name, description, status, updated_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (team_id, name) DO UPDATE SET
            description = EXCLUDED.description,
            status = EXCLUDED.status,
            updated_at = NOW()
        RETURNING *
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, name.strip(), description.strip(), status.strip() or "active"))
            row = cur.fetchone()
    return dict(row)


def update_project(team_id: str, project_id: int, name: str, description: str = "", status: str = "active") -> dict | None:
    sql = """
        UPDATE projects
        SET name = %s, description = %s, status = %s, updated_at = NOW()
        WHERE team_id = %s AND id = %s
        RETURNING *
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (name.strip(), description.strip(), status.strip() or "active", team_id, project_id))
            row = cur.fetchone()
    return dict(row) if row else None


def _create_progress_snapshot(
    team_id: str,
    entry_id: int,
    snapshot_type: str,
    payload: dict,
    created_by: str = "",
) -> None:
    sql = """
        INSERT INTO progress_entry_snapshots (team_id, entry_id, snapshot_type, payload, created_by)
        VALUES (%s, %s, %s, %s, %s)
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, entry_id, snapshot_type, json.dumps(payload, default=str), created_by))


def save_progress_entry(
    *,
    team_id: str,
    user_id: str,
    content: str,
    collection_id: int | None = None,
    project_id: int | None = None,
    role: str = "",
    source: str = "feishu_dm",
) -> int | None:
    sql = """
        INSERT INTO progress_entries (
            team_id, collection_id, project_id, user_id, role, content, source, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
    """
    payload = {
        "team_id": team_id,
        "collection_id": collection_id,
        "project_id": project_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        "source": source,
    }
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    team_id,
                    collection_id,
                    project_id,
                    user_id,
                    role,
                    content,
                    source,
                ),
            )
            row = cur.fetchone()
    entry_id = row[0] if row else None
    if entry_id:
        _create_progress_snapshot(team_id, entry_id, "create", payload, user_id)
    return entry_id


def get_progress_entries(
    team_id: str,
    *,
    days: int = 30,
    from_date: str | None = None,
    to_date: str | None = None,
    user_id: str | None = None,
    project_id: int | None = None,
) -> list[dict]:
    conditions = ["e.team_id = %s"]
    params: list[Any] = [team_id]
    if from_date:
        conditions.append("e.progress_date >= %s")
        params.append(from_date)
    if to_date:
        conditions.append("e.progress_date <= %s")
        params.append(to_date)
    if not from_date and not to_date:
        conditions.append("e.progress_date >= CURRENT_DATE - ((%s - 1) * INTERVAL '1 day')")
        params.append(days)
    if user_id:
        conditions.append("e.user_id = %s")
        params.append(user_id)
    if project_id:
        conditions.append("e.project_id = %s")
        params.append(project_id)
    sql = f"""
        SELECT
            e.*,
            COALESCE(NULLIF(m.display_name_override, ''), NULLIF(m.real_name, ''), e.user_id) AS member_name,
            m.tags AS member_tags,
            p.name AS project_name
        FROM progress_entries e
        LEFT JOIN members m ON m.team_id = e.team_id AND m.user_id = e.user_id
        LEFT JOIN projects p ON p.id = e.project_id
        WHERE {" AND ".join(conditions)}
        ORDER BY e.progress_date DESC, e.submitted_at DESC
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def update_progress_entry(team_id: str, entry_id: int, created_by: str = "", **kwargs: Any) -> dict | None:
    allowed = {"user_id", "project_id", "role", "content"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return get_progress_entry(team_id, entry_id)
    before = get_progress_entry(team_id, entry_id)
    if not before:
        return None
    set_clause = ", ".join(f"{k} = %s" for k in fields) + ", updated_at = NOW()"
    sql = f"UPDATE progress_entries SET {set_clause} WHERE team_id = %s AND id = %s RETURNING *"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, list(fields.values()) + [team_id, entry_id])
            row = cur.fetchone()
    after = dict(row) if row else None
    if after:
        _create_progress_snapshot(team_id, entry_id, "update", {"before": before, "after": after}, created_by)
    return after


def get_progress_entry(team_id: str, entry_id: int) -> dict | None:
    rows = get_progress_entries(team_id, days=3650)
    for row in rows:
        if int(row["id"]) == int(entry_id):
            return row
    return None


def get_progress_snapshots(team_id: str, entry_id: int) -> list[dict]:
    sql = """
        SELECT * FROM progress_entry_snapshots
        WHERE team_id = %s AND entry_id = %s
        ORDER BY created_at DESC
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, entry_id))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def get_previous_progress_entry(team_id: str, user_id: str) -> dict | None:
    sql = """
        SELECT * FROM progress_entries
        WHERE team_id = %s AND user_id = %s
        ORDER BY submitted_at DESC
        LIMIT 1
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return dict(row) if row else None


def get_data_board(team_id: str, days: int = 7) -> dict:
    entries = get_progress_entries(team_id, days=days)
    members = [m for m in get_active_members(team_id) if m.get("user_id") != "admin"]
    projects = get_projects(team_id)
    by_project: dict[str, int] = {}
    by_member: dict[str, int] = {}
    by_date: dict[str, int] = {}
    for row in entries:
        project_name = row.get("project_name") or "未归属项目"
        member_name = row.get("member_name") or row.get("user_id")
        date_key = str(row.get("progress_date"))
        by_project[project_name] = by_project.get(project_name, 0) + 1
        by_member[member_name] = by_member.get(member_name, 0) + 1
        by_date[date_key] = by_date.get(date_key, 0) + 1
    return {
        "total_entries": len(entries),
        "active_members": len(members),
        "active_projects": len([p for p in projects if p.get("status") == "active"]),
        "updated_today": len([e for e in entries if str(e.get("progress_date")) == str(__import__("datetime").date.today())]),
        "by_project": [{"name": k, "count": v} for k, v in sorted(by_project.items())],
        "by_member": [{"name": k, "count": v} for k, v in sorted(by_member.items())],
        "by_date": [{"date": k, "count": v} for k, v in sorted(by_date.items())],
        "recent_entries": entries[:10],
    }


def get_publish_jobs(team_id: str) -> list[dict]:
    sql = "SELECT * FROM publish_jobs WHERE team_id = %s ORDER BY created_at"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def create_publish_job(team_id: str, **kwargs: Any) -> dict:
    allowed = {
        "name",
        "destination_type",
        "destination",
        "schedule_time",
        "schedule_tz",
        "schedule_days",
        "range_days",
        "member_ids",
        "project_ids",
        "ai_summary_enabled",
        "ai_provider",
        "ai_prompt",
        "active",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if "schedule_days" in fields and isinstance(fields["schedule_days"], list):
        fields["schedule_days"] = ",".join(fields["schedule_days"])
    cols = ", ".join(fields.keys())
    placeholders = ", ".join(["%s"] * len(fields))
    sql = f"""
        INSERT INTO publish_jobs (team_id, {cols}, updated_at)
        VALUES (%s, {placeholders}, NOW())
        RETURNING *
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, [team_id] + list(fields.values()))
            row = cur.fetchone()
    return dict(row)


def update_publish_job(team_id: str, job_id: int, **kwargs: Any) -> dict | None:
    allowed = {
        "name",
        "destination_type",
        "destination",
        "schedule_time",
        "schedule_tz",
        "schedule_days",
        "range_days",
        "member_ids",
        "project_ids",
        "ai_summary_enabled",
        "ai_provider",
        "ai_prompt",
        "active",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return None
    if "schedule_days" in fields and isinstance(fields["schedule_days"], list):
        fields["schedule_days"] = ",".join(fields["schedule_days"])
    set_clause = ", ".join(f"{k} = %s" for k in fields) + ", updated_at = NOW()"
    sql = f"UPDATE publish_jobs SET {set_clause} WHERE team_id = %s AND id = %s RETURNING *"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, list(fields.values()) + [team_id, job_id])
            row = cur.fetchone()
    return dict(row) if row else None


def delete_publish_job(team_id: str, job_id: int) -> bool:
    sql = "DELETE FROM publish_jobs WHERE team_id = %s AND id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, job_id))
            return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------


def get_dashboard_stats(team_id: str) -> dict:
    """Return completion rate, active member count, and response counts."""
    sql_responses = """
        SELECT COUNT(*) AS total,
               COUNT(DISTINCT user_id) AS active_members
        FROM standups
        WHERE team_id = %s
          AND standup_date >= CURRENT_DATE - INTERVAL '7 days'
    """
    sql_total_members = "SELECT COUNT(*) AS cnt FROM members WHERE team_id = %s AND active = TRUE"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql_responses, (team_id,))
            row = dict(cur.fetchone())
            cur.execute(sql_total_members, (team_id,))
            members_row = dict(cur.fetchone())
    total_members = members_row.get("cnt", 0) or 0
    responses_week = row.get("total", 0) or 0
    active_members = row.get("active_members", 0) or 0
    # Completion rate: responses this week / (members * working days this week)
    completion_rate = 0
    if total_members > 0 and responses_week > 0:
        completion_rate = min(100, int(responses_week / max(total_members, 1) * 100 / 5))
    return {
        "completion_rate": completion_rate,
        "active_members": active_members,
        "total_responses": responses_week,
        "responses_this_week": responses_week,
        "total_members": total_members,
    }


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


def get_webhooks(team_id: str) -> list[dict]:
    """Return all webhooks registered for a team."""
    sql = "SELECT * FROM webhooks WHERE team_id = %s ORDER BY created_at"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def add_webhook(
    team_id: str,
    url: str,
    secret: str | None = None,
    events: list[str] | None = None,
) -> dict:
    """Insert a new webhook and return the created row."""
    if events is None:
        events = ["standup.completed"]
    sql = """
        INSERT INTO webhooks (team_id, webhook_url, secret, events)
        VALUES (%s, %s, %s, %s)
        RETURNING *
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, url, secret, events))
            row = cur.fetchone()
    logger.info("Added webhook %s for team %s", url, team_id)
    return dict(row)


def delete_webhook(team_id: str, webhook_id: int) -> bool:
    """Delete a webhook by id (scoped to team_id for safety). Returns True if deleted."""
    sql = "DELETE FROM webhooks WHERE id = %s AND team_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (webhook_id, team_id))
            deleted = cur.rowcount > 0
    return deleted


# ---------------------------------------------------------------------------
# Standup lookup
# ---------------------------------------------------------------------------


def get_standup_by_id(standup_id: int) -> dict | None:
    """Return a single standup row by primary key, or None."""
    sql = "SELECT * FROM standups WHERE id = %s"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (standup_id,))
            row = cur.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Skip today
# ---------------------------------------------------------------------------


def skip_today(team_id: str, user_id: str) -> None:
    """Mark user as skipping today's standup."""
    sql = """
        INSERT INTO user_skip (team_id, user_id, skip_date)
        VALUES (%s, %s, CURRENT_DATE)
        ON CONFLICT DO NOTHING
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))


def is_skipped_today(team_id: str, user_id: str) -> bool:
    """Return True if user has skipped today."""
    sql = "SELECT 1 FROM user_skip WHERE team_id=%s AND user_id=%s AND skip_date=CURRENT_DATE"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))
            return cur.fetchone() is not None


def set_vacation(team_id: str, user_id: str, on_vacation: bool) -> None:
    """Mark a member as on vacation (or back from vacation)."""
    sql = """
        INSERT INTO members (team_id, user_id, on_vacation)
        VALUES (%s, %s, %s)
        ON CONFLICT (team_id, user_id) DO UPDATE SET on_vacation = EXCLUDED.on_vacation
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id, on_vacation))


def is_on_vacation(team_id: str, user_id: str) -> bool:
    """Return True if this member is currently marked as on vacation."""
    sql = "SELECT on_vacation FROM members WHERE team_id = %s AND user_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return bool(row[0]) if row else False


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


def get_standup_streak(team_id: str, user_id: str) -> int:
    """Return the current consecutive standup streak (number of working days in a row).

    Counts backwards from today (or the most recent standup date) through
    consecutive weekdays where the user submitted a standup.
    """
    sql = """
        WITH dates AS (
            SELECT DISTINCT standup_date
            FROM standups
            WHERE team_id = %s AND user_id = %s
            ORDER BY standup_date DESC
        ),
        numbered AS (
            SELECT standup_date,
                   standup_date - (ROW_NUMBER() OVER (ORDER BY standup_date DESC))::int AS grp
            FROM dates
        )
        SELECT COUNT(*) AS streak
        FROM numbered
        WHERE grp = (SELECT grp FROM numbered LIMIT 1)
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return int(row[0]) if row and row[0] else 0


def get_user_last_standup_answers(team_id: str, user_id: str) -> dict | None:
    """Return the most recent standup answers for prefilling the form."""
    sql = """
        SELECT yesterday, today, blockers
        FROM standups
        WHERE team_id = %s AND user_id = %s
        ORDER BY submitted_at DESC
        LIMIT 1
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return dict(row) if row else None


def get_participation_stats(team_id: str, days: int = 7) -> list[dict]:
    """Return per-member participation stats for the last N days."""
    sql = """
        SELECT
            m.user_id,
            m.real_name,
            COUNT(s.id) AS responses,
            MAX(s.submitted_at) AS last_standup,
            COUNT(CASE WHEN s.has_blockers THEN 1 END) AS days_with_blockers
        FROM members m
        LEFT JOIN standups s ON s.team_id = m.team_id
            AND s.user_id = m.user_id
            AND s.standup_date >= CURRENT_DATE - (%s - 1) * INTERVAL '1 day'
        WHERE m.team_id = %s AND m.active = TRUE
        GROUP BY m.user_id, m.real_name
        ORDER BY responses DESC, m.real_name
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (days, team_id))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def export_standups(team_id: str, from_date: str | None = None, to_date: str | None = None) -> list[dict]:
    """Return standup rows for export, optionally filtered by date range."""
    conditions = ["team_id = %s"]
    params: list = [team_id]
    if from_date:
        conditions.append("standup_date >= %s")
        params.append(from_date)
    if to_date:
        conditions.append("standup_date <= %s")
        params.append(to_date)
    sql = f"SELECT * FROM standups WHERE {' AND '.join(conditions)} ORDER BY standup_date, submitted_at"
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Member email lookup
# ---------------------------------------------------------------------------


def get_member_email(team_id: str, user_id: str) -> str | None:
    """Return email for a member, or None."""
    sql = "SELECT email FROM members WHERE team_id=%s AND user_id=%s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Standup schedules
# ---------------------------------------------------------------------------


def get_standup_schedules(team_id: str) -> list[dict]:
    """Compatibility wrapper for progress collection tasks."""
    return get_progress_collections(team_id)


def create_standup_schedule(team_id: str, **kwargs) -> dict:
    """Compatibility wrapper for progress collection tasks."""
    allowed = {
        "name",
        "channel_id",
        "schedule_time",
        "schedule_tz",
        "schedule_days",
        "questions",
        "participants",
        "reminder_minutes",
        "active",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    return create_progress_collection(team_id, **fields)


def upsert_daily_thread(
    team_id: str, channel_id: str, thread_date: str, parent_ts: str, schedule_id: int = 0
) -> None:
    """Persist the parent message ts for today's standup thread.

    Scoped by schedule_id so workspaces running multiple standups on the same
    channel (morning + evening) get a distinct thread parent per schedule.
    """
    sql = """
        INSERT INTO daily_standup_threads (team_id, channel_id, thread_date, schedule_id, parent_ts)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (team_id, channel_id, thread_date, schedule_id) DO NOTHING
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql, (team_id, channel_id, thread_date, int(schedule_id or 0), parent_ts))
            except Exception:
                pass


def get_daily_thread_ts(team_id: str, channel_id: str, thread_date: str, schedule_id: int = 0) -> str | None:
    """Look up the parent ts for today's standup thread, if one was created."""
    sql = """
        SELECT parent_ts FROM daily_standup_threads
        WHERE team_id = %s AND channel_id = %s AND thread_date = %s AND schedule_id = %s
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql, (team_id, channel_id, thread_date, int(schedule_id or 0)))
            except Exception:
                return None
            row = cur.fetchone()
    return row[0] if row else None


def get_schedule_for_user(team_id: str, user_id: str) -> dict | None:
    """Compatibility wrapper for progress collection tasks."""
    return get_progress_collection_for_user(team_id, user_id)


def get_standup_schedule_for_channel(team_id: str, channel_id: str) -> dict | None:
    """Return the active progress collection for a channel."""
    sql = """
        SELECT * FROM progress_collections
        WHERE team_id = %s AND channel_id = %s AND active = TRUE
        ORDER BY created_at
        LIMIT 1
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, channel_id))
            row = cur.fetchone()
    return _progress_collection_payload(dict(row)) if row else None


def update_standup_schedule(team_id: str, schedule_id: int, **kwargs) -> dict | None:
    """Compatibility wrapper for progress collection tasks."""
    allowed = {
        "name",
        "channel_id",
        "schedule_time",
        "schedule_tz",
        "schedule_days",
        "questions",
        "participants",
        "reminder_minutes",
        "active",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return get_standup_schedule(team_id, schedule_id)
    return update_progress_collection(team_id, schedule_id, **fields)


def delete_standup_schedule(team_id: str, schedule_id: int) -> bool:
    """Compatibility wrapper for progress collection tasks."""
    return delete_progress_collection(team_id, schedule_id)


def get_standup_schedule(team_id: str, schedule_id: int) -> dict | None:
    """Compatibility wrapper for progress collection tasks."""
    return get_progress_collection(team_id, schedule_id)


def get_all_active_schedules() -> list[dict]:
    """Return all active progress collection tasks across all workspaces."""
    sql = """
        SELECT s.*, i.bot_token
        FROM progress_collections s
        JOIN installations i ON i.team_id = s.team_id
        WHERE s.active = TRUE
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Kudos
# ---------------------------------------------------------------------------


def save_kudos(team_id: str, from_user: str, to_user: str, message: str, channel_id: str = "") -> dict:
    """Save a kudos entry and return it."""
    sql = """
        INSERT INTO kudos (team_id, from_user, to_user, message, channel_id)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, from_user, to_user, message, channel_id))
            row = cur.fetchone()
    return dict(row)


def get_kudos(team_id: str, limit: int = 50) -> list[dict]:
    """Return recent kudos for a team."""
    sql = """
        SELECT * FROM kudos
        WHERE team_id = %s
        ORDER BY created_at DESC
        LIMIT %s
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, limit))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def get_kudos_leaderboard(team_id: str, days: int = 30) -> list[dict]:
    """Return top kudos receivers for the last N days."""
    sql = """
        SELECT
            to_user,
            COUNT(*) AS received,
            MAX(created_at) AS last_kudos
        FROM kudos
        WHERE team_id = %s
          AND created_at >= NOW() - (%s * INTERVAL '1 day')
        GROUP BY to_user
        ORDER BY received DESC
        LIMIT 20
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, days))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Role-based access control
# ---------------------------------------------------------------------------


def get_member_role(team_id: str, user_id: str) -> str:
    """Return 'admin' or 'member' for a user. Defaults to 'member' if not found."""
    sql = "SELECT role FROM members WHERE team_id = %s AND user_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return (row[0] if row else None) or "member"


def set_member_role(team_id: str, user_id: str, role: str) -> None:
    """Set a member's role to 'admin' or 'member'."""
    if role not in ("admin", "member"):
        raise ValueError(f"Invalid role: {role}")
    sql = "UPDATE members SET role = %s WHERE team_id = %s AND user_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (role, team_id, user_id))


def ensure_admin(team_id: str, user_id: str) -> None:
    """Upsert user as admin — used on OAuth install."""
    sql = """
        INSERT INTO members (team_id, user_id, role)
        VALUES (%s, %s, 'admin')
        ON CONFLICT (team_id, user_id) DO UPDATE SET role = 'admin'
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, user_id))


# ---------------------------------------------------------------------------
# Standup editing helpers
# ---------------------------------------------------------------------------


def get_latest_standup(user_id: str, team_id: str) -> dict | None:
    """Return the most recent standup for a user/team, or None."""
    sql = """
        SELECT * FROM standups
        WHERE team_id = %s AND user_id = %s
        ORDER BY submitted_at DESC
        LIMIT 1
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id, user_id))
            row = cur.fetchone()
    return dict(row) if row else None


def update_standup(user_id: str, team_id: str, **kwargs: Any) -> None:
    """Update the most recent standup for a user/team with the provided fields.

    Accepted keyword arguments: yesterday, today, blockers, mood.
    Automatically recomputes ``has_blockers`` when ``blockers`` is updated.
    """
    allowed = {"yesterday", "today", "blockers", "mood"}
    updates: dict[str, Any] = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    if "blockers" in updates:
        blocker_val: str = updates["blockers"] or ""
        updates["has_blockers"] = blocker_val.strip().lower() not in ("none", "no", "nope", "-", "n/a", "")
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values: list[Any] = list(updates.values())
    sql = f"""
        UPDATE standups SET {set_clause}
        WHERE id = (
            SELECT id FROM standups
            WHERE team_id = %s AND user_id = %s
            ORDER BY submitted_at DESC
            LIMIT 1
        )
    """
    values.extend([team_id, user_id])
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, values)
    logger.info("Updated standup for %s / %s", team_id, user_id)


# ---------------------------------------------------------------------------
# MCP API keys
# ---------------------------------------------------------------------------

import hashlib as _hashlib
import secrets as _secrets


def generate_mcp_key(team_id: str, name: str = "Default") -> str:
    """Generate a new MCP API key, store its hash, return the full key."""
    key = "mrn_" + _secrets.token_urlsafe(32)
    key_hash = _hashlib.sha256(key.encode()).hexdigest()
    key_prefix = key[:12]
    sql = """
        INSERT INTO mcp_api_keys (team_id, key_hash, key_prefix, name)
        VALUES (%s, %s, %s, %s)
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, key_hash, key_prefix, name))
    logger.info("Generated MCP key %s... for team %s", key_prefix, team_id)
    return key


def get_mcp_keys(team_id: str) -> list[dict]:
    """Return all MCP keys for a team (prefix only, not the raw key)."""
    sql = """
        SELECT id, key_prefix, name, created_at, last_used_at, active
        FROM mcp_api_keys
        WHERE team_id = %s
        ORDER BY created_at DESC
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (team_id,))
            return [dict(r) for r in cur.fetchall()]


def revoke_mcp_key(key_id: int, team_id: str) -> None:
    """Soft-delete an MCP API key (marks inactive)."""
    sql = "UPDATE mcp_api_keys SET active = FALSE WHERE id = %s AND team_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (key_id, team_id))


def verify_mcp_key(key: str) -> str | None:
    """Verify an API key, update last_used_at, return team_id or None."""
    key_hash = _hashlib.sha256(key.encode()).hexdigest()
    sql = """
        UPDATE mcp_api_keys SET last_used_at = NOW()
        WHERE key_hash = %s AND active = TRUE
        RETURNING team_id
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (key_hash,))
            row = cur.fetchone()
    return row[0] if row else None


def delete_installation(team_id: str) -> bool:
    """Delete a workspace installation and all cascading data (members, standups, config, etc.).

    All child tables reference installations(team_id) with ON DELETE CASCADE,
    so a single DELETE removes all workspace data.
    Returns True if a row was deleted, False if team_id was not found.
    """
    sql = "DELETE FROM installations WHERE team_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id,))
            return cur.rowcount > 0
