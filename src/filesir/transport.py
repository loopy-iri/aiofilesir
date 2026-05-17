"""HTTP transport layer for the Files.ir client.

This module owns the single :class:`httpx.AsyncClient` used by the library and
provides:

* :class:`RetryPolicy` — configurable attempts/backoff, honors ``Retry-After``.
* :class:`Transport` — Bearer-token injection, JSON helpers, streaming download,
  external (S3/TUS) PUT helper, error-mapping, and retry orchestration.
* :class:`StreamingResponse` — small wrapper around an open ``httpx.Response``
  exposing :meth:`aiter_bytes` / :meth:`aiter_chunks`.
"""
from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import (
    Any,
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Mapping,
)

import httpx

from .exceptions import (
    AuthenticationError,
    FilesIrError,
    ForbiddenError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from .logging import install_default_redactor, logger

DEFAULT_BASE_URL = "https://my.files.ir/api/v1"
_DEFAULT_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryPolicy:
    """Configures retry attempts and exponential backoff."""

    max_attempts: int = 3
    initial_backoff: float = 0.5
    max_backoff: float = 30.0
    backoff_multiplier: float = 2.0
    backoff_jitter: float = 0.2
    retryable_status_codes: frozenset[int] = _DEFAULT_RETRYABLE_STATUS

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.initial_backoff <= 0:
            raise ValueError("initial_backoff must be > 0")
        if self.max_backoff < self.initial_backoff:
            raise ValueError("max_backoff must be >= initial_backoff")
        if self.backoff_multiplier < 1.0:
            raise ValueError("backoff_multiplier must be >= 1.0")
        if not (0.0 <= self.backoff_jitter <= 1.0):
            raise ValueError("backoff_jitter must be in [0, 1]")

    def should_retry(self, attempt: int, error: BaseException | int) -> bool:
        if attempt >= self.max_attempts:
            return False
        if isinstance(error, int):
            return error in self.retryable_status_codes
        return isinstance(
            error,
            (httpx.TransportError, httpx.ReadTimeout, httpx.ConnectTimeout),
        )

    def next_delay(self, attempt: int, retry_after: float | None) -> float:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        if retry_after is not None:
            return max(0.0, min(retry_after, self.max_backoff))
        base = self.initial_backoff * (self.backoff_multiplier ** (attempt - 1))
        if self.backoff_jitter > 0:
            jitter = 1.0 + random.uniform(-self.backoff_jitter, self.backoff_jitter)
            base *= jitter
        return max(0.0, min(base, self.max_backoff))


def parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header value (seconds-or-HTTP-date) into seconds."""

    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    # delta-seconds form
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    # HTTP-date form
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = (dt - datetime.now(tz=timezone.utc)).total_seconds()
    return max(0.0, delta)


# ---------------------------------------------------------------------------
# StreamingResponse helper
# ---------------------------------------------------------------------------


class StreamingResponse:
    """Wraps an open ``httpx.Response`` for streaming consumption."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.status_code = response.status_code
        self.headers = response.headers

    async def aiter_bytes(self, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
        async for chunk in self._response.aiter_bytes(chunk_size=chunk_size):
            yield chunk

    async def aiter_chunks(self) -> AsyncIterator[bytes]:
        async for chunk in self._response.aiter_raw():
            yield chunk


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


def _extract_message(body: Any, default: str) -> str:
    if isinstance(body, dict):
        for key in ("message", "error", "detail"):
            value = body.get(key)
            if isinstance(value, str) and value:
                return value
    return default


def _try_parse_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return None


def map_response_error(response: httpx.Response) -> FilesIrError:
    """Map a non-2xx ``httpx.Response`` into a typed :class:`FilesIrError`."""

    status = response.status_code
    body = _try_parse_json(response)
    message = _extract_message(body, default=f"HTTP {status}")

    if status == 401:
        return AuthenticationError(message, response=response)
    if status == 403:
        return ForbiddenError(message, response=response)
    if status == 404:
        return NotFoundError(message, response=response)
    if status == 422:
        errors: dict[str, str] = {}
        if isinstance(body, dict):
            raw_errors = body.get("errors")
            if isinstance(raw_errors, dict):
                for k, v in raw_errors.items():
                    if isinstance(v, list) and v:
                        errors[str(k)] = str(v[0])
                    else:
                        errors[str(k)] = str(v)
        return ValidationError(message, errors=errors, response=response)
    if status == 429:
        retry_after = parse_retry_after(response.headers.get("Retry-After"))
        return RateLimitError(message, retry_after=retry_after, response=response)
    if 500 <= status < 600:
        return ServerError(message, response=response)
    return FilesIrError(message, response=response)


def map_transport_error(error: BaseException) -> FilesIrError:
    return NetworkError(f"network error: {error}")


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


_RequestFactory = Callable[[], Awaitable[httpx.Response]]


class Transport:
    """Owns the :class:`httpx.AsyncClient` shared by every resource façade."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = 30.0,
        retry: RetryPolicy | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        install_default_redactor()
        self._base_url = base_url.rstrip("/")
        self._retry = retry or RetryPolicy()
        self._access_token: str | None = None
        self._owns_client = http_client is None
        if http_client is None:
            self._client = httpx.AsyncClient(timeout=timeout)
        else:
            self._client = http_client
        self._timeout = timeout

    # ------------------------------------------------------------------ token

    @property
    def access_token(self) -> str | None:
        return self._access_token

    def set_access_token(self, token: str | None) -> None:
        self._access_token = token

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def retry_policy(self) -> RetryPolicy:
        return self._retry

    # ------------------------------------------------------------------ urls

    def _full_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self._base_url}{path}"

    def _auth_headers(self, authenticated: bool) -> dict[str, str]:
        if not authenticated:
            return {}
        if not self._access_token:
            raise AuthenticationError(
                "missing access token; call set_access_token(...) or use "
                "FilesIrClient.from_credentials(...) before authenticated calls",
            )
        return {"Authorization": f"Bearer {self._access_token}"}

    # ------------------------------------------------------------------ retry loop

    async def _execute_with_retry(
        self,
        request_factory: _RequestFactory,
    ) -> httpx.Response:
        last_error: BaseException | None = None
        last_response: httpx.Response | None = None
        for attempt in range(1, self._retry.max_attempts + 1):
            try:
                response = await request_factory()
            except (httpx.TransportError, httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
                last_error = exc
                if self._retry.should_retry(attempt, exc):
                    delay = self._retry.next_delay(attempt, retry_after=None)
                    logger.debug(
                        "transport error on attempt %d/%d; sleeping %.3fs: %s",
                        attempt,
                        self._retry.max_attempts,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise map_transport_error(exc) from exc

            if response.status_code in self._retry.retryable_status_codes:
                last_response = response
                if self._retry.should_retry(attempt, response.status_code):
                    retry_after = parse_retry_after(response.headers.get("Retry-After"))
                    delay = self._retry.next_delay(attempt, retry_after=retry_after)
                    logger.debug(
                        "retryable status %d on attempt %d/%d; sleeping %.3fs",
                        response.status_code,
                        attempt,
                        self._retry.max_attempts,
                        delay,
                    )
                    try:
                        await response.aclose()
                    except Exception:  # pragma: no cover
                        pass
                    await asyncio.sleep(delay)
                    continue
            return response

        if last_response is not None:
            raise map_response_error(last_response)
        if last_error is not None:
            raise map_transport_error(last_error)
        raise FilesIrError("retry loop exhausted with no recorded error")

    # ------------------------------------------------------------------ JSON helper

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Mapping[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
        authenticated: bool = True,
        extra_headers: Mapping[str, str] | None = None,
        expect_json: bool = True,
    ) -> Any:
        """Issue an HTTP request and return the JSON-decoded body (``dict``/``list``)."""

        provided = sum(x is not None for x in (json, data, files))
        if provided > 1:
            raise ValueError("at most one of json, data, files may be provided")

        url = self._full_url(path)
        headers: dict[str, str] = {"Accept": "application/json"}
        headers.update(self._auth_headers(authenticated))
        if extra_headers:
            headers.update(extra_headers)

        clean_params = self._clean_params(params)

        async def factory() -> httpx.Response:
            return await self._client.request(
                method,
                url,
                params=clean_params,
                json=json,
                data=data,
                files=files,
                headers=headers,
            )

        response = await self._execute_with_retry(factory)
        try:
            if response.status_code >= 400:
                raise map_response_error(response)
            if not expect_json:
                return None
            if response.status_code == 204 or not response.content:
                return None
            return response.json()
        finally:
            try:
                await response.aclose()
            except Exception:  # pragma: no cover
                pass

    # ------------------------------------------------------------------ stream download

    @asynccontextmanager
    async def stream_download(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        authenticated: bool = True,
    ) -> AsyncIterator[StreamingResponse]:
        """Yield an open :class:`StreamingResponse` whose body is consumed lazily."""

        url = self._full_url(path)
        headers: dict[str, str] = {}
        headers.update(self._auth_headers(authenticated))
        clean_params = self._clean_params(params)
        request = self._client.build_request("GET", url, params=clean_params, headers=headers)
        response = await self._client.send(request, stream=True)
        try:
            if response.status_code >= 400:
                # Need the body to extract a meaningful message.
                await response.aread()
                raise map_response_error(response)
            yield StreamingResponse(response)
        finally:
            try:
                await response.aclose()
            except Exception:  # pragma: no cover
                pass

    # ------------------------------------------------------------------ external PUT

    async def external_put(
        self,
        url: str,
        *,
        content: bytes | AsyncIterable[bytes],
        headers: Mapping[str, str] | None = None,
        content_length: int | None = None,
    ) -> httpx.Response:
        """PUT to an external URL (S3 signed URL); never adds ``Authorization``."""

        send_headers: dict[str, str] = {}
        if headers:
            send_headers.update(headers)
        if content_length is not None and "Content-Length" not in send_headers:
            send_headers["Content-Length"] = str(content_length)

        async def factory() -> httpx.Response:
            return await self._client.request(
                "PUT",
                url,
                content=content,
                headers=send_headers,
            )

        response = await self._execute_with_retry(factory)
        if response.status_code >= 400:
            raise map_response_error(response)
        return response

    # ------------------------------------------------------------------ misc helpers

    @staticmethod
    def _clean_params(params: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if not params:
            return None
        cleaned: dict[str, Any] = {}
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, bool):
                cleaned[key] = "true" if value else "false"
            elif isinstance(value, (list, tuple)):
                cleaned[key] = ",".join(str(v) for v in value)
            else:
                cleaned[key] = value
        return cleaned or None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


__all__ = [
    "DEFAULT_BASE_URL",
    "RetryPolicy",
    "StreamingResponse",
    "Transport",
    "map_response_error",
    "map_transport_error",
    "parse_retry_after",
]
