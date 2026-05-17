"""Resource façade wire-shape tests via :class:`httpx.MockTransport`."""
from __future__ import annotations

import httpx
import pytest

from filesir import FilesIrClient
from filesir.exceptions import ValidationError


def build_client(handler) -> FilesIrClient:
    mock = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=mock)
    return FilesIrClient(
        access_token="tok",
        base_url="https://api.example.com",
        http_client=http,
    )


@pytest.mark.asyncio
async def test_storage_space_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path.endswith("/user/space-usage")
        return httpx.Response(200, json={
            "status": "success", "used": 100, "available": None, "remaining": None,
        })

    client = build_client(handler)
    async with client:
        usage = await client.storage.space_usage()
        assert usage.used == 100
        assert usage.available is None


@pytest.mark.asyncio
async def test_files_list_serializes_parent_ids_and_filters() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[
            {"id": 1, "name": "a"},
            {"id": 2, "name": "b"},
        ])

    client = build_client(handler)
    async with client:
        entries = await client.files.list(
            parent_ids=["10", "20"],
            type="image",
            workspace_id=5,
            deleted_only=False,
        )
        assert [e.id for e in entries] == [1, 2]
        url = str(seen[0].url)
        assert "parentIds=10%2C20" in url or "parentIds=10,20" in url
        assert "type=image" in url
        assert "workspaceId=5" in url
        assert "deletedOnly=false" in url


@pytest.mark.asyncio
async def test_files_delete_empty_raises_client_side() -> None:
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json={"status": "success"})

    client = build_client(handler)
    async with client:
        with pytest.raises(ValidationError):
            await client.files.delete([])
        assert called["n"] == 0


@pytest.mark.asyncio
async def test_folders_create_returns_file_entry() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/folders")
        body = httpx.Request("POST", request.url, content=request.content).read()
        assert b"new-folder" in body
        return httpx.Response(200, json={
            "status": "success",
            "folder": {"id": 99, "name": "new-folder", "type": "folder"},
        })

    client = build_client(handler)
    async with client:
        folder = await client.folders.create(name="new-folder")
        assert folder.id == 99 and folder.name == "new-folder"


@pytest.mark.asyncio
async def test_share_validates_permissions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "success", "users": []})

    client = build_client(handler)
    async with client:
        with pytest.raises(ValidationError):
            await client.sharing.share(1, emails=["a@b"], permissions=[])
        with pytest.raises(ValidationError):
            await client.sharing.share(
                1, emails=["a@b"], permissions=["bogus"],  # type: ignore[list-item]
            )


@pytest.mark.asyncio
async def test_starring_returns_tag() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "status": "success", "tag": {"id": 1, "name": "starred"},
        })

    client = build_client(handler)
    async with client:
        tag = await client.starring.star([1, 2])
        assert tag.id == 1 and tag.name == "starred"


@pytest.mark.asyncio
async def test_workspaces_pagination_iter_all() -> None:
    pages = {
        1: {
            "status": "success",
            "pagination": {
                "data": [{"id": 1, "name": "a", "owner_id": 1, "members_count": 0}],
                "current_page": 1,
                "per_page": 1,
                "last_page": 2,
                "total": 2,
            },
        },
        2: {
            "status": "success",
            "pagination": {
                "data": [{"id": 2, "name": "b", "owner_id": 1, "members_count": 0}],
                "current_page": 2,
                "per_page": 1,
                "last_page": 2,
                "total": 2,
            },
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json=pages[page])

    client = build_client(handler)
    async with client:
        ids = [ws.id async for ws in client.workspaces.iter_all(per_page=1)]
        assert ids == [1, 2]


@pytest.mark.asyncio
async def test_workspaces_delete_with_list_uses_comma_path() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"status": "success"})

    client = build_client(handler)
    async with client:
        await client.workspaces.delete([5, 6, 7])
        assert seen[-1].endswith("/workspace/5,6,7")
