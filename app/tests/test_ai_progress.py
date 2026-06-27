"""Tests for progress normalization validation."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from ai_progress import validate_progress_payload  # noqa: E402


def test_validate_progress_payload_maps_existing_project():
    result = validate_progress_payload(
        {"project_name": "晨序", "role": "后端", "content": "完成飞书长连接测试。"},
        raw_answers=["完成飞书长连接测试。"],
        projects=[{"id": 7, "name": "晨序"}],
        member={"tags": ["工程"]},
    )

    assert result["valid"] is True
    assert result["project_id"] == 7
    assert result["project_name"] == "晨序"
    assert result["role"] == "后端"
    assert result["content"] == "完成飞书长连接测试。"


def test_validate_progress_payload_rejects_unknown_project():
    result = validate_progress_payload(
        {"project_name": "不存在的项目", "role": "后端", "content": "完成接口联调。"},
        raw_answers=["完成接口联调。"],
        projects=[{"id": 7, "name": "晨序"}],
        member={"tags": ["工程"]},
    )

    assert result["valid"] is False
    assert result["project_id"] is None
    assert result["project_name"] == "未归属项目"
    assert result["validation_errors"] == ["项目不存在：不存在的项目"]


def test_validate_progress_payload_rejects_empty_content():
    result = validate_progress_payload(
        {"project_name": "未归属项目", "role": "后端", "content": ""},
        raw_answers=[],
        projects=[],
        member={"tags": ["工程"]},
    )

    assert result["valid"] is False
    assert result["validation_errors"] == ["进度内容不能为空"]
