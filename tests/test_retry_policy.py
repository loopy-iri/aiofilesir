"""Unit tests for :class:`RetryPolicy` and the retry helpers."""
from __future__ import annotations

import httpx
import pytest

from filesir.transport import RetryPolicy, parse_retry_after


def test_should_retry_on_5xx_when_attempts_remain() -> None:
    policy = RetryPolicy(max_attempts=3, backoff_jitter=0.0)
    assert policy.should_retry(1, 503) is True
    assert policy.should_retry(2, 503) is True
    assert policy.should_retry(3, 503) is False


def test_should_retry_on_transport_error() -> None:
    policy = RetryPolicy(max_attempts=2, backoff_jitter=0.0)
    err = httpx.ConnectError("boom")
    assert policy.should_retry(1, err) is True
    # Non-retryable status code should not retry.
    assert policy.should_retry(1, 404) is False


def test_next_delay_respects_retry_after_cap() -> None:
    policy = RetryPolicy(initial_backoff=1, max_backoff=5, backoff_jitter=0.0)
    assert policy.next_delay(1, retry_after=2.0) == 2.0
    assert policy.next_delay(1, retry_after=100.0) == 5.0


def test_next_delay_exponential_growth_no_jitter() -> None:
    policy = RetryPolicy(
        max_attempts=4,
        initial_backoff=1.0,
        max_backoff=8.0,
        backoff_multiplier=2.0,
        backoff_jitter=0.0,
    )
    assert policy.next_delay(1, None) == 1.0
    assert policy.next_delay(2, None) == 2.0
    assert policy.next_delay(3, None) == 4.0
    assert policy.next_delay(4, None) == 8.0  # capped


def test_parse_retry_after_seconds_and_date() -> None:
    assert parse_retry_after("3") == 3.0
    assert parse_retry_after("0") == 0.0
    assert parse_retry_after("") is None
    assert parse_retry_after(None) is None
    # HTTP-date in the past should clamp to 0.
    past = "Wed, 21 Oct 2015 07:28:00 GMT"
    parsed = parse_retry_after(past)
    assert parsed is not None and parsed >= 0.0


def test_invalid_policy_construction_raises() -> None:
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError):
        RetryPolicy(initial_backoff=0)
    with pytest.raises(ValueError):
        RetryPolicy(initial_backoff=2, max_backoff=1)
    with pytest.raises(ValueError):
        RetryPolicy(backoff_multiplier=0.5)
    with pytest.raises(ValueError):
        RetryPolicy(backoff_jitter=2.0)
