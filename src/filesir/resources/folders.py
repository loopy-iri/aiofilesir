"""``/folders`` endpoint."""
from __future__ import annotations

from ..models import FileEntry
from .base import BaseResource


class FoldersResource(BaseResource):
    async def create(
        self,
        *,
        name: str,
        parent_id: int | None = None,
    ) -> FileEntry:
        body: dict[str, object] = {"name": name}
        if parent_id is not None:
            body["parentId"] = parent_id
        data = await self._transport.request_json("POST", "/folders", json=body)
        if isinstance(data, dict) and "folder" in data:
            return FileEntry.model_validate(data["folder"])
        return FileEntry.model_validate(data)
