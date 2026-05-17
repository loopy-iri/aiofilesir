"""``/file-entries/star|unstar`` endpoints."""
from __future__ import annotations

from typing import Sequence

from ..exceptions import ValidationError
from ..models import Tag
from .base import BaseResource


def _tag_from_envelope(data: object) -> Tag:
    if isinstance(data, dict) and "tag" in data:
        return Tag.model_validate(data["tag"])
    return Tag.model_validate(data)


class StarringResource(BaseResource):
    async def star(self, entry_ids: Sequence[int]) -> Tag:
        if len(entry_ids) == 0:
            raise ValidationError("entry_ids must be a non-empty sequence")
        body = {"entryIds": list(entry_ids)}
        data = await self._transport.request_json(
            "POST", "/file-entries/star", json=body,
        )
        return _tag_from_envelope(data)

    async def unstar(self, entry_ids: Sequence[int]) -> Tag:
        if len(entry_ids) == 0:
            raise ValidationError("entry_ids must be a non-empty sequence")
        body = {"entryIds": list(entry_ids)}
        data = await self._transport.request_json(
            "POST", "/file-entries/unstar", json=body,
        )
        return _tag_from_envelope(data)
