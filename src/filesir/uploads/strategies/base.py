"""Abstract strategy base class."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, TYPE_CHECKING

from ...models import FileEntry, NewUploadInitResponse

if TYPE_CHECKING:
    from ...transport import Transport
    from ..sessions import NewUploadSessionClient
    from ..sources import FileSource

ProgressCallback = Callable[[int, int], None]


class UploadStrategy(ABC):
    def __init__(
        self,
        *,
        sessions: "NewUploadSessionClient",
        transport: "Transport",
        concurrency: int,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        self._sessions = sessions
        self._transport = transport
        self._concurrency = concurrency

    @abstractmethod
    async def upload(
        self,
        *,
        source: "FileSource",
        init: NewUploadInitResponse,
        progress: ProgressCallback | None,
    ) -> FileEntry: ...
