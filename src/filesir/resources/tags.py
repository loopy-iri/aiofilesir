"""``/taggable/*`` endpoints."""
from __future__ import annotations

from typing import Sequence

from ..exceptions import ValidationError
from ..models import Tag
from .base import BaseResource


def _tag_from_envelope(data: object) -> Tag:
    if isinstance(data, dict) and "tag" in data:
        return Tag.model_validate(data["tag"])
    return Tag.model_validate(data)


def _tags_from_envelope(data: object) -> list[Tag]:
    if isinstance(data, dict):
        items = data.get("tags", [])
    else:
        items = data
    if not isinstance(items, list):
        return []
    return [Tag.model_validate(x) for x in items]


class TagsResource(BaseResource):
    async def list_for(
        self,
        taggable_type: str,
        taggable_id: int,
        *,
        type: str | None = None,
        not_type: str | None = None,
    ) -> list[Tag]:
        params: dict[str, object] = {}
        if type is not None:
            params["type"] = type
        if not_type is not None:
            params["notType"] = not_type
        data = await self._transport.request_json(
            "GET",
            f"/taggable/{taggable_type}/{taggable_id}/list-tags",
            params=params,
        )
        return _tags_from_envelope(data)

    async def attach(
        self,
        *,
        tag_name: str,
        taggable_type: str,
        taggable_ids: Sequence[int],
        tag_type: str | None = None,
        user_id: int | None = None,
    ) -> Tag:
        if len(taggable_ids) == 0:
            raise ValidationError("taggable_ids must be a non-empty sequence")
        body: dict[str, object] = {
            "tagName": tag_name,
            "taggableType": taggable_type,
            "taggableIds": list(taggable_ids),
        }
        if tag_type is not None:
            body["tagType"] = tag_type
        if user_id is not None:
            body["userId"] = user_id
        data = await self._transport.request_json(
            "POST", "/taggable/attach-tag", json=body,
        )
        return _tag_from_envelope(data)

    async def detach(
        self,
        *,
        tag_id: int,
        taggable_type: str,
        taggable_ids: Sequence[int],
    ) -> None:
        if len(taggable_ids) == 0:
            raise ValidationError("taggable_ids must be a non-empty sequence")
        body: dict[str, object] = {
            "tagId": tag_id,
            "taggableType": taggable_type,
            "taggableIds": list(taggable_ids),
        }
        await self._transport.request_json(
            "POST", "/taggable/detach-tag", json=body,
        )

    async def sync(
        self,
        *,
        taggable_type: str,
        taggable_ids: Sequence[int],
        tag_ids: Sequence[int],
        user_id: int | None = None,
        detach: bool | None = None,
    ) -> None:
        if len(taggable_ids) == 0:
            raise ValidationError("taggable_ids must be a non-empty sequence")
        body: dict[str, object] = {
            "taggableType": taggable_type,
            "taggableIds": list(taggable_ids),
            "tagIds": list(tag_ids),
        }
        if user_id is not None:
            body["userId"] = user_id
        if detach is not None:
            body["detach"] = detach
        await self._transport.request_json(
            "POST", "/taggable/sync-tags", json=body,
        )
