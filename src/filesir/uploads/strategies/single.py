"""``uploadMode == "single"`` strategy."""
from __future__ import annotations

from ...models import FileEntry, NewUploadInitResponse
from ..sources import FileSource
from .base import ProgressCallback, UploadStrategy


class SingleUploadStrategy(UploadStrategy):
    async def upload(
        self,
        *,
        source: FileSource,
        init: NewUploadInitResponse,
        progress: ProgressCallback | None,
    ) -> FileEntry:
        result = await self._sessions.upload_single(init.uploadSessionId, source)
        if progress is not None:
            try:
                progress(source.size(), source.size())
            except Exception:  # pragma: no cover - user callback
                pass
        return result
