"""Tests for dashboard.py — Flask blueprint API endpoints."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

# Stub heavy dependencies before importing dashboard
sys.modules.setdefault("psycopg2", MagicMock())
sys.modules.setdefault("psycopg2.extras", MagicMock())
sys.modules.setdefault("psycopg2.pool", MagicMock())
sys.modules.setdefault("slack_sdk", MagicMock())
sys.modules.setdefault("slack_bolt", MagicMock())
sys.modules.setdefault("markupsafe", MagicMock())

# Stub db and oauth at the module level before dashboard imports them.
# Save any prior values so we can restore them after dashboard is imported
# (avoiding interference with test_oauth.py which tests the real oauth module).
_prior_db = sys.modules.get("db")
_prior_oauth = sys.modules.get("oauth")

_db_mock = MagicMock()
_oauth_mock = MagicMock()
sys.modules["db"] = _db_mock
sys.modules["oauth"] = _oauth_mock

import dashboard  # noqa: E402
from flask import Flask  # noqa: E402

# Restore so test_oauth.py (and others) get the real modules
if _prior_db is not None:
    sys.modules["db"] = _prior_db
else:
    sys.modules.pop("db", None)
if _prior_oauth is not None:
    sys.modules["oauth"] = _prior_oauth
else:
    sys.modules.pop("oauth", None)


@pytest.fixture(autouse=True)
def dashboard_auth_key_mode(monkeypatch):
    monkeypatch.setenv("DASHBOARD_AUTH", "key")
    monkeypatch.delenv("DASHBOARD_ADMIN_KEY", raising=False)
    _db_mock.get_app_settings.return_value = {}
    _db_mock.get_installation.return_value = None


@pytest.fixture()
def app():
    flask_app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "../src/templates"))
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    flask_app.register_blueprint(dashboard.dashboard_bp)
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def authed_client(client, app):
    """Return a test client with a session containing team_id and user_id."""
    with client.session_transaction() as sess:
        sess["team_id"] = "T123"
        sess["user_id"] = "U456"
    return client


# ---------------------------------------------------------------------------
# Auth / redirect behaviour
# ---------------------------------------------------------------------------


class TestAuthGuard:
    def test_api_members_unauthenticated_returns_401(self, client):
        resp = client.get("/dashboard/api/members")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "Unauthorized"

    def test_api_reports_unauthenticated_returns_401(self, client):
        resp = client.get("/dashboard/api/reports")
        assert resp.status_code == 401

    def test_api_standups_unauthenticated_returns_401(self, client):
        resp = client.get("/dashboard/api/standups")
        assert resp.status_code == 401

    def test_dashboard_page_unauthenticated_redirects(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code in (301, 302)

    def test_internal_auth_mode_auto_logs_in(self, client, monkeypatch):
        monkeypatch.setenv("DASHBOARD_AUTH", "none")
        _db_mock.get_standup_schedules.return_value = []

        resp = client.get("/dashboard/api/standups")

        assert resp.status_code == 200
        with client.session_transaction() as sess:
            assert sess["team_id"] == "feishu"
            assert sess["user_id"] == "admin"

    def test_logout_clears_session_and_redirects(self, authed_client):
        resp = authed_client.get("/dashboard/logout")
        assert resp.status_code in (301, 302)

    def test_feishu_admin_key_login_sets_session(self, client, monkeypatch):
        monkeypatch.setenv("FEISHU_APP_ID", "cli_x")
        monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
        monkeypatch.setenv("FEISHU_DASHBOARD_ADMIN_KEY", "admin-key")
        monkeypatch.setenv("FEISHU_ADMIN_OPEN_ID", "ou_admin")
        _db_mock.get_installation.return_value = {"team_name": "Feishu Team"}

        resp = client.get("/dashboard/login?key=admin-key")

        assert resp.status_code in (301, 302)
        with client.session_transaction() as sess:
            assert sess["team_id"] == "feishu"
            assert sess["user_id"] == "ou_admin"
        _db_mock.ensure_admin.assert_called()

    def test_settings_update_persists_allowed_keys(self, authed_client):
        longconn_mod = MagicMock()
        with patch.dict(sys.modules, {"feishu_longconn": longconn_mod}):
            resp = authed_client.put(
                "/dashboard/api/settings",
                json={"settings": {"APP_URL": "http://localhost:3000", "FEISHU_TEAM_NAME": "研发部", "FEISHU_EVENT_MODE": "ws", "UNKNOWN": "x"}},
            )

        assert resp.status_code == 200
        _db_mock.set_app_settings.assert_called()
        saved = _db_mock.set_app_settings.call_args.args[0]
        assert saved == {"APP_URL": "http://localhost:3000", "FEISHU_TEAM_NAME": "研发部", "FEISHU_EVENT_MODE": "ws"}
        longconn_mod.feishu_longconn_service.stop.assert_called_once()


# ---------------------------------------------------------------------------
# /dashboard/api/members
# ---------------------------------------------------------------------------


class TestApiMembers:
    def test_returns_200_with_list(self, authed_client):
        _db_mock.get_installation.return_value = {"bot_token": "xoxb-test", "team_name": "Acme"}
        _db_mock.get_active_members.return_value = []

        slack_client_mock = MagicMock()
        slack_client_mock.users_list.return_value = {
            "members": [
                {
                    "id": "U1",
                    "name": "alice",
                    "deleted": False,
                    "is_bot": False,
                    "tz": "UTC",
                    "profile": {"real_name": "Alice", "display_name": "alice", "image_48": "", "email": "a@b.com"},
                }
            ]
        }

        slack_sdk_mod = MagicMock()
        slack_sdk_mod.WebClient.return_value = slack_client_mock
        with patch.dict(sys.modules, {"slack_sdk": slack_sdk_mod}):
            resp = authed_client.get("/dashboard/api/members")

        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_returns_empty_list_when_no_bot_token(self, authed_client):
        _db_mock.get_installation.return_value = None
        resp = authed_client.get("/dashboard/api/members")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_falls_back_to_db_on_slack_error(self, authed_client):
        _db_mock.get_installation.return_value = {"bot_token": "xoxb-test", "team_name": "Acme"}
        _db_mock.get_active_members.return_value = [
            {"user_id": "U2", "real_name": "Bob", "email": "b@c.com", "tz": "UTC", "role": "member"}
        ]

        slack_sdk_mod = MagicMock()
        slack_sdk_mod.WebClient.side_effect = Exception("Slack down")
        with patch.dict(sys.modules, {"slack_sdk": slack_sdk_mod}):
            resp = authed_client.get("/dashboard/api/members")

        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_feishu_returns_db_members(self, authed_client, monkeypatch):
        monkeypatch.setenv("FEISHU_APP_ID", "cli_x")
        monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
        with authed_client.session_transaction() as sess:
            sess["team_id"] = "feishu"
            sess["user_id"] = "ou_admin"
        _db_mock.get_active_members.return_value = [
            {"user_id": "ou_1", "real_name": "Alice", "email": "a@example.com", "tz": "Asia/Shanghai", "role": "member"}
        ]

        resp = authed_client.get("/dashboard/api/members")

        assert resp.status_code == 200
        assert resp.get_json()[0]["id"] == "ou_1"

    def test_feishu_hides_placeholder_admin_member(self, authed_client, monkeypatch):
        monkeypatch.setenv("FEISHU_APP_ID", "cli_x")
        monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
        with authed_client.session_transaction() as sess:
            sess["team_id"] = "feishu"
            sess["user_id"] = "ou_admin"
        _db_mock.get_active_members.return_value = [
            {"user_id": "admin", "real_name": "admin", "email": "", "tz": "Asia/Shanghai", "role": "admin"},
            {"user_id": "ou_1", "real_name": "Alice", "email": "a@example.com", "tz": "Asia/Shanghai", "role": "member"},
        ]

        resp = authed_client.get("/dashboard/api/members")

        assert resp.status_code == 200
        assert [row["id"] for row in resp.get_json()] == ["ou_1"]

    def test_feishu_invite_adds_member_without_slack(self, authed_client, monkeypatch):
        monkeypatch.setenv("FEISHU_APP_ID", "cli_x")
        monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
        with authed_client.session_transaction() as sess:
            sess["team_id"] = "feishu"
            sess["user_id"] = "ou_admin"
        _db_mock.get_member_role.return_value = "admin"

        resp = authed_client.post(
            "/dashboard/api/members/invite",
            json={"user_id": "ou_2", "name": "Bob", "email": "b@example.com", "role": "admin"},
        )

        assert resp.status_code == 200
        _db_mock.upsert_member.assert_called()
        _db_mock.set_member_role.assert_called_with("feishu", "ou_2", "admin")

    def test_update_member_profile(self, authed_client):
        _db_mock.get_member_role.return_value = "admin"

        resp = authed_client.put(
            "/dashboard/api/members/U2",
            json={"display_name_override": "张三", "tags": ["后端", "负责人", "后端"]},
        )

        assert resp.status_code == 200
        _db_mock.update_member_profile.assert_called_once_with(
            "T123",
            "U2",
            display_name_override="张三",
            tags=["后端", "负责人"],
        )

    def test_feishu_members_payload_prefers_display_name_override(self, authed_client, monkeypatch):
        monkeypatch.setenv("FEISHU_APP_ID", "cli_x")
        monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
        with authed_client.session_transaction() as sess:
            sess["team_id"] = "feishu"
            sess["user_id"] = "ou_admin"
        _db_mock.get_active_members.return_value = [
            {
                "user_id": "ou_1",
                "real_name": "飞书用户7348HB",
                "display_name_override": "张三",
                "email": "a@example.com",
                "tz": "Asia/Shanghai",
                "role": "member",
                "tags": ["研发"],
            }
        ]

        resp = authed_client.get("/dashboard/api/members")

        assert resp.status_code == 200
        assert resp.get_json() == [
            {
                "id": "ou_1",
                "name": "张三",
                "display_name": "张三",
                "raw_name": "飞书用户7348HB",
                "avatar": "",
                "email": "a@example.com",
                "tz": "Asia/Shanghai",
                "role": "member",
                "tags": ["研发"],
            }
        ]


# ---------------------------------------------------------------------------
# /dashboard/api/reports
# ---------------------------------------------------------------------------


class TestApiReports:
    def test_returns_200_with_expected_keys(self, authed_client):
        _db_mock.get_standups.return_value = []
        _db_mock.get_participation_stats.return_value = []
        resp = authed_client.get("/dashboard/api/reports")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "standups" in data
        assert "participation" in data
        assert "total_days" in data

    def test_filters_by_user_id(self, authed_client):
        _db_mock.get_standups.return_value = [
            {"user_id": "U1", "yesterday": "a", "today": "b"},
            {"user_id": "U2", "yesterday": "c", "today": "d"},
        ]
        _db_mock.get_participation_stats.return_value = []
        resp = authed_client.get("/dashboard/api/reports?user_id=U1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert all(s["user_id"] == "U1" for s in data["standups"])

    def test_db_error_returns_empty_fallback(self, authed_client):
        _db_mock.get_standups.side_effect = Exception("DB error")
        resp = authed_client.get("/dashboard/api/reports")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["standups"] == []
        _db_mock.get_standups.side_effect = None  # reset

    def test_date_from_param_accepted(self, authed_client):
        _db_mock.get_standups.return_value = []
        _db_mock.get_participation_stats.return_value = []
        resp = authed_client.get("/dashboard/api/reports?date_from=2024-01-01")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /dashboard/api/standups
# ---------------------------------------------------------------------------


class TestApiStandups:
    def test_list_standups_returns_200(self, authed_client):
        _db_mock.get_standup_schedules.return_value = [
            {
                "id": 1,
                "name": "Morning",
                "channel_id": "C1",
                "schedule_time": "09:00",
                "schedule_tz": "UTC",
                "schedule_days": "mon,tue,wed,thu,fri",
                "questions": [],
                "active": True,
                "participants": [],
                "reminder_minutes": 0,
            }
        ]
        resp = authed_client.get("/dashboard/api/standups")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_create_standup_returns_201(self, authed_client):
        _db_mock.create_standup_schedule.return_value = {
            "id": 2,
            "name": "New",
            "channel_id": "C2",
            "schedule_time": "10:00",
            "schedule_tz": "UTC",
            "schedule_days": "mon,tue,wed,thu,fri",
            "questions": [],
            "active": True,
            "participants": [],
            "reminder_minutes": 0,
        }
        resp = authed_client.post(
            "/dashboard/api/standups",
            json={"name": "New", "channel_id": "C2", "schedule_time": "10:00"},
        )
        assert resp.status_code == 201
        assert _db_mock.create_standup_schedule.call_args.kwargs["post_summary"] is True

    def test_create_standup_saves_ai_fields(self, authed_client):
        _db_mock.create_standup_schedule.return_value = {
            "id": 3,
            "name": "AI",
            "channel_id": "C2",
            "schedule_time": "10:00",
            "schedule_tz": "UTC",
            "schedule_days": "mon,tue,wed,thu,fri",
            "questions": [],
            "active": True,
            "participants": [],
            "reminder_minutes": 0,
            "ai_summary_enabled": True,
            "ai_provider": "openai",
        }
        resp = authed_client.post(
            "/dashboard/api/standups",
            json={"name": "AI", "channel_id": "C2", "ai_summary_enabled": True, "ai_provider": "openai"},
        )

        assert resp.status_code == 201
        kwargs = _db_mock.create_standup_schedule.call_args.kwargs
        assert kwargs["ai_summary_enabled"] is True
        assert kwargs["ai_provider"] == "openai"
        assert kwargs["post_summary"] is True


class TestApiChannels:
    def test_feishu_channels_from_env_and_schedules(self, authed_client, monkeypatch):
        monkeypatch.setenv("FEISHU_APP_ID", "cli_x")
        monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
        monkeypatch.setenv("FEISHU_DEFAULT_CHAT_ID", "oc_default")
        monkeypatch.setenv("FEISHU_DEFAULT_CHAT_NAME", "Default")
        monkeypatch.setenv("FEISHU_CHANNELS", "oc_eng|Engineering")
        with authed_client.session_transaction() as sess:
            sess["team_id"] = "feishu"
            sess["user_id"] = "ou_admin"
        _db_mock.get_workspace_config.return_value = {}
        _db_mock.get_standup_schedules.return_value = [{"channel_id": "oc_product", "name": "Product"}]

        resp = authed_client.get("/dashboard/api/channels")

        assert resp.status_code == 200
        ids = {row["id"] for row in resp.get_json()}
        assert {"oc_default", "oc_eng", "oc_product"}.issubset(ids)

    def test_feishu_channels_include_remote_chat_list(self, authed_client, monkeypatch):
        monkeypatch.setenv("FEISHU_APP_ID", "cli_x")
        monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
        with authed_client.session_transaction() as sess:
            sess["team_id"] = "feishu"
            sess["user_id"] = "ou_admin"
        _db_mock.get_workspace_config.return_value = {}
        _db_mock.get_standup_schedules.return_value = []

        adapter_mod = MagicMock()
        adapter_instance = adapter_mod.FeishuAdapter.return_value
        adapter_instance.list_chats.return_value = [{"chat_id": "oc_remote", "name": "Remote Team"}]

        with patch.dict(sys.modules, {"adapters.feishu_adapter": adapter_mod}):
            resp = authed_client.get("/dashboard/api/channels")

        assert resp.status_code == 200
        ids = {row["id"] for row in resp.get_json()}
        assert "oc_remote" in ids

    def test_feishu_channels_preserve_remote_name_over_db_fallback(self, authed_client, monkeypatch):
        monkeypatch.setenv("FEISHU_APP_ID", "cli_x")
        monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
        with authed_client.session_transaction() as sess:
            sess["team_id"] = "feishu"
            sess["user_id"] = "ou_admin"
        _db_mock.get_workspace_config.return_value = {"channel_id": "oc_remote"}
        _db_mock.get_standup_schedules.return_value = []

        adapter_mod = MagicMock()
        adapter_instance = adapter_mod.FeishuAdapter.return_value
        adapter_instance.list_chats.return_value = [{"chat_id": "oc_remote", "name": "远程群"}]

        with patch.dict(sys.modules, {"adapters.feishu_adapter": adapter_mod}):
            resp = authed_client.get("/dashboard/api/channels")

        assert resp.status_code == 200
        assert resp.get_json() == [{"id": "oc_remote", "name": "远程群"}]

    def test_feishu_channels_ignore_placeholder_workspace_channel(self, authed_client, monkeypatch):
        monkeypatch.setenv("FEISHU_APP_ID", "cli_x")
        monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
        with authed_client.session_transaction() as sess:
            sess["team_id"] = "feishu"
            sess["user_id"] = "ou_admin"
        _db_mock.get_workspace_config.return_value = {"channel_id": "oc_demo"}
        _db_mock.get_standup_schedules.return_value = []

        adapter_mod = MagicMock()
        adapter_instance = adapter_mod.FeishuAdapter.return_value
        adapter_instance.list_chats.return_value = []

        with patch.dict(sys.modules, {"adapters.feishu_adapter": adapter_mod}):
            resp = authed_client.get("/dashboard/api/channels")

        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_feishu_members_sync_default_chat_when_no_channel_id(self, authed_client, monkeypatch):
        monkeypatch.setenv("FEISHU_APP_ID", "cli_x")
        monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
        monkeypatch.setenv("FEISHU_DEFAULT_CHAT_ID", "oc_default")
        with authed_client.session_transaction() as sess:
            sess["team_id"] = "feishu"
            sess["user_id"] = "ou_admin"
        _db_mock.get_workspace_config.return_value = {}
        _db_mock.get_active_members.return_value = []

        adapter_mod = MagicMock()
        adapter_instance = adapter_mod.FeishuAdapter.return_value
        adapter_instance.list_chat_members.return_value = [{"member_id": "ou_1", "name": "Alice"}]

        with patch.dict(sys.modules, {"adapters.feishu_adapter": adapter_mod}):
            resp = authed_client.get("/dashboard/api/members")

        assert resp.status_code == 200
        _db_mock.upsert_member.assert_called()

    def test_feishu_members_do_not_sync_placeholder_channel(self, authed_client, monkeypatch):
        monkeypatch.setenv("FEISHU_APP_ID", "cli_x")
        monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
        monkeypatch.setenv("FEISHU_DEFAULT_CHAT_ID", "oc_demo")
        with authed_client.session_transaction() as sess:
            sess["team_id"] = "feishu"
            sess["user_id"] = "ou_admin"
        _db_mock.get_active_members.return_value = []

        adapter_mod = MagicMock()
        adapter_instance = adapter_mod.FeishuAdapter.return_value
        adapter_instance.list_chat_members.return_value = [{"member_id": "ou_1", "name": "Alice"}]

        with patch.dict(sys.modules, {"adapters.feishu_adapter": adapter_mod}):
            resp = authed_client.get("/dashboard/api/members")

        assert resp.status_code == 200
        adapter_instance.list_chat_members.assert_not_called()


# ---------------------------------------------------------------------------
# /dashboard/api/stats
# ---------------------------------------------------------------------------


class TestApiStats:
    def test_returns_200(self, authed_client):
        _db_mock.get_dashboard_stats.return_value = {
            "total_standups": 10,
            "active_members": 3,
            "response_rate": 0.8,
        }
        resp = authed_client.get("/dashboard/api/stats")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# _is_safe_webhook_url helper
# ---------------------------------------------------------------------------


class TestIsSafeWebhookUrl:
    def test_localhost_rejected(self):
        from dashboard import _is_safe_webhook_url

        assert _is_safe_webhook_url("http://localhost/hook") is False

    def test_loopback_ip_rejected(self):
        from dashboard import _is_safe_webhook_url

        assert _is_safe_webhook_url("https://127.0.0.1/hook") is False

    def test_private_ip_rejected(self):
        from dashboard import _is_safe_webhook_url

        assert _is_safe_webhook_url("https://192.168.1.1/hook") is False

    def test_public_url_allowed(self):
        from dashboard import _is_safe_webhook_url

        assert _is_safe_webhook_url("https://hooks.example.com/standup") is True

    def test_non_http_scheme_rejected(self):
        from dashboard import _is_safe_webhook_url

        assert _is_safe_webhook_url("ftp://hooks.example.com/hook") is False

    def test_invalid_url_rejected(self):
        from dashboard import _is_safe_webhook_url

        assert _is_safe_webhook_url("not-a-url") is False


# ---------------------------------------------------------------------------
# _schedule_to_standup normalisation helper
# ---------------------------------------------------------------------------


class TestScheduleToStandup:
    def test_minimal_row_fills_defaults(self):
        from dashboard import _schedule_to_standup

        row = {"id": 1}
        result = _schedule_to_standup(row)
        assert result["id"] == 1
        assert result["name"] == "Morning Standup"
        assert result["schedule_days"] == ["mon", "tue", "wed", "thu", "fri"]
        assert isinstance(result["questions"], list)
        assert isinstance(result["participants"], list)

    def test_json_string_questions_parsed(self):
        from dashboard import _schedule_to_standup

        row = {"id": 2, "questions": '["Q1","Q2"]', "participants": "[]"}
        result = _schedule_to_standup(row)
        assert result["questions"] == ["Q1", "Q2"]

    def test_schedule_days_split(self):
        from dashboard import _schedule_to_standup

        row = {"id": 3, "schedule_days": "mon,wed,fri"}
        result = _schedule_to_standup(row)
        assert result["schedule_days"] == ["mon", "wed", "fri"]
