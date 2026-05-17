"""Logging helpers for the Files.ir client.

The :class:`AuthorizationRedactor` filter rewrites any occurrence of an
``Authorization: Bearer ...`` header (case-insensitive) inside a log record's
formatted message and inside its ``extra`` dict, so the plaintext token never
appears in logs even if the user enabled httpx debug logging.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("filesir")

_BEARER_PATTERN = re.compile(
    r"(?i)(authorization\s*[:=]\s*['\"]?bearer\s+)([A-Za-z0-9._\-+/=]+)",
)
_HEADER_VALUE_PATTERN = re.compile(r"(?i)^bearer\s+([A-Za-z0-9._\-+/=]+)$")


def _redact_text(text: str) -> str:
    return _BEARER_PATTERN.sub(r"\1***", text)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        if _HEADER_VALUE_PATTERN.match(value):
            return "Bearer ***"
        return _redact_text(value)
    if isinstance(value, dict):
        return {k: ("Bearer ***" if str(k).lower() == "authorization" else _redact_value(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(v) for v in value)
    return value


class AuthorizationRedactor(logging.Filter):
    """Logging filter that strips Bearer tokens from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            msg = str(record.msg)
        record.msg = _redact_text(msg)
        record.args = ()
        # Best-effort redact arbitrary extras attached to the record.
        for attr_name in tuple(vars(record).keys()):
            if attr_name in {"msg", "args", "message"}:
                continue
            value = getattr(record, attr_name, None)
            if isinstance(value, (str, dict, list, tuple)):
                setattr(record, attr_name, _redact_value(value))
        return True


_default_filter_installed = False


def install_default_redactor() -> None:
    """Attach :class:`AuthorizationRedactor` to the ``filesir`` logger.

    Idempotent. Safe to call multiple times.
    """

    global _default_filter_installed
    if _default_filter_installed:
        return
    logger.addFilter(AuthorizationRedactor())
    _default_filter_installed = True


__all__ = ["AuthorizationRedactor", "install_default_redactor", "logger"]
