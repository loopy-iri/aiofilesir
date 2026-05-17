"""Verify the ``/file-entries`` vs ``/file_entries`` URL quirk for shareable links."""
from __future__ import annotations

import httpx
import pytest

from filesir import FilesIrClient


def make_client(handler) -> FilesIrClient:
    mock = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=mock)
    return FilesIrClient(access_token="t", base_url="https://api.example.com", http_client=http)


@pytest.mark.asyncio
async def test_get_uses_hyphen_path() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"status": "success", "link": None})

    client = make_client(handler)
    async with client:
        await client.links.get(42)
    assert seen == ["/file-entries/42/shareable-link"]


@pytest.mark.asyncio
async def test_create_uses_hyphen_path() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={"status": "success", "link": {"id": 1}})

    client = make_client(handler)
    async with client:
        await client.links.create(7, password="pw")
    assert seen == [("POST", "/file-entries/7/shareable-link")]


@pytest.mark.asyncio
async def test_update_uses_underscore_path() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={"status": "success", "link": {"id": 1}})

    client = make_client(handler)
    async with client:
        await client.links.update(13, allow_edit=True)
    assert seen == [("PUT", "/file_entries/13/shareable-link")]


@pytest.mark.asyncio
async def test_delete_uses_underscore_path() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={"status": "success"})

    client = make_client(handler)
    async with client:
        await client.links.delete(99)
    assert seen == [("DELETE", "/file_entries/99/shareable-link")]
