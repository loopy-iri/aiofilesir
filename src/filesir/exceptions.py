"""Exception hierarchy for the Files.ir client."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx


class FilesIrError(Exception):
    """Base for every error raised by the library."""

    def __init__(
        self,
        message: str,
        *,
        response: "httpx.Response | None" = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.response = response

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class NetworkError(FilesIrError):
    """Wraps :class:`httpx.TransportError` (and friends) when retries are exhausted."""


class AuthenticationError(FilesIrError):
    """HTTP 401."""


class ForbiddenError(FilesIrError):
    """HTTP 403."""


class NotFoundError(FilesIrError):
    """HTTP 404."""


class ValidationError(FilesIrError):
    """HTTP 422.

    Carries the structured ``errors`` dict and ``message`` extracted from the
    422 response body.
    """

    def __init__(
        self,
        message: str,
        errors: dict[str, str] | None = None,
        *,
        response: "httpx.Response | None" = None,
    ) -> None:
        super().__init__(message, response=response)
        self._errors: dict[str, str] = dict(errors or {})

    @property
    def errors(self) -> dict[str, str]:
        return dict(self._errors)


class RateLimitError(FilesIrError):
    """HTTP 429.

    Exposes the parsed ``retry_after`` value (in seconds, may be ``None``).
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        response: "httpx.Response | None" = None,
    ) -> None:
        super().__init__(message, response=response)
        self._retry_after = retry_after

    @property
    def retry_after(self) -> float | None:
        return self._retry_after


class ServerError(FilesIrError):
    """HTTP 5xx."""


class UploadError(FilesIrError):
    """Upload-flow specific failure.

    Raised for things like an unknown ``uploadMode``, missing ``partSize``,
    out-of-range part counts, missing ETag header on an S3 PUT, or when the
    upload session needs to be aborted because of a transport-level failure.
    """
