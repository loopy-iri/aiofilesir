"""``uploadMode == "s3-multipart"`` strategy."""
from __future__ import annotations

import asyncio
import math

from ...exceptions import UploadError
from ...models import FileEntry, NewUploadCompletedPart, NewUploadInitResponse
from ..sources import FileSource
from .base import ProgressCallback, UploadStrategy


class S3MultipartUploadStrategy(UploadStrategy):
    """Splits the source into ``ceil(size / partSize)`` chunks and uploads them
    concurrently via signed S3 PUT URLs, then issues ``/complete`` with the
    collected ETags.
    """

    async def upload(
        self,
        *,
        source: FileSource,
        init: NewUploadInitResponse,
        progress: ProgressCallback | None,
    ) -> FileEntry:
        if init.partSize is None or init.partSize <= 0:
            raise UploadError(
                "server returned uploadMode=s3-multipart without a positive partSize",
            )
        if not init.uploadSessionId:
            raise UploadError("init response is missing uploadSessionId")

        size = source.size()
        part_size = init.partSize
        # Treat zero-byte files as a single empty part so the API contract holds.
        n = math.ceil(size / part_size) if size > 0 else 1
        if n < 1 or n > 10000:
            raise UploadError(f"invalid part count: {n}")

        sid = init.uploadSessionId
        signed = await self._sessions.sign_parts(sid, list(range(1, n + 1)))
        if len(signed) != n:
            raise UploadError(
                f"sign_parts returned {len(signed)} URLs but {n} were requested",
            )
        url_by_part: dict[int, str] = {p.partNumber: p.url for p in signed}
        if any(i not in url_by_part for i in range(1, n + 1)):
            raise UploadError("sign_parts response is missing one or more part numbers")

        etags: list[str | None] = [None] * n
        sem = asyncio.Semaphore(self._concurrency)
        progress_lock = asyncio.Lock()
        uploaded = 0

        async def upload_part(i: int) -> None:
            nonlocal uploaded
            offset = (i - 1) * part_size
            length = min(part_size, max(0, size - offset))
            chunk = await source.read_chunk(offset, length)
            url = url_by_part[i]
            async with sem:
                response = await self._transport.external_put(
                    url,
                    content=chunk,
                    content_length=length,
                )
                etag = response.headers.get("ETag") or response.headers.get("etag")
                if not etag:
                    raise UploadError(f"S3 part {i} returned no ETag header")
                etags[i - 1] = etag
                if progress is not None:
                    async with progress_lock:
                        uploaded += length
                        try:
                            progress(uploaded, size)
                        except Exception:  # pragma: no cover
                            pass

        try:
            await asyncio.gather(*(upload_part(i) for i in range(1, n + 1)))
        except Exception as exc:
            await self._sessions.abort(sid)
            if isinstance(exc, UploadError):
                raise
            raise UploadError(f"multipart part upload failed: {exc}") from exc

        parts = [
            NewUploadCompletedPart(PartNumber=i, ETag=etags[i - 1] or "")
            for i in range(1, n + 1)
        ]
        return await self._sessions.complete(sid, parts=parts)
