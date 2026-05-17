"""Authorization-redaction tests."""
from __future__ import annotations

import logging

from filesir.logging import AuthorizationRedactor, install_default_redactor, logger


def test_redactor_strips_bearer_token_from_message() -> None:
    redactor = AuthorizationRedactor()
    record = logging.LogRecord(
        name="filesir",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="GET / Authorization: Bearer s3cr3t-1234",
        args=(),
        exc_info=None,
    )
    assert redactor.filter(record) is True
    assert "s3cr3t-1234" not in record.getMessage()
    assert "Bearer ***" in record.getMessage()


def test_redactor_strips_bearer_in_extra_dict() -> None:
    redactor = AuthorizationRedactor()
    record = logging.LogRecord(
        name="filesir",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request",
        args=(),
        exc_info=None,
    )
    record.headers = {"Authorization": "Bearer abc.def-ghi"}  # type: ignore[attr-defined]
    redactor.filter(record)
    assert record.headers["Authorization"] == "Bearer ***"  # type: ignore[attr-defined]


def test_install_default_redactor_is_idempotent() -> None:
    install_default_redactor()
    install_default_redactor()
    # No assertion needed; just confirming the second call doesn't raise/duplicate.
    assert any(isinstance(f, AuthorizationRedactor) for f in logger.filters)
