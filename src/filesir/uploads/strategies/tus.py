"""``uploadMode == "tus"`` strategy.

Implements a small TUS 1.0.0 client (creation + PATCH protocol) so we don't pull
in a heavyweight external dependency. Compatible with the standard TUS server
implementation used by Files.ir / Spatie tus-server.
"""
from __future__ import annotations

import base64
import os
from urllib.parse import urlsplit

from ...exceptions import UploadError
from ...models import FileEntry, NewUploadInitResponse
from ..sources import FileSource
from .base import ProgressCallback, UploadStrategy

_TUS_VERSION = "1.0.0"
_DEFAULT_CHUNK = 5 * 1024 * 1024


def _encode_metadata(metadata: dict[str, str] | None) -> str:
    if not metadata:
        return ""
    parts: list[str] = []
    for key, value in metadata.items():
        encoded = base64.b64encode(str(value).encode("utf-8")).decode("ascii")
        parts.append(f"{key} {encoded}")
    return ",".join(parts)


class TusUploadStrategy(UploadStrategy):
    async def upload(
        self,
        *,
        source: FileSource,
        init: NewUploadInitResponse,
        progress: ProgressCallback | None,
    ) -> FileEntry:
        if init.next is None or not init.next.url:
            raise UploadError("tus mode requires next.url in init response")

        size = source.size()
        creation_url = init.next.url
        metadata = init.next.metadata or {}
        extra_headers = dict(init.next.headers or {})

        upload_url = await self._create_tus_upload(
            creation_url,
            size=size,
            metadata=metadata,
            extra_headers=extra_headers,
        )
        await self._transfer_chunks(
            upload_url,
            source=source,
            size=size,
            progress=progress,
            extra_headers=extra_headers,
        )
        upload_key = self._extract_upload_key(upload_url)
        return await self._sessions.complete(
            init.uploadSessionId,
            upload_key=upload_key,
            complete_url=init.next.completeUrl,
        )

    async def _create_tus_upload(
        self,
        creation_url: str,
        *,
        size: int,
        metadata: dict[str, str],
        extra_headers: dict[str, str],
    ) -> str:
        headers = {
            "Tus-Resumable": _TUS_VERSION,
            "Upload-Length": str(size),
        }
        encoded_meta = _encode_metadata(metadata)
        if encoded_meta:
            headers["Upload-Metadata"] = encoded_meta
        for k, v in extra_headers.items():
            if k.lower() in {"content-type", "tus-resumable"}:
                continue
            headers.setdefault(k, v)

        client = self._transport._client  # type: ignore[attr-defined]
        response = await client.request("POST", creation_url, headers=headers)
        if response.status_code not in (200, 201):
            raise UploadError(
                f"TUS creation failed: HTTP {response.status_code} {response.text!r}",
            )
        location = response.headers.get("Location")
        if not location:
            raise UploadError("TUS creation succeeded but no Location header was returned")
        # The TUS spec allows relative URLs; resolve against the creation URL.
        if location.startswith("http://") or location.startswith("https://"):
            return location
        split = urlsplit(creation_url)
        if location.startswith("/"):
            return f"{split.scheme}://{split.netloc}{location}"
        base = creation_url.rsplit("/", 1)[0]
        return f"{base}/{location}"

    async def _transfer_chunks(
        self,
        upload_url: str,
        *,
        source: FileSource,
        size: int,
        progress: ProgressCallback | None,
        extra_headers: dict[str, str],
    ) -> None:
        offset = 0
        client = self._transport._client  # type: ignore[attr-defined]
        while offset < size:
            length = min(_DEFAULT_CHUNK, size - offset)
            chunk = await source.read_chunk(offset, length)
            headers = {
                "Tus-Resumable": _TUS_VERSION,
                "Upload-Offset": str(offset),
                "Content-Type": "application/offset+octet-stream",
                "Content-Length": str(length),
            }
            for k, v in extra_headers.items():
                if k.lower() in {"content-type", "tus-resumable", "upload-offset", "content-length"}:
                    continue
                headers.setdefault(k, v)
            response = await client.request(
                "PATCH",
                upload_url,
                content=chunk,
                headers=headers,
            )
            if response.status_code != 204:
                raise UploadError(
                    f"TUS PATCH failed: HTTP {response.status_code} {response.text!r}",
                )
            new_offset = response.headers.get("Upload-Offset")
            try:
                offset = int(new_offset) if new_offset is not None else offset + length
            except ValueError:
                offset = offset + length
            if progress is not None:
                try:
                    progress(min(offset, size), size)
                except Exception:  # pragma: no cover
                    pass
        if size == 0:
            # Some TUS servers require a zero-length PATCH to finalize empty uploads.
            headers = {
                "Tus-Resumable": _TUS_VERSION,
                "Upload-Offset": "0",
                "Content-Type": "application/offset+octet-stream",
                "Content-Length": "0",
            }
            await client.request("PATCH", upload_url, content=b"", headers=headers)

    @staticmethod
    def _extract_upload_key(upload_url: str) -> str:
        # The upload "key" is the last path segment of the TUS upload URL.
        path = urlsplit(upload_url).path.rstrip("/")
        return os.path.basename(path)
