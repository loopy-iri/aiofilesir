"""``/user/space-usage`` endpoint."""
from __future__ import annotations

from ..models import SpaceUsage
from .base import BaseResource


class StorageResource(BaseResource):
    async def space_usage(self) -> SpaceUsage:
        data = await self._transport.request_json("GET", "/user/space-usage")
        return SpaceUsage.model_validate(data)
