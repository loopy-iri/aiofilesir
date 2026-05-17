"""``uploadMode == "s3-single"`` strategy."""
from __future__ import annotations

from ...exceptions import UploadError
from ...models import FileEntry, NewUploadInitResponse
from ..sources import FileSource
from .base import ProgressCallback, UploadStrategy


class S3SingleUploadStrategy(UploadStrategy):
    async def upload(
        self,
        *,
        source: FileSource,
        init: NewUploadInitResponse,
        progress: ProgressCallback | None,
    ) -> FileEntry:
        if init.next is None or not init.next.url:
            raise UploadError("s3-single mode requires next.url in init response")
        size = source.size()
        body = await source.read_chunk(0, size)
        headers = dict(init.next.headers or {})
        await self._transport.external_put(
            init.next.url,
            content=body,
            headers=headers,
            content_length=size,
        )
        if progress is not None:
            try:
                progress(size, size)
            except Exception:  # pragma: no cover
                pass
        return await self._sessions.complete(
            init.uploadSessionId,
            complete_url=init.next.completeUrl,
        )
