"""Tests for ``FilesResource.direct_download_url``."""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from filesir import FilesIrClient


def make_client(token: str | None = "tok") -> FilesIrClient:
    mock = httpx.MockTransport(lambda r: httpx.Response(404))
    http = httpx.AsyncClient(transport=mock)
    return FilesIrClient(
        access_token=token,
        base_url="https://api.example.com/v1",
        http_client=http,
    )


@pytest.mark.asyncio
async def test_direct_url_uses_client_token_by_default() -> None:
    client = make_client(token="my-token")
    async with client:
        url = client.files.direct_download_url(42)
    split = urlsplit(url)
    qs = parse_qs(split.query)
    assert split.path == "/v1/file-entries/42"
    assert qs["accessToken"] == ["my-token"]


@pytest.mark.asyncio
async def test_direct_url_explicit_token_overrides_client_token() -> None:
    client = make_client(token="default-tok")
    async with client:
        url = client.files.direct_download_url(7, access_token="other")
    qs = parse_qs(urlsplit(url).query)
    assert qs["accessToken"] == ["other"]


@pytest.mark.asyncio
async def test_direct_url_empty_string_omits_token() -> None:
    client = make_client(token="default-tok")
    async with client:
        url = client.files.direct_download_url(7, access_token="")
    qs = parse_qs(urlsplit(url).query)
    assert "accessToken" not in qs


@pytest.mark.asyncio
async def test_direct_url_includes_thumbnail_and_preview_token() -> None:
    client = make_client(token="x")
    async with client:
        url = client.files.direct_download_url(
            10, access_token="", thumbnail=True, preview_token="pv-1",
        )
    qs = parse_qs(urlsplit(url).query)
    assert qs["thumbnail"] == ["1"]
    assert qs["preview_token"] == ["pv-1"]
    assert "accessToken" not in qs


@pytest.mark.asyncio
async def test_direct_url_with_no_token_and_no_options_is_bare() -> None:
    client = make_client(token=None)
    async with client:
        url = client.files.direct_download_url(99)
    assert url == "https://api.example.com/v1/file-entries/99"
