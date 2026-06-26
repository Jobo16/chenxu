"""Tests for Feishu bootstrap helpers."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))


def test_parse_feishu_channels_skips_placeholder_ids():
    from feishu_bootstrap import parse_feishu_channels

    channels = parse_feishu_channels("oc_demo|Demo,oc_real|研发群")

    assert channels == [{"id": "oc_real", "name": "研发群"}]


def test_ensure_feishu_workspace_clears_stale_default_channel(monkeypatch):
    monkeypatch.setenv("FEISHU_APP_ID", "cli_x")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    monkeypatch.setenv("FEISHU_DEFAULT_CHAT_ID", "")

    db_mock = MagicMock()
    prior_db = sys.modules.get("db")
    sys.modules["db"] = db_mock
    try:
        from feishu_bootstrap import ensure_feishu_workspace

        ensure_feishu_workspace()
    finally:
        if prior_db is not None:
            sys.modules["db"] = prior_db
        else:
            sys.modules.pop("db", None)

    kwargs = db_mock.upsert_workspace_config.call_args.kwargs
    assert "channel_id" in kwargs
    assert kwargs["channel_id"] is None
