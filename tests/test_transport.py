"""Transport-level tests using :class:`httpx.MockTransport`."""
from __future__ import annotations

import httpx
import pytest

from filesir.exceptions import (
    AuthenticationError,
    ForbiddenError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from filesir.transport import RetryPolicy, Transport


def make_transport(handler, retry: RetryPolicy | None = None) -> Transport:
    mock = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=mock)
    return Transport(
        base_url="https://api.example.com",
        retry=retry or RetryPolicy(max_attempts=2, initial_backoff=0.001, backoff_jitter=0.0),
        http_client=client,
    )


@pytest.mark.asyncio
async def test_authenticated_call_injects_bearer() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    t = make_transport(handler)
    t.set_access_token("abc123")
    try:
        body = await t.request_json("GET", "/foo")
        assert body == {"ok": True}
        assert seen[0].headers["Authorization"] == "Bearer abc123"
    finally:
        await t.aclose()


@pytest.mark.asyncio
async def test_authenticated_call_without_token_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    t = make_transport(handler)
    try:
        with pytest.raises(AuthenticationError):
            await t.request_json("GET", "/foo")
    finally:
        await t.aclose()


@pytest.mark.asyncio
async def test_unauthenticated_call_omits_bearer_even_when_token_set() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    t = make_transport(handler)
    t.set_access_token("secret")
    try:
        await t.request_json("POST", "/auth/login", json={"x": 1}, authenticated=False)
        assert "Authorization" not in seen[0].headers
    finally:
        await t.aclose()


@pytest.mark.asyncio
async def test_status_to_exception_mapping() -> None:
    cases = [
        (401, AuthenticationError),
        (403, ForbiddenError),
        (404, NotFoundError),
        (422, ValidationError),
        (500, ServerError),
    ]
    for status, exc in cases:
        body = (
            {"message": "validation failed", "errors": {"email": ["bad"]}}
            if status == 422
            else {"message": "oops"}
        )

        def handler(request: httpx.Request, _body=body, _status=status) -> httpx.Response:
            return httpx.Response(_status, json=_body)

        t = make_transport(
            handler, retry=RetryPolicy(max_attempts=1, backoff_jitter=0.0),
        )
        t.set_access_token("x")
        try:
            with pytest.raises(exc) as info:
                await t.request_json("GET", "/foo")
            if status == 422:
                assert isinstance(info.value, ValidationError)
                assert info.value.errors == {"email": "bad"}
        finally:
            await t.aclose()


@pytest.mark.asyncio
async def test_retries_exhausted_raises_server_error() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"message": "down"})

    t = make_transport(
        lambda r: handler(r),
        retry=RetryPolicy(max_attempts=3, initial_backoff=0.001, backoff_jitter=0.0),
    )
    t.set_access_token("x")
    try:
        with pytest.raises(ServerError):
            await t.request_json("GET", "/foo")
        assert calls["n"] == 3
    finally:
        await t.aclose()


@pytest.mark.asyncio
async def test_retry_then_success() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"message": "down"})
        return httpx.Response(200, json={"ok": True})

    t = make_transport(
        handler,
        retry=RetryPolicy(max_attempts=3, initial_backoff=0.001, backoff_jitter=0.0),
    )
    t.set_access_token("x")
    try:
        body = await t.request_json("GET", "/foo")
        assert body == {"ok": True}
        assert calls["n"] == 3
    finally:
        await t.aclose()


@pytest.mark.asyncio
async def test_429_with_retry_after_then_rate_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "slow"}, headers={"Retry-After": "0"})

    t = make_transport(
        handler,
        retry=RetryPolicy(max_attempts=2, initial_backoff=0.001, backoff_jitter=0.0),
    )
    t.set_access_token("x")
    try:
        with pytest.raises(RateLimitError) as info:
            await t.request_json("GET", "/foo")
        assert info.value.retry_after == 0.0
    finally:
        await t.aclose()


@pytest.mark.asyncio
async def test_transport_error_wraps_to_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    t = make_transport(
        handler,
        retry=RetryPolicy(max_attempts=1, backoff_jitter=0.0),
    )
    t.set_access_token("x")
    try:
        with pytest.raises(NetworkError):
            await t.request_json("GET", "/foo")
    finally:
        await t.aclose()


@pytest.mark.asyncio
async def test_clean_params_serializes_lists_and_bools() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    t = make_transport(handler)
    t.set_access_token("x")
    try:
        await t.request_json(
            "GET",
            "/foo",
            params={"parentIds": ["a", "b", "c"], "deletedOnly": True, "skip": None},
        )
        url = str(seen[0].url)
        assert "parentIds=a%2Cb%2Cc" in url or "parentIds=a,b,c" in url
        assert "deletedOnly=true" in url
        assert "skip" not in url
    finally:
        await t.aclose()


@pytest.mark.asyncio
async def test_external_put_omits_bearer() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"ETag": '"deadbeef"'})

    t = make_transport(handler)
    t.set_access_token("secret")
    try:
        response = await t.external_put(
            "https://s3.example.com/bucket/key",
            content=b"abc",
            content_length=3,
            headers={"x-amz-acl": "private"},
        )
        assert response.headers["ETag"] == '"deadbeef"'
        assert "Authorization" not in seen[0].headers
        assert seen[0].headers["x-amz-acl"] == "private"
        assert seen[0].headers["Content-Length"] == "3"
    finally:
        await t.aclose()
