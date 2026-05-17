"""``/drive/file-entries`` and ``/file-entries/*`` endpoints."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Sequence
from urllib.parse import quote, urlencode

from ..exceptions import ValidationError
from ..models import FileEntry, FileEntryType
from ..transport import StreamingResponse
from .base import BaseResource


def _require_non_empty(values: Sequence[object], name: str) -> None:
    if len(values) == 0:
        raise ValidationError(f"{name} must be a non-empty sequence")


def _entries_from_envelope(data: object) -> list[FileEntry]:
    if isinstance(data, dict):
        items = data.get("entries", data.get("data", []))
    else:
        items = data
    if not isinstance(items, list):
        return []
    return [FileEntry.model_validate(x) for x in items]


def _entry_from_envelope(data: object) -> FileEntry:
    if isinstance(data, dict) and "fileEntry" in data:
        return FileEntry.model_validate(data["fileEntry"])
    return FileEntry.model_validate(data)


class FilesResource(BaseResource):
    """File-entry CRUD, list, move, duplicate, restore, and download."""

    async def list(
        self,
        *,
        per_page: int = 50,
        deleted_only: bool | None = None,
        starred_only: bool | None = None,
        recent_only: bool | None = None,
        shared_only: bool | None = None,
        query: str | None = None,
        type: FileEntryType | None = None,
        parent_ids: Sequence[str] | None = None,
        workspace_id: int | None = None,
    ) -> list[FileEntry]:
        params: dict[str, object] = {"perPage": per_page}
        if deleted_only is not None:
            params["deletedOnly"] = deleted_only
        if starred_only is not None:
            params["starredOnly"] = starred_only
        if recent_only is not None:
            params["recentOnly"] = recent_only
        if shared_only is not None:
            params["sharedOnly"] = shared_only
        if query is not None:
            params["query"] = query
        if type is not None:
            params["type"] = type
        if parent_ids is not None:
            params["parentIds"] = list(parent_ids)
        if workspace_id is not None:
            params["workspaceId"] = workspace_id
        data = await self._transport.request_json(
            "GET", "/drive/file-entries", params=params,
        )
        if isinstance(data, list):
            return [FileEntry.model_validate(x) for x in data]
        if isinstance(data, dict):
            for key in ("data", "entries", "fileEntries"):
                items = data.get(key)
                if isinstance(items, list):
                    return [FileEntry.model_validate(x) for x in items]
        return []

    async def delete(
        self,
        entry_ids: Sequence[str],
        *,
        delete_forever: bool = False,
    ) -> None:
        _require_non_empty(entry_ids, "entry_ids")
        body = {
            "entryIds": list(entry_ids),
            "deleteForever": delete_forever,
        }
        await self._transport.request_json(
            "POST", "/file-entries/delete", json=body,
        )

    async def update(
        self,
        entry_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> FileEntry:
        body: dict[str, object] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        data = await self._transport.request_json(
            "PUT", f"/file-entries/{entry_id}", json=body,
        )
        return _entry_from_envelope(data)

    async def move(
        self,
        entry_ids: Sequence[int],
        *,
        destination_id: int | None = None,
        target_workspace_id: int | None = None,
    ) -> list[FileEntry]:
        _require_non_empty(entry_ids, "entry_ids")
        body: dict[str, object] = {"entryIds": list(entry_ids)}
        if destination_id is not None:
            body["destinationId"] = destination_id
        if target_workspace_id is not None:
            body["targetWorkspaceId"] = target_workspace_id
        data = await self._transport.request_json(
            "POST", "/file-entries/move", json=body,
        )
        return _entries_from_envelope(data)

    async def duplicate(
        self,
        entry_ids: Sequence[int],
        *,
        destination_id: int | None = None,
    ) -> list[FileEntry]:
        _require_non_empty(entry_ids, "entry_ids")
        body: dict[str, object] = {"entryIds": list(entry_ids)}
        if destination_id is not None:
            body["destinationId"] = destination_id
        data = await self._transport.request_json(
            "POST", "/file-entries/duplicate", json=body,
        )
        return _entries_from_envelope(data)

    async def restore(self, entry_ids: Sequence[int]) -> None:
        _require_non_empty(entry_ids, "entry_ids")
        body = {"entryIds": list(entry_ids)}
        await self._transport.request_json(
            "POST", "/file-entries/restore", json=body,
        )

    @asynccontextmanager
    async def download_stream(
        self,
        entry_id: int,
        *,
        thumbnail: bool | None = None,
        preview_token: str | None = None,
        access_token: str | None = None,
    ) -> AsyncIterator[StreamingResponse]:
        params: dict[str, object] = {}
        if thumbnail is not None:
            params["thumbnail"] = thumbnail
        if preview_token is not None:
            params["preview_token"] = preview_token
        if access_token is not None:
            params["accessToken"] = access_token
        async with self._transport.stream_download(
            f"/file-entries/{entry_id}",
            params=params,
        ) as response:
            yield response

    async def download_to_file(
        self,
        entry_id: int,
        destination: str | os.PathLike[str],
        *,
        chunk_size: int = 1024 * 1024,
        thumbnail: bool | None = None,
        preview_token: str | None = None,
        access_token: str | None = None,
    ) -> int:
        """Stream the file to disk; returns the total number of bytes written."""

        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        path = os.fspath(destination)
        total = 0
        with open(path, "wb") as fh:
            async with self.download_stream(
                entry_id,
                thumbnail=thumbnail,
                preview_token=preview_token,
                access_token=access_token,
            ) as response:
                async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                    fh.write(chunk)
                    total += len(chunk)
        return total

    def direct_download_url(
        self,
        entry_id: int,
        *,
        access_token: str | None = None,
        preview_token: str | None = None,
        thumbnail: bool | None = None,
    ) -> str:
        """Build a direct GET URL for a file entry.

        Useful when you want to hand a single URL to a browser, ``curl``, ``wget``,
        a download manager, or an ``<a href="...">`` tag without sharing your
        ``Authorization`` header.

        ``access_token`` defaults to the client's currently configured token
        (so the URL works as a stand-alone link). Pass ``access_token=""`` to
        omit it explicitly (useful when the link will be consumed by an already
        authenticated session via cookies, or when ``preview_token`` is enough).
        """

        params: dict[str, str] = {}
        if thumbnail is True:
            params["thumbnail"] = "1"
        elif thumbnail is False:
            params["thumbnail"] = "0"
        if preview_token:
            params["preview_token"] = preview_token

        if access_token is None:
            token_to_use = self._transport.access_token
        else:
            token_to_use = access_token or None
        if token_to_use:
            params["accessToken"] = token_to_use

        base = f"{self._transport.base_url}/file-entries/{entry_id}"
        if not params:
            return base
        # Encode without "+" for spaces so tokens with reserved chars round-trip cleanly.
        query = urlencode(params, quote_via=quote)
        return f"{base}?{query}"
