"""Low-level wrapper for ``/uploads-new/*`` endpoints."""
from __future__ import annotations

from typing import Sequence

from ..exceptions import UploadError
from ..models import (
    FileEntry,
    NewUploadCompletedPart,
    NewUploadInitResponse,
    NewUploadSignedPart,
)
from ..transport import Transport
from .sources import FileSource


class NewUploadSessionClient:
    """Thin async wrapper for the session-based upload endpoints."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def init(
        self,
        *,
        filename: str,
        size: int,
        parent_id: int | None = None,
        workspace_id: int | None = None,
    ) -> NewUploadInitResponse:
        if not filename:
            raise UploadError("filename must be non-empty")
        if size < 0:
            raise UploadError("size must be >= 0")
        body: dict[str, object] = {"filename": filename, "size": size}
        if parent_id is not None:
            body["parentId"] = parent_id
        if workspace_id is not None:
            body["workspaceId"] = workspace_id
        data = await self._transport.request_json(
            "POST", "/uploads-new/init", json=body,
        )
        return NewUploadInitResponse.model_validate(data)

    async def upload_single(
        self,
        session_id: str,
        source: FileSource,
    ) -> FileEntry:
        # Read the entire source into memory: by design the "single" mode is
        # only used by the server when the file is small (< 4 MB).
        chunks: list[bytes] = []
        async for chunk in source.read_stream():
            chunks.append(chunk)
        body = b"".join(chunks)
        files = {
            "file": (
                source.filename(),
                body,
                source.content_type() or "application/octet-stream",
            ),
        }
        data = await self._transport.request_json(
            "POST",
            f"/uploads-new/{session_id}/file",
            files=files,
        )
        return _file_entry_from_envelope(data)

    async def sign_parts(
        self,
        session_id: str,
        part_numbers: Sequence[int],
    ) -> list[NewUploadSignedPart]:
        if not part_numbers:
            raise UploadError("part_numbers must be a non-empty sequence")
        seen: set[int] = set()
        for n in part_numbers:
            if n < 1 or n > 10000:
                raise UploadError(f"part number out of range [1, 10000]: {n}")
            if n in seen:
                raise UploadError(f"duplicate part number: {n}")
            seen.add(n)
        body = {"partNumbers": list(part_numbers)}
        data = await self._transport.request_json(
            "POST",
            f"/uploads-new/{session_id}/parts/sign",
            json=body,
        )
        if isinstance(data, dict):
            urls = data.get("urls", [])
        else:
            urls = data
        if not isinstance(urls, list):
            return []
        return [NewUploadSignedPart.model_validate(x) for x in urls]

    async def complete(
        self,
        session_id: str,
        *,
        parts: Sequence[NewUploadCompletedPart] | None = None,
        upload_key: str | None = None,
        complete_url: str | None = None,
    ) -> FileEntry:
        body: dict[str, object] = {}
        if parts is not None:
            body["parts"] = [p.model_dump(by_alias=True) for p in parts]
        if upload_key is not None:
            body["uploadKey"] = upload_key
        # When the server's init response provides next.completeUrl we prefer it
        # (used for s3-single / tus). Otherwise we fall back to the session path.
        if complete_url is not None:
            data = await self._transport.request_json(
                "POST", complete_url, json=body or None,
            )
        else:
            data = await self._transport.request_json(
                "POST",
                f"/uploads-new/{session_id}/complete",
                json=body or None,
            )
        return _file_entry_from_envelope(data)

    async def abort(self, session_id: str) -> None:
        try:
            await self._transport.request_json(
                "DELETE", f"/uploads-new/{session_id}",
            )
        except Exception:  # pragma: no cover - best-effort
            pass


def _file_entry_from_envelope(data: object) -> FileEntry:
    if isinstance(data, dict) and "fileEntry" in data:
        return FileEntry.model_validate(data["fileEntry"])
    return FileEntry.model_validate(data)


__all__ = ["NewUploadSessionClient"]
