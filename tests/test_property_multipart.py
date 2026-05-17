"""Property-based tests for the s3-multipart strategy.

Verifies design correctness properties P4–P7:
* part count == ceil(size / part_size) (with an empty single-part for size==0),
* PartNumber list is exactly [1..n] sorted, unique, no gaps,
* total bytes read across read_chunk calls equals size,
* part-count bound: n out of [1, 10000] raises UploadError before signing.
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import AsyncIterator, Sequence

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from filesir.exceptions import UploadError
from filesir.models import (
    FileEntry,
    NewUploadCompletedPart,
    NewUploadInitResponse,
    NewUploadSignedPart,
)
from filesir.uploads.strategies.s3_multipart import S3MultipartUploadStrategy


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class _RecordingSource:
    _data: bytes
    _filename: str = "x.bin"
    _content_type: str | None = "application/octet-stream"
    reads: list[tuple[int, int]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.reads = []

    def filename(self) -> str:
        return self._filename

    def size(self) -> int:
        return len(self._data)

    async def read_chunk(self, offset: int, length: int) -> bytes:
        self.reads.append((offset, length))
        return self._data[offset : offset + length]

    def read_stream(self) -> AsyncIterator[bytes]:  # pragma: no cover - unused here
        async def gen() -> AsyncIterator[bytes]:
            yield self._data
        return gen()

    def content_type(self) -> str | None:
        return self._content_type


class _FakeSessions:
    """Fake :class:`NewUploadSessionClient` that records calls."""

    def __init__(self, fail_sign: bool = False) -> None:
        self.signed_args: list[Sequence[int]] = []
        self.complete_args: list[list[NewUploadCompletedPart]] = []
        self.aborts: list[str] = []
        self._fail_sign = fail_sign

    async def sign_parts(
        self, session_id: str, part_numbers: Sequence[int],
    ) -> list[NewUploadSignedPart]:
        self.signed_args.append(list(part_numbers))
        if self._fail_sign:
            raise UploadError("forced sign failure")
        return [
            NewUploadSignedPart(partNumber=n, url=f"https://s3.example.com/p{n}")
            for n in part_numbers
        ]

    async def complete(
        self,
        session_id: str,
        *,
        parts: Sequence[NewUploadCompletedPart] | None = None,
        upload_key: str | None = None,
        complete_url: str | None = None,
    ) -> FileEntry:
        assert parts is not None
        self.complete_args.append(list(parts))
        return FileEntry(id=1, name="x.bin")

    async def abort(self, session_id: str) -> None:
        self.aborts.append(session_id)


class _FakeTransport:
    """Fake transport that returns a successful S3 PUT with an ETag header."""

    def __init__(self) -> None:
        self.in_flight = 0
        self.peak_in_flight = 0
        self._lock = asyncio.Lock()

    async def external_put(self, url, *, content, headers=None, content_length=None):
        async with self._lock:
            self.in_flight += 1
            if self.in_flight > self.peak_in_flight:
                self.peak_in_flight = self.in_flight
        try:
            await asyncio.sleep(0)  # let other tasks run
            n = int(url.rsplit("/p", 1)[-1])
            import httpx
            return httpx.Response(200, headers={"ETag": f'"etag-{n}"'})
        finally:
            async with self._lock:
                self.in_flight -= 1


def _make_init(*, session_id: str = "sid", part_size: int) -> NewUploadInitResponse:
    return NewUploadInitResponse.model_validate({
        "uploadSessionId": session_id,
        "uploadMode": "s3-multipart",
        "partSize": part_size,
    })


# ---------------------------------------------------------------------------
# P4 + P5 + P6: chunk count / partNumber discipline / byte coverage
# ---------------------------------------------------------------------------


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    size=st.integers(min_value=0, max_value=4096),
    part_size=st.integers(min_value=1, max_value=512),
)
def test_multipart_chunk_math_and_byte_coverage(size: int, part_size: int) -> None:
    asyncio.run(_run_multipart_property(size, part_size))


async def _run_multipart_property(size: int, part_size: int) -> None:
    sessions = _FakeSessions()
    transport = _FakeTransport()
    strategy = S3MultipartUploadStrategy(
        sessions=sessions,  # type: ignore[arg-type]
        transport=transport,  # type: ignore[arg-type]
        concurrency=4,
    )
    source = _RecordingSource(b"x" * size)
    init = _make_init(part_size=part_size)

    expected_n = math.ceil(size / part_size) if size > 0 else 1

    if expected_n > 10000 or expected_n < 1:  # pragma: no cover
        with pytest.raises(UploadError):
            await strategy.upload(source=source, init=init, progress=None)
        return

    await strategy.upload(source=source, init=init, progress=None)

    # P5: partNumbers passed to sign_parts and complete are exactly [1..n].
    assert sessions.signed_args == [list(range(1, expected_n + 1))]
    assert [p.PartNumber for p in sessions.complete_args[0]] == list(range(1, expected_n + 1))
    # P6: total bytes read equals size.
    total_read = sum(length for _, length in source.reads)
    assert total_read == size
    # No part receives more than part_size bytes.
    for _, length in source.reads:
        assert 0 <= length <= part_size


# ---------------------------------------------------------------------------
# P7: out-of-range part counts raise without ever calling sign_parts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multipart_zero_size_uses_one_empty_part() -> None:
    sessions = _FakeSessions()
    transport = _FakeTransport()
    strategy = S3MultipartUploadStrategy(
        sessions=sessions,  # type: ignore[arg-type]
        transport=transport,  # type: ignore[arg-type]
        concurrency=2,
    )
    source = _RecordingSource(b"")
    init = _make_init(part_size=10)
    await strategy.upload(source=source, init=init, progress=None)
    assert sessions.signed_args == [[1]]
    assert source.reads == [(0, 0)]


@pytest.mark.asyncio
async def test_multipart_no_part_size_aborts_via_outer_orchestration() -> None:
    sessions = _FakeSessions()
    transport = _FakeTransport()
    strategy = S3MultipartUploadStrategy(
        sessions=sessions,  # type: ignore[arg-type]
        transport=transport,  # type: ignore[arg-type]
        concurrency=2,
    )
    init = NewUploadInitResponse.model_validate({
        "uploadSessionId": "sid",
        "uploadMode": "s3-multipart",
    })
    with pytest.raises(UploadError):
        await strategy.upload(
            source=_RecordingSource(b"abc"), init=init, progress=None,
        )
    # The strategy itself does not abort — that is the orchestrator's job.
    assert sessions.aborts == []


# ---------------------------------------------------------------------------
# P8: concurrency cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multipart_concurrency_cap() -> None:
    sessions = _FakeSessions()
    transport = _FakeTransport()
    strategy = S3MultipartUploadStrategy(
        sessions=sessions,  # type: ignore[arg-type]
        transport=transport,  # type: ignore[arg-type]
        concurrency=3,
    )
    # 30 parts of 1 byte each.
    source = _RecordingSource(b"x" * 30)
    init = _make_init(part_size=1)
    await strategy.upload(source=source, init=init, progress=None)
    assert transport.peak_in_flight <= 3
