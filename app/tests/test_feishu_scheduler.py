"""Tests for Feishu scheduler reporting."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))


def test_feishu_report_posts_ai_summary_when_enabled():
    import scheduler

    db_mock = MagicMock()
    db_mock.get_active_members.return_value = [{"user_id": "ou_1", "real_name": "Alice"}]
    db_mock.get_workspace_config.return_value = {"ai_summary_enabled": True, "ai_provider": "deepseek"}
    db_mock.get_installation.return_value = {"team_name": "Engineering"}

    adapter = MagicMock()
    standups = [
        {
            "user_id": "ou_1",
            "yesterday": "完成登录页",
            "today": "接入飞书机器人",
            "blockers": "无",
            "has_blockers": False,
        }
    ]

    with patch.dict(sys.modules, {"db": db_mock}):
        with patch.object(scheduler, "_get_feishu_adapter", return_value=adapter):
            with patch("ai_summary.generate_summary", return_value="团队昨天完成登录页，今天继续接入飞书机器人。") as summary:
                scheduler._post_feishu_scheduled_report("feishu", "oc_1", None, standups, ["昨天", "今天", "阻塞"])

    assert adapter.post_to_channel.call_count == 2
    assert adapter.post_to_channel.call_args_list[0].args[0] == "oc_1"
    assert "每日站会汇总" in adapter.post_to_channel.call_args_list[0].args[1]
    assert "AI Summary" in adapter.post_to_channel.call_args_list[1].args[1]
    assert summary.call_args.kwargs["provider"] == "deepseek"


def test_feishu_report_skips_ai_summary_when_disabled():
    import scheduler

    db_mock = MagicMock()
    db_mock.get_active_members.return_value = [{"user_id": "ou_1", "real_name": "Alice"}]
    db_mock.get_workspace_config.return_value = {"ai_summary_enabled": False}

    adapter = MagicMock()
    standups = [{"user_id": "ou_1", "yesterday": "a", "today": "b", "blockers": "无"}]

    with patch.dict(sys.modules, {"db": db_mock}):
        with patch.object(scheduler, "_get_feishu_adapter", return_value=adapter):
            scheduler._post_feishu_scheduled_report("feishu", "oc_1", None, standups, None)

    adapter.post_to_channel.assert_called_once()
