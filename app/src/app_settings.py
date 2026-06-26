"""Runtime settings stored in the DB, with environment variables as bootstrap defaults."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def get_setting(key: str, default: str = "") -> str:
    """Return a Dashboard-managed setting, falling back to the environment."""
    try:
        import db  # noqa: PLC0415

        value = db.get_app_setting(key)
        if isinstance(value, str):
            return value
    except Exception as exc:
        logger.debug("Could not read app setting %s: %s", key, exc)
    return os.environ.get(key, default)


def get_bool_setting(key: str, default: bool = False) -> bool:
    value = get_setting(key, "true" if default else "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def get_int_setting(key: str, default: int = 0) -> int:
    try:
        return int(get_setting(key, str(default)))
    except ValueError:
        return default
