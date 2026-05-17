"""Upload strategy classes (one per server-reported ``uploadMode``)."""
from __future__ import annotations

from .base import ProgressCallback, UploadStrategy
from .s3_multipart import S3MultipartUploadStrategy
from .s3_single import S3SingleUploadStrategy
from .single import SingleUploadStrategy
from .tus import TusUploadStrategy

__all__ = [
    "ProgressCallback",
    "S3MultipartUploadStrategy",
    "S3SingleUploadStrategy",
    "SingleUploadStrategy",
    "TusUploadStrategy",
    "UploadStrategy",
    "select_strategy",
]


def select_strategy(
    init: "object",  # NewUploadInitResponse, but avoid runtime cycle
    *,
    sessions: "object",
    transport: "object",
    concurrency: int,
) -> UploadStrategy:
    """Pick the right strategy based on ``init.uploadMode``."""

    from ...exceptions import UploadError
    from ...models import NewUploadInitResponse
    from ..sessions import NewUploadSessionClient
    from ...transport import Transport

    assert isinstance(init, NewUploadInitResponse)
    assert isinstance(sessions, NewUploadSessionClient)
    assert isinstance(transport, Transport)

    mode = init.uploadMode
    common = {"sessions": sessions, "transport": transport, "concurrency": concurrency}
    if mode == "single":
        return SingleUploadStrategy(**common)
    if mode == "s3-single":
        return S3SingleUploadStrategy(**common)
    if mode == "s3-multipart":
        return S3MultipartUploadStrategy(**common)
    if mode == "tus":
        return TusUploadStrategy(**common)
    raise UploadError(f"unknown uploadMode: {mode!r}")
