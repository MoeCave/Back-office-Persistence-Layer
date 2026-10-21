"""Payload validation helpers shared by the router and the services.

Every helper raises :class:`~src.server.errors.ValidationError` so that
malformed input is reported to the client instead of being silently
ignored or turned into an internal error.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from src.server.errors import ValidationError

_DATETIME_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M")


def clean_str(value: Any) -> str:
    """Return *value* stripped, or ``""`` if it is not a string."""
    return value.strip() if isinstance(value, str) else ""


def require_int(payload: dict[str, Any], key: str) -> int:
    """Extract a required integer field from *payload*."""
    value = payload.get(key)
    if value is None:
        raise ValidationError(f"Missing required field: '{key}'.")
    return _to_int(value, key)


def optional_int(payload: dict[str, Any], key: str) -> int | None:
    """Extract an optional integer field (``None`` when absent)."""
    value = payload.get(key)
    return None if value is None else _to_int(value, key)


def optional_number(payload: dict[str, Any], key: str) -> float | None:
    """Extract an optional numeric field (``None`` when absent)."""
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValidationError(f"Field '{key}' must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"Field '{key}' must be a number.") from None
    if not math.isfinite(number):
        raise ValidationError(f"Field '{key}' must be a finite number.")
    return number


def pagination(payload: dict[str, Any], max_page_size: int = 100):
    """Return a validated ``(page, page_size)`` pair."""
    page = optional_int(payload, "page")
    page_size = optional_int(payload, "page_size")
    page = 1 if page is None else page
    page_size = 10 if page_size is None else page_size
    if page < 1:
        raise ValidationError("Field 'page' must be >= 1.")
    if not 1 <= page_size <= max_page_size:
        raise ValidationError(
            f"Field 'page_size' must be between 1 and {max_page_size}."
        )
    return page, page_size


def parse_datetime(value: Any, key: str) -> datetime | None:
    """Parse ``YYYY-MM-DD``, ``YYYY-MM-DD HH:MM`` or ISO-8601 text.

    Returns ``None`` for empty values and raises ``ValidationError`` for
    anything that cannot be parsed.
    """
    if value in (None, ""):
        return None
    if isinstance(value, str):
        for fmt in _DATETIME_FORMATS:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    raise ValidationError(
        f"Field '{key}' must be a date like 'YYYY-MM-DD' "
        "or 'YYYY-MM-DD HH:MM'."
    )


def _to_int(value: Any, key: str) -> int:
    message = f"Field '{key}' must be an integer."
    if isinstance(value, bool):
        raise ValidationError(message)
    if isinstance(value, float) and not (
        math.isfinite(value) and value.is_integer()
    ):
        raise ValidationError(message)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError(message) from None
