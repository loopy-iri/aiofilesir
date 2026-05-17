"""Shareable Links endpoints.

Note the path quirk in the swagger:

* ``GET`` and ``POST`` use ``/file-entries/{id}/shareable-link`` (hyphen).
* ``PUT`` and ``DELETE`` use ``/file_entries/{id}/shareable-link`` (underscore).

The constants below encapsulate the quirk so it cannot leak elsewhere.
"""
from __future__ import annotations

from ..models import ShareableLink, ShareableLinkResponse
from .base import BaseResource

_GET_CREATE_PATH = "/file-entries/{entry_id}/shareable-link"
_UPDATE_DELETE_PATH = "/file_entries/{entry_id}/shareable-link"


def _link_from_envelope(data: object) -> ShareableLink:
    if isinstance(data, dict) and "link" in data and isinstance(data["link"], dict):
        return ShareableLink.model_validate(data["link"])
    return ShareableLink.model_validate(data)


class ShareableLinksResource(BaseResource):
    async def get(self, entry_id: int) -> ShareableLinkResponse:
        path = _GET_CREATE_PATH.format(entry_id=entry_id)
        data = await self._transport.request_json("GET", path)
        return ShareableLinkResponse.model_validate(data or {})

    async def create(
        self,
        entry_id: int,
        *,
        password: str | None = None,
        expires_at: str | None = None,
        allow_edit: bool | None = None,
        allow_download: bool | None = None,
    ) -> ShareableLink:
        body: dict[str, object] = {}
        if password is not None:
            body["password"] = password
        if expires_at is not None:
            body["expires_at"] = expires_at
        if allow_edit is not None:
            body["allow_edit"] = allow_edit
        if allow_download is not None:
            body["allow_download"] = allow_download
        path = _GET_CREATE_PATH.format(entry_id=entry_id)
        data = await self._transport.request_json("POST", path, json=body)
        return _link_from_envelope(data)

    async def update(
        self,
        entry_id: int,
        *,
        password: str | None = None,
        expires_at: str | None = None,
        allow_edit: bool | None = None,
        allow_download: bool | None = None,
    ) -> ShareableLink:
        body: dict[str, object] = {}
        if password is not None:
            body["password"] = password
        if expires_at is not None:
            body["expires_at"] = expires_at
        if allow_edit is not None:
            body["allow_edit"] = allow_edit
        if allow_download is not None:
            body["allow_download"] = allow_download
        path = _UPDATE_DELETE_PATH.format(entry_id=entry_id)
        data = await self._transport.request_json("PUT", path, json=body)
        return _link_from_envelope(data)

    async def delete(self, entry_id: int) -> None:
        path = _UPDATE_DELETE_PATH.format(entry_id=entry_id)
        await self._transport.request_json("DELETE", path)


__all__ = ["ShareableLinksResource"]
