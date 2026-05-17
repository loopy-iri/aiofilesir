"""Auth resource and ``from_credentials`` flow tests."""
from __future__ import annotations

import httpx
import pytest

from filesir import FilesIrClient


def make_handler(seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={
                "status": "success",
                "user": {"id": 1, "access_token": "tok-from-login"},
            })
        if request.url.path.endswith("/auth/register"):
            return httpx.Response(200, json={
                "status": "success",
                "user": {"id": 2, "access_token": "tok-from-register"},
            })
        if request.url.path.endswith("/user/space-usage"):
            return httpx.Response(200, json={"used": 1, "available": 2, "remaining": 1})
        return httpx.Response(404)

    return handler


@pytest.mark.asyncio
async def test_login_does_not_send_authorization() -> None:
    seen: list[httpx.Request] = []
    mock = httpx.MockTransport(make_handler(seen))
    http = httpx.AsyncClient(transport=mock)
    client = FilesIrClient(
        access_token="pre-existing",
        base_url="https://api.example.com",
        http_client=http,
    )
    async with client:
        user = await client.auth.login(email="a@b", password="x")
    assert user.access_token == "tok-from-login"
    login_req = next(r for r in seen if r.url.path.endswith("/auth/login"))
    assert "Authorization" not in login_req.headers


@pytest.mark.asyncio
async def test_from_credentials_logs_in_and_sets_token() -> None:
    seen: list[httpx.Request] = []
    mock = httpx.MockTransport(make_handler(seen))
    http = httpx.AsyncClient(transport=mock)
    client = await FilesIrClient.from_credentials(
        email="me@x", password="pw",
        base_url="https://api.example.com",
        http_client=http,
    )
    try:
        assert client.access_token == "tok-from-login"
        # Subsequent authenticated call should include the new token.
        await client.storage.space_usage()
        usage_req = next(r for r in seen if r.url.path.endswith("/user/space-usage"))
        assert usage_req.headers["Authorization"] == "Bearer tok-from-login"
    finally:
        await client.aclose()
