"""Public ``UploadsResource`` façade.

Exposes:

* :meth:`upload_legacy` for the simple ``POST /uploads`` multipart endpoint.
* :meth:`upload_file` — the high-level helper that calls ``/uploads-new/init``
  and dispatches to the correct strategy based on the server-reported
  ``uploadMode``.
* :attr:`sessions` — direct access to the low-level ``/uploads-new/*`` methods.
"""
from __future__ import annotations

import os
from typing import Union

from ..exceptions import FilesIrError, UploadError
from ..models import FileEntry, NewUploadInitResponse
from ..resources.base import BaseResource
from ..transport import Transport
from .sessions import NewUploadSessionClient
from .sources import FileSource, make_source
from .strategies import ProgressCallback, UploadStrategy, select_strategy

UploadInput = Union[FileSource, str, "os.PathLike[str]", bytes, bytearray, memoryview]


class UploadsResource(BaseResource):
    sessions: NewUploadSessionClient

    def __init__(self, transport: Transport, *, concurrency: int = 4) -> None:
        super().__init__(transport)
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        self._concurrency = concurrency
        self.sessions = NewUploadSessionClient(transport)

    async def upload_legacy(
        self,
        source: UploadInput,
        *,
        parent_id: int | None = None,
        workspace_id: int | None = None,
        relative_path: str | None = None,
        filename: str | None = None,
    ) -> FileEntry:
        fs = make_source(source, filename=filename)
        body = bytearray()
        async for chunk in fs.read_stream():
            body.extend(chunk)
        files = {
            "file": (
                fs.filename(),
                bytes(body),
                fs.content_type() or "application/octet-stream",
            ),
        }
        data: dict[str, object] = {}
        if parent_id is not None:
            data["parentId"] = parent_id
        if workspace_id is not None:
            data["workspaceId"] = workspace_id
        if relative_path is not None:
            data["relativePath"] = relative_path
        result = await self._transport.request_json(
            "POST", "/uploads", data=data or None, files=files,
        )
        return _file_entry_from_envelope(result)

    async def upload_file(
        self,
        source: UploadInput,
        *,
        parent_id: int | None = None,
        workspace_id: int | None = None,
        filename: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> FileEntry:
        """Init the session, dispatch on ``uploadMode``, and return the new entry."""

        fs = make_source(source, filename=filename)
        if fs.size() < 0:
            raise UploadError("source size must be >= 0")
        if not fs.filename():
            raise UploadError("source filename must be non-empty")

        init: NewUploadInitResponse = await self.sessions.init(
            filename=fs.filename(),
            size=fs.size(),
            parent_id=parent_id,
            workspace_id=workspace_id,
        )
        strategy: UploadStrategy = select_strategy(
            init,
            sessions=self.sessions,
            transport=self._transport,
            concurrency=self._concurrency,
        )
        try:
            return await strategy.upload(source=fs, init=init, progress=progress)
        except (FilesIrError, UploadError):
            await self.sessions.abort(init.uploadSessionId)
            raise


def _file_entry_from_envelope(data: object) -> FileEntry:
    if isinstance(data, dict) and "fileEntry" in data:
        return FileEntry.model_validate(data["fileEntry"])
    return FileEntry.model_validate(data)


__all__ = ["UploadsResource", "UploadInput"]
