"""``/file-entries/{id}/share|change-permissions|unshare`` endpoints."""
from __future__ import annotations

from typing import Sequence

from ..exceptions import ValidationError
from ..models import Permission, User
from .base import BaseResource

_VALID_PERMS: frozenset[str] = frozenset({"view", "edit", "download"})


def _validate_permissions(permissions: Sequence[str]) -> list[str]:
    if len(permissions) == 0:
        raise ValidationError("permissions must be a non-empty sequence")
    perms = [str(p) for p in permissions]
    invalid = [p for p in perms if p not in _VALID_PERMS]
    if invalid:
        raise ValidationError(
            f"invalid permissions: {invalid!r}; allowed: {sorted(_VALID_PERMS)!r}",
        )
    return perms


def _users_from_envelope(data: object) -> list[User]:
    if isinstance(data, dict):
        items = data.get("users", [])
    else:
        items = data
    if not isinstance(items, list):
        return []
    return [User.model_validate(x) for x in items]


class SharingResource(BaseResource):
    async def share(
        self,
        entry_id: int,
        *,
        emails: Sequence[str],
        permissions: Sequence[Permission],
    ) -> list[User]:
        if len(emails) == 0:
            raise ValidationError("emails must be a non-empty sequence")
        body = {
            "emails": list(emails),
            "permissions": _validate_permissions(permissions),
        }
        data = await self._transport.request_json(
            "POST", f"/file-entries/{entry_id}/share", json=body,
        )
        return _users_from_envelope(data)

    async def change_permissions(
        self,
        entry_id: int,
        *,
        user_id: int,
        permissions: Sequence[Permission],
    ) -> list[User]:
        body = {
            "userId": user_id,
            "permissions": _validate_permissions(permissions),
        }
        data = await self._transport.request_json(
            "PUT", f"/file-entries/{entry_id}/change-permissions", json=body,
        )
        return _users_from_envelope(data)

    async def unshare(self, entry_id: int, *, user_id: int) -> list[User]:
        body = {"userId": user_id}
        data = await self._transport.request_json(
            "DELETE", f"/file-entries/{entry_id}/unshare", json=body,
        )
        return _users_from_envelope(data)
