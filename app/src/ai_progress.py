"""AI-assisted normalization for progress collection."""

from __future__ import annotations

import json
import logging

from app_settings import get_setting

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = """你是团队进度整理助手。根据成员原始回复，结合已知项目、成员岗位、上一次提交，把内容整理成准确、简洁、可入库的中文进度。

要求：
1. 不编造事实，不扩写不存在的进展。
2. 优先匹配已有项目名；无法判断项目时使用“未归属项目”。
3. 输出 JSON，字段为 project_name、role、content。
4. content 是用户确认后要入库的最终进度正文，用 2-5 行描述事实进展、下一步和风险阻塞。
5. project_name 必须等于输入 projects 中已有的 name，或等于“未归属项目”。
"""


def normalize_progress(
    *,
    raw_answers: list[str],
    conversation: list[dict] | None = None,
    projects: list[dict],
    member: dict | None,
    previous_entry: dict | None,
    provider: str | None = None,
    feedback: str = "",
) -> dict:
    if not raw_answers:
        return _fallback(raw_answers, member, projects)

    payload = {
        "member": member or {},
        "projects": [{"id": p.get("id"), "name": p.get("name"), "description": p.get("description", "")} for p in projects],
        "previous_entry": previous_entry or {},
        "raw_answers": raw_answers,
        "conversation": conversation or [],
        "feedback": feedback,
    }
    provider = (provider or get_setting("FEISHU_AI_PROVIDER", "deepseek")).strip().lower()
    if provider == "anthropic":
        return _fallback(raw_answers, member, projects)

    key = get_setting("DEEPSEEK_API_KEY") if provider == "deepseek" else get_setting("OPENAI_API_KEY")
    if not key:
        return _fallback(raw_answers, member, projects)

    base_url = get_setting("DEEPSEEK_BASE_URL", "https://api.deepseek.com") if provider == "deepseek" else "https://api.openai.com"
    model = get_setting("DEEPSEEK_MODEL", "deepseek-chat") if provider == "deepseek" else "gpt-4o-mini"

    try:
        import httpx

        response = httpx.post(
            _chat_completions_url(base_url),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _DEFAULT_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
                ],
                "temperature": 0.2,
                "max_tokens": 700,
                "response_format": {"type": "json_object"},
            },
            timeout=20,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        result = validate_progress_payload(data, raw_answers=raw_answers, projects=projects, member=member)
        if result["valid"]:
            return result
        logger.warning("Progress normalization validation failed: %s", result["validation_errors"])
        return _fallback(raw_answers, member, projects)
    except Exception as exc:
        logger.warning("Progress normalization failed: %s", exc)
        return _fallback(raw_answers, member, projects)


def _chat_completions_url(base_url: str) -> str:
    base = (base_url or "https://api.deepseek.com").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def validate_progress_payload(
    data: dict,
    *,
    raw_answers: list[str],
    projects: list[dict],
    member: dict | None,
) -> dict:
    errors: list[str] = []
    project_index = {_clean_text(project.get("name")): project for project in projects if _clean_text(project.get("name"))}
    project_name = _clean_text(data.get("project_name")) or "未归属项目"
    project_id = None
    if project_name != "未归属项目":
        project = project_index.get(project_name)
        if project:
            project_id = int(project["id"]) if project.get("id") is not None else None
        else:
            errors.append(f"项目不存在：{project_name}")

    role = _clean_text(data.get("role")) or _member_role(member)
    content = _clean_text(data.get("content"))
    if not content:
        errors.append("进度内容不能为空")

    return {
        "valid": not errors,
        "validation_errors": errors,
        "project_id": project_id,
        "project_name": project_name if not errors else "未归属项目",
        "role": role,
        "content": content,
    }


def _fallback(raw_answers: list[str], member: dict | None, projects: list[dict]) -> dict:
    lines = [answer.strip() for answer in raw_answers if answer and answer.strip()]
    text = "\n".join(lines)
    result = {
        "project_name": "未归属项目",
        "role": _member_role(member),
        "content": text,
    }
    return validate_progress_payload(result, raw_answers=raw_answers, projects=projects, member=member)


def _member_role(member: dict | None) -> str:
    if not member:
        return ""
    tags = member.get("tags") or []
    return "、".join(tags) if isinstance(tags, list) else str(tags or "")


def _clean_text(value) -> str:
    return str(value or "").strip()
