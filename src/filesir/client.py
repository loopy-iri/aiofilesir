"""Public composition root: :class:`FilesIrClient`."""
from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx

from .resources import (
    AuthResource,
    FilesResource,
    FoldersResource,
    ShareableLinksResource,
    SharingResource,
    StarringResource,
    StorageResource,
    TagsResource,
    WorkspacesResource,
)
from .transport import DEFAULT_BASE_URL, RetryPolicy, Transport
from .uploads import UploadsResource


class FilesIrClient:
    """High-level async client for the Files.ir API.

    Construct from an existing access token::

        async with FilesIrClient(access_token="pat_...") as client:
            entries = await client.files.list()

    Or asynchronously from credentials::

        client = await FilesIrClient.from_credentials(
            email="me@example.com", password="secret", token_name="my-script",
        )
    """

    auth: AuthResource
    files: FilesResource
    folders: FoldersResource
    uploads: UploadsResource
    storage: StorageResource
    sharing: SharingResource
    starring: StarringResource
    links: ShareableLinksResource
    workspaces: WorkspacesResource
    tags: TagsResource

    def __init__(
        self,
        access_token: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = 30.0,
        retry: RetryPolicy | None = None,
        http_client: httpx.AsyncClient | None = None,
        upload_concurrency: int = 4,
    ) -> None:
        self._transport = Transport(
            base_url=base_url,
            timeout=timeout,
            retry=retry,
            http_client=http_client,
        )
        if access_token is not None:
            self._transport.set_access_token(access_token)

        self.auth = AuthResource(self._transport)
        self.storage = StorageResource(self._transport)
        self.files = FilesResource(self._transport)
        self.folders = FoldersResource(self._transport)
        self.uploads = UploadsResource(self._transport, concurrency=upload_concurrency)
        self.sharing = SharingResource(self._transport)
        self.starring = StarringResource(self._transport)
        self.links = ShareableLinksResource(self._transport)
        self.workspaces = WorkspacesResource(self._transport)
        self.tags = TagsResource(self._transport)

    @property
    def transport(self) -> Transport:
        return self._transport

    @property
    def access_token(self) -> str | None:
        return self._transport.access_token

    def set_access_token(self, token: str | None) -> None:
        self._transport.set_access_token(token)

    @classmethod
    async def from_credentials(
        cls,
        email: str,
        password: str,
        *,
        token_name: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        **kwargs: Any,
    ) -> "FilesIrClient":
        client = cls(base_url=base_url, **kwargs)
        try:
            user = await client.auth.login(
                email=email, password=password, token_name=token_name,
            )
        except Exception:
            await client.aclose()
            raise
        if not user.access_token:
            await client.aclose()
            raise RuntimeError(
                "login response did not include an access_token; cannot authenticate",
            )
        client.set_access_token(user.access_token)
        return client

    async def __aenter__(self) -> "FilesIrClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._transport.aclose()


__all__ = ["FilesIrClient"]
