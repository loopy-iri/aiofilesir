"""Pydantic v2 response/request models matching the swagger wire format."""
from __future__ import annotations

from typing import Any, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

FileEntryType = Literal["folder", "image", "text", "audio", "video", "pdf"]
UploadMode = Literal["single", "s3-single", "s3-multipart", "tus"]
Permission = Literal["view", "edit", "download"]


class _Base(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        protected_namespaces=(),
    )


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


class SpaceUsage(_Base):
    used: int = 0
    available: int | None = None
    remaining: int | None = None


# ---------------------------------------------------------------------------
# File entries
# ---------------------------------------------------------------------------


class FileEntryUserStub(_Base):
    id: int
    email: str | None = None


class FileEntry(_Base):
    id: int
    name: str
    file_name: str | None = None
    file_size: int | None = None
    parent_id: int | None = None
    workspace_id: int | None = None
    parent: Optional["FileEntry"] = None
    thumbnail: str | None = None
    mime: str | None = None
    url: str | None = None
    hash: str | None = None
    type: FileEntryType | None = None
    description: str | None = None
    deleted_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    path: str | None = None
    users: list[FileEntryUserStub] | None = None


FileEntry.model_rebuild()


# ---------------------------------------------------------------------------
# Auth / users
# ---------------------------------------------------------------------------


class User(_Base):
    id: int
    access_token: str | None = None
    display_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------


class WorkspacePermission(_Base):
    id: int
    name: str
    restrictions: dict[str, Any] | None = None


class WorkspaceMember(_Base):
    id: int
    email: str
    workspace_id: int | None = None
    joined_at: str | None = None
    role_id: int | None = None
    is_owner: bool = False
    member_id: int
    first_name: str | None = None
    last_name: str | None = None
    image: str | None = None
    role_name: str | None = None
    name: str
    model_type: str
    can_view_activity_logs: bool | None = None
    permissions: list[WorkspacePermission] | None = None


class WorkspaceInvite(_Base):
    id: str
    workspace_id: int | None = None
    role_name: str | None = None
    email: str | None = None
    role_id: int | None = None
    image: str | None = None


class Workspace(_Base):
    id: int
    name: str
    owner_id: int
    use_owner_storage: bool | None = None
    storage_limit: int | None = None
    storage_used: int | None = None
    owner_max_upload_size: int | None = None
    owner_plan_name: str | None = None
    members_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None
    owner: WorkspaceMember | None = None
    current_user: WorkspaceMember | None = None
    members: list[WorkspaceMember] | None = None
    invites: list[WorkspaceInvite] | None = None


class WorkspaceActivityLog(_Base):
    id: int
    workspace_id: int | None = None
    user_id: int | None = None
    action: str
    subject_type: str | None = None
    subject_id: int | None = None
    subject_name: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None
    user: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


class Tag(_Base):
    id: int
    name: str


# ---------------------------------------------------------------------------
# Shareable links
# ---------------------------------------------------------------------------


class ShareableLink(_Base):
    id: int
    hash: str | None = None
    password: str | None = None
    user_id: int | None = None
    entry_id: int | None = None
    entry: FileEntry | None = None
    expires_at: str | None = None
    allow_edit: bool | None = None
    allow_download: bool | None = None


class ShareableLinkResponse(_Base):
    status: str | None = None
    link: ShareableLink | None = None
    folderChildren: list[FileEntry] | None = Field(default=None, alias="folderChildren")
    errors: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# Upload session schemas
# ---------------------------------------------------------------------------


class NewUploadInitRequest(_Base):
    filename: str
    size: int
    parentId: int | None = Field(default=None, alias="parentId")
    workspaceId: int | None = Field(default=None, alias="workspaceId")


class NewUploadNext(_Base):
    method: str | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    completeUrl: str | None = Field(default=None, alias="completeUrl")
    metadata: dict[str, str] | None = None


class NewUploadInitResponse(_Base):
    status: str | None = None
    uploadSessionId: str = Field(alias="uploadSessionId")
    uploadMode: UploadMode = Field(alias="uploadMode")
    partSize: int | None = Field(default=None, alias="partSize")
    next: NewUploadNext | None = None


class NewUploadSignedPart(_Base):
    partNumber: int = Field(alias="partNumber")
    url: str


class NewUploadSignPartsResponse(_Base):
    status: str | None = None
    urls: list[NewUploadSignedPart] = Field(default_factory=list)


class NewUploadCompletedPart(_Base):
    """Wire format requires PartNumber/ETag with PascalCase keys."""

    PartNumber: int = Field(alias="PartNumber")
    ETag: str = Field(alias="ETag")


class NewUploadCompleteRequest(_Base):
    parts: list[NewUploadCompletedPart] | None = None
    uploadKey: str | None = Field(default=None, alias="uploadKey")


class NewUploadFileEntryResponse(_Base):
    status: str | None = None
    fileEntry: FileEntry = Field(alias="fileEntry")


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


T = TypeVar("T")


class Page(_Base, Generic[T]):
    """Generic paginated container.

    Mirrors the ``pagination`` envelope used by Files.ir's paginated endpoints.
    Files.ir returns a Laravel-style page object with ``data``, ``current_page``,
    ``per_page``, ``last_page`` and ``total`` (any subset of these may be present).
    """

    data: list[T] = Field(default_factory=list)
    total: int | None = None
    current_page: int | None = None
    per_page: int | None = None
    last_page: int | None = None
