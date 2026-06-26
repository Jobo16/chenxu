"""AI-powered standup summary generator.

Uses OpenAI (gpt-4o-mini), DeepSeek, or Anthropic (claude-haiku) to generate
a concise paragraph summarising the team's standup responses.

Requires provider API keys from Dashboard settings or env.
Falls back to a plain bullet-point summary if no key is set.
"""

from __future__ import annotations

import logging

from app_settings import get_setting

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a team standup summariser. Given a list of standup updates from team members, write a single cohesive paragraph (3-5 sentences) that:
1. Highlights the key themes of what the team worked on yesterday
2. Notes what the team is focused on today
3. Calls out any blockers or risks

Be concise, professional, and use "the team" language. Do not list every person individually."""


def generate_summary(standups: list[dict], team_name: str = "", provider: str | None = None) -> str:
    """Generate an AI summary paragraph from standup data.

    Falls back to plain list summary if no API key configured.
    """
    if not standups:
        return ""

    # Build the standup text
    lines = []
    for s in standups:
        name = s.get("user_id", "Unknown")
        lines.append(
            f"{name}:\n"
            f"  Yesterday: {s.get('yesterday', '')}\n"
            f"  Today: {s.get('today', '')}\n"
            f"  Blockers: {s.get('blockers', '')}"
        )
    standup_text = "\n\n".join(lines)

    provider = (provider or "").strip().lower()
    openai_key = get_setting("OPENAI_API_KEY")
    anthropic_key = get_setting("ANTHROPIC_API_KEY")
    deepseek_key = get_setting("DEEPSEEK_API_KEY")

    if provider == "openai":
        return _openai_summary(standup_text, team_name, openai_key) if openai_key else ""
    if provider == "anthropic":
        return _anthropic_summary(standup_text, team_name, anthropic_key) if anthropic_key else ""
    if provider == "deepseek":
        return _deepseek_summary(standup_text, team_name, deepseek_key) if deepseek_key else ""

    if openai_key:
        return _openai_summary(standup_text, team_name, openai_key)
    if deepseek_key:
        return _deepseek_summary(standup_text, team_name, deepseek_key)
    if anthropic_key:
        return _anthropic_summary(standup_text, team_name, anthropic_key)

    # Fallback: plain summary
    return _plain_summary(standups, team_name)


def _openai_summary(text: str, team_name: str, api_key: str) -> str:
    return _openai_compatible_summary(
        text=text,
        team_name=team_name,
        api_key=api_key,
        base_url="https://api.openai.com",
        model="gpt-4o-mini",
        provider_name="OpenAI",
    )


def _deepseek_summary(text: str, team_name: str, api_key: str) -> str:
    return _openai_compatible_summary(
        text=text,
        team_name=team_name,
        api_key=api_key,
        base_url=get_setting("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=get_setting("DEEPSEEK_MODEL", "deepseek-chat"),
        provider_name="DeepSeek",
    )


def _openai_compatible_summary(
    *,
    text: str,
    team_name: str,
    api_key: str,
    base_url: str,
    model: str,
    provider_name: str,
) -> str:
    try:
        import httpx

        response = httpx.post(
            _chat_completions_url(base_url),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"Team: {team_name}\n\nStandups:\n{text}"},
                ],
                "max_tokens": 300,
                "temperature": 0.4,
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("%s summary failed: %s", provider_name, exc)
        return ""


def _chat_completions_url(base_url: str) -> str:
    base = (base_url or "https://api.deepseek.com").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _anthropic_summary(text: str, team_name: str, api_key: str) -> str:
    try:
        import httpx

        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-haiku-20240307",
                "max_tokens": 300,
                "system": _SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": f"Team: {team_name}\n\nStandups:\n{text}"},
                ],
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"].strip()
    except Exception as exc:
        logger.warning("Anthropic summary failed: %s", exc)
        return ""


def _plain_summary(standups: list[dict], team_name: str) -> str:
    """Plain text summary — no AI needed."""
    total = len(standups)
    with_blockers = sum(1 for s in standups if s.get("has_blockers"))

    summary = f"📊 *Team Summary* — {total} standup{'s' if total != 1 else ''} submitted"
    if team_name:
        summary = f"📊 *{team_name} Summary* — {total} standup{'s' if total != 1 else ''} submitted"

    if with_blockers:
        summary += f"\n⚠️ {with_blockers} team member{'s' if with_blockers != 1 else ''} reported blockers"

    return summary
