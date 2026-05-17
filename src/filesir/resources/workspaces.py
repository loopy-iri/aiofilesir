"""``/me/workspaces``, ``/workspace/*``, ``/workspaces/{id}/activity-logs`` endpoints."""
from __future__ import annotations

from typing import AsyncIterator, Sequence

from ..exceptions import ValidationError
from ..models import Page, Workspace, WorkspaceActivityLog, WorkspaceInvite
from ..pagination import paginate
from .base import BaseResource


def _workspaces_from_envelope(data: object) -> list[Workspace]:
    if isinstance(data, dict):
        items = data.get("workspaces", data.get("data", []))
    else:
        items = data
    if not isinstance(items, list):
        return []
    return [Workspace.model_validate(x) for x in items]


def _workspace_from_envelope(data: object) -> Workspace:
    if isinstance(data, dict) and "workspace" in data:
        return Workspace.model_validate(data["workspace"])
    return Workspace.model_validate(data)


def _page_from_envelope(data: object, model: type) -> Page:
    if isinstance(data, dict):
        pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else data
    else:
        pagination = {}
    if not isinstance(pagination, dict):
        pagination = {}
    raw_items = pagination.get("data", []) if isinstance(pagination, dict) else []
    items = [model.model_validate(x) for x in raw_items] if isinstance(raw_items, list) else []
    return Page(
        data=items,
        total=pagination.get("total") if isinstance(pagination, dict) else None,
        current_page=pagination.get("current_page") if isinstance(pagination, dict) else None,
        per_page=pagination.get("per_page") if isinstance(pagination, dict) else None,
        last_page=pagination.get("last_page") if isinstance(pagination, dict) else None,
    )


def _invites_from_envelope(data: object) -> list[WorkspaceInvite]:
    if isinstance(data, dict):
        items = data.get("invites", [])
    else:
        items = data
    if not isinstance(items, list):
        return []
    return [WorkspaceInvite.model_validate(x) for x in items]


def _invite_from_envelope(data: object) -> WorkspaceInvite:
    if isinstance(data, dict) and "invite" in data:
        return WorkspaceInvite.model_validate(data["invite"])
    return WorkspaceInvite.model_validate(data)


class WorkspacesResource(BaseResource):
    async def list_mine(self) -> list[Workspace]:
        data = await self._transport.request_json("GET", "/me/workspaces")
        return _workspaces_from_envelope(data)

    async def list(
        self,
        *,
        page: int = 1,
        per_page: int = 15,
        user_id: int | None = None,
    ) -> Page[Workspace]:
        params: dict[str, object] = {"page": page, "perPage": per_page}
        if user_id is not None:
            params["userId"] = user_id
        data = await self._transport.request_json("GET", "/workspace", params=params)
        return _page_from_envelope(data, Workspace)

    def iter_all(
        self,
        *,
        per_page: int = 15,
        user_id: int | None = None,
    ) -> AsyncIterator[Workspace]:
        async def fetch(page: int, page_size: int) -> Page[Workspace]:
            return await self.list(page=page, per_page=page_size, user_id=user_id)

        return paginate(fetch, per_page=per_page)

    async def create(
        self,
        *,
        name: str,
        use_owner_storage: bool | None = None,
        storage_limit: int | None = None,
    ) -> Workspace:
        body: dict[str, object] = {"name": name}
        if use_owner_storage is not None:
            body["use_owner_storage"] = use_owner_storage
        if storage_limit is not None:
            body["storage_limit"] = storage_limit
        data = await self._transport.request_json("POST", "/workspace", json=body)
        return _workspace_from_envelope(data)

    async def get(self, workspace_id: int) -> Workspace:
        data = await self._transport.request_json("GET", f"/workspace/{workspace_id}")
        return _workspace_from_envelope(data)

    async def update(
        self,
        workspace_id: int,
        *,
        name: str,
        use_owner_storage: bool | None = None,
        storage_limit: int | None = None,
    ) -> Workspace:
        body: dict[str, object] = {"name": name}
        if use_owner_storage is not None:
            body["use_owner_storage"] = use_owner_storage
        if storage_limit is not None:
            body["storage_limit"] = storage_limit
        data = await self._transport.request_json(
            "PUT", f"/workspace/{workspace_id}", json=body,
        )
        return _workspace_from_envelope(data)

    async def delete(self, workspace_ids: int | Sequence[int]) -> None:
        if isinstance(workspace_ids, int):
            id_path: str = str(workspace_ids)
        else:
            ids = list(workspace_ids)
            if not ids:
                raise ValidationError("workspace_ids must be a non-empty sequence")
            id_path = ",".join(str(i) for i in ids)
        await self._transport.request_json("DELETE", f"/workspace/{id_path}")

    async def invite(
        self,
        workspace_id: int,
        *,
        emails: Sequence[str],
        role_id: int,
    ) -> list[WorkspaceInvite]:
        if len(emails) == 0:
            raise ValidationError("emails must be a non-empty sequence")
        body = {"emails": list(emails), "roleId": role_id}
        data = await self._transport.request_json(
            "POST", f"/workspace/{workspace_id}/invite", json=body,
        )
        return _invites_from_envelope(data)

    async def resend_invite(
        self,
        workspace_id: int,
        invite_id: str,
    ) -> WorkspaceInvite:
        data = await self._transport.request_json(
            "POST", f"/workspace/{workspace_id}/{invite_id}/resend",
        )
        return _invite_from_envelope(data)

    async def change_member_role(
        self,
        workspace_id: int,
        member_id: int,
        *,
        role_id: int,
    ) -> None:
        await self._transport.request_json(
            "POST",
            f"/workspace/{workspace_id}/member/{member_id}/change-role",
            json={"roleId": role_id},
        )

    async def change_invite_role(
        self,
        workspace_id: int,
        invite_id: str,
        *,
        role_id: int,
    ) -> None:
        await self._transport.request_json(
            "POST",
            f"/workspace/{workspace_id}/invite/{invite_id}/change-role",
            json={"roleId": role_id},
        )

    async def remove_member(self, workspace_id: int, user_id: int) -> None:
        await self._transport.request_json(
            "DELETE", f"/workspace/{workspace_id}/member/{user_id}",
        )

    async def delete_invite(self, invite_id: str) -> None:
        await self._transport.request_json(
            "DELETE", f"/workspace/invite/{invite_id}",
        )

    async def join(self, invite_id: str) -> Workspace:
        data = await self._transport.request_json(
            "GET", f"/workspace/join/{invite_id}",
        )
        return _workspace_from_envelope(data)

    async def list_activity_logs(
        self,
        workspace_id: int,
        *,
        page: int = 1,
        per_page: int = 15,
    ) -> Page[WorkspaceActivityLog]:
        params: dict[str, object] = {"page": page, "perPage": per_page}
        data = await self._transport.request_json(
            "GET", f"/workspaces/{workspace_id}/activity-logs", params=params,
        )
        return _page_from_envelope(data, WorkspaceActivityLog)

    def iter_activity_logs(
        self,
        workspace_id: int,
        *,
        per_page: int = 15,
    ) -> AsyncIterator[WorkspaceActivityLog]:
        async def fetch(page: int, page_size: int) -> Page[WorkspaceActivityLog]:
            return await self.list_activity_logs(workspace_id, page=page, per_page=page_size)

        return paginate(fetch, per_page=per_page)
