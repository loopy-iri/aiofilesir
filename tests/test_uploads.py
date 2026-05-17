"""End-to-end upload-flow tests against ``httpx.MockTransport``."""
from __future__ import annotations

import math
from typing import Any

import httpx
import pytest

from filesir import FilesIrClient
from filesir.exceptions import UploadError
from filesir.uploads import BytesSource, make_source
from filesir.uploads.strategies import (
    S3MultipartUploadStrategy,
    S3SingleUploadStrategy,
    SingleUploadStrategy,
    TusUploadStrategy,
    select_strategy,
)


def make_client(handler) -> FilesIrClient:
    mock = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=mock)
    return FilesIrClient(
        access_token="t",
        base_url="https://api.example.com",
        http_client=http,
        upload_concurrency=2,
    )


# ---------------------------------------------------------------------------
# Source factory
# ---------------------------------------------------------------------------


def test_make_source_from_bytes_requires_filename() -> None:
    with pytest.raises(ValueError):
        make_source(b"abc")


def test_bytes_source_read_chunk_truncates() -> None:
    src = BytesSource(b"abcdef", filename="x.bin")
    assert src.size() == 6


# ---------------------------------------------------------------------------
# Strategy selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_strategy_dispatches_by_mode() -> None:
    from filesir.models import NewUploadInitResponse
    from filesir.transport import Transport
    from filesir.uploads.sessions import NewUploadSessionClient

    transport = Transport(http_client=httpx.AsyncClient())
    sessions = NewUploadSessionClient(transport)
    try:
        for mode, cls in [
            ("single", SingleUploadStrategy),
            ("s3-single", S3SingleUploadStrategy),
            ("s3-multipart", S3MultipartUploadStrategy),
            ("tus", TusUploadStrategy),
        ]:
            init = NewUploadInitResponse.model_validate({
                "uploadSessionId": "sid", "uploadMode": mode,
            })
            strat = select_strategy(init, sessions=sessions, transport=transport, concurrency=1)
            assert isinstance(strat, cls)
    finally:
        await transport.aclose()


# ---------------------------------------------------------------------------
# Mode: single
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_file_single_mode() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/uploads-new/init"):
            return httpx.Response(201, json={
                "status": "success",
                "uploadSessionId": "sid-single",
                "uploadMode": "single",
            })
        if path.endswith("/uploads-new/sid-single/file"):
            return httpx.Response(201, json={
                "status": "success",
                "fileEntry": {"id": 7, "name": "f.bin"},
            })
        return httpx.Response(404, json={"message": "not handled"})

    client = make_client(handler)
    async with client:
        entry = await client.uploads.upload_file(
            b"hello", filename="f.bin",
        )
        assert entry.id == 7
        assert any(r.url.path.endswith("/uploads-new/init") for r in seen)
        assert any(r.url.path.endswith("/uploads-new/sid-single/file") for r in seen)


# ---------------------------------------------------------------------------
# Mode: s3-single
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_file_s3_single_mode() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url)))
        if request.url.path.endswith("/uploads-new/init"):
            return httpx.Response(201, json={
                "status": "success",
                "uploadSessionId": "sid-s3-single",
                "uploadMode": "s3-single",
                "next": {
                    "method": "PUT",
                    "url": "https://s3.example.com/bucket/object?sig=1",
                    "headers": {"Content-Type": "application/octet-stream"},
                    "completeUrl": "https://api.example.com/uploads-new/sid-s3-single/complete",
                },
            })
        if request.url.host == "s3.example.com":
            # Verify no Authorization header on the S3 PUT.
            assert "Authorization" not in request.headers
            return httpx.Response(200, headers={"ETag": '"single-etag"'})
        if request.url.path.endswith("/uploads-new/sid-s3-single/complete"):
            return httpx.Response(200, json={
                "status": "success",
                "fileEntry": {"id": 88, "name": "f.bin", "file_size": 5},
            })
        return httpx.Response(404)

    client = make_client(handler)
    async with client:
        entry = await client.uploads.upload_file(b"hello", filename="f.bin")
        assert entry.id == 88

    methods_paths = [(m, httpx.URL(u).path) for m, u in seen]
    init_idx = methods_paths.index(("POST", "/uploads-new/init"))
    s3_idx = next(i for i, (m, p) in enumerate(methods_paths)
                  if m == "PUT" and "bucket/object" in p)
    complete_idx = methods_paths.index(("POST", "/uploads-new/sid-s3-single/complete"))
    assert init_idx < s3_idx < complete_idx


# ---------------------------------------------------------------------------
# Mode: s3-multipart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_file_s3_multipart_mode_chunking_and_etags() -> None:
    body = b"x" * 25  # 25 bytes
    part_size = 10
    expected_parts = math.ceil(len(body) / part_size)  # = 3

    seen: list[tuple[str, str]] = []
    s3_chunks: dict[int, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url)))
        path = request.url.path
        if path.endswith("/uploads-new/init"):
            return httpx.Response(201, json={
                "status": "success",
                "uploadSessionId": "sid-mp",
                "uploadMode": "s3-multipart",
                "partSize": part_size,
            })
        if path.endswith("/uploads-new/sid-mp/parts/sign"):
            payload = request.content.decode() if request.content else ""
            assert "partNumbers" in payload
            return httpx.Response(200, json={
                "status": "success",
                "urls": [
                    {"partNumber": i, "url": f"https://s3.example.com/p{i}"}
                    for i in range(1, expected_parts + 1)
                ],
            })
        if request.url.host == "s3.example.com":
            assert "Authorization" not in request.headers
            n = int(request.url.path.lstrip("/p"))
            s3_chunks[n] = bytes(request.content)
            return httpx.Response(200, headers={"ETag": f'"etag-{n}"'})
        if path.endswith("/uploads-new/sid-mp/complete"):
            data = request.content.decode() if request.content else ""
            for n in range(1, expected_parts + 1):
                assert f'"PartNumber":{n}' in data or f'"PartNumber": {n}' in data
            for n in range(1, expected_parts + 1):
                assert f'etag-{n}' in data
            return httpx.Response(200, json={
                "status": "success",
                "fileEntry": {"id": 555, "name": "big.bin", "file_size": len(body)},
            })
        return httpx.Response(404)

    progress: list[tuple[int, int]] = []
    client = make_client(handler)
    async with client:
        entry = await client.uploads.upload_file(
            body, filename="big.bin", progress=lambda d, t: progress.append((d, t)),
        )
    assert entry.id == 555
    # All three chunks were uploaded with the right byte boundaries.
    assert s3_chunks[1] == body[0:10]
    assert s3_chunks[2] == body[10:20]
    assert s3_chunks[3] == body[20:25]
    # Progress monotonic, ends at total.
    assert progress[-1] == (25, 25)


@pytest.mark.asyncio
async def test_upload_file_s3_multipart_missing_part_size_raises() -> None:
    aborted = {"called": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/uploads-new/init"):
            return httpx.Response(201, json={
                "status": "success",
                "uploadSessionId": "sid-bad",
                "uploadMode": "s3-multipart",
                # partSize intentionally missing
            })
        if request.method == "DELETE" and "/uploads-new/sid-bad" in request.url.path:
            aborted["called"] = True
            return httpx.Response(200, json={"status": "success"})
        return httpx.Response(404)

    client = make_client(handler)
    async with client:
        with pytest.raises(UploadError):
            await client.uploads.upload_file(b"abc", filename="x.bin")
    assert aborted["called"] is True


@pytest.mark.asyncio
async def test_upload_file_s3_multipart_aborts_on_part_failure() -> None:
    aborted = {"called": False}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/uploads-new/init"):
            return httpx.Response(201, json={
                "status": "success",
                "uploadSessionId": "sid-fail",
                "uploadMode": "s3-multipart",
                "partSize": 5,
            })
        if path.endswith("/parts/sign"):
            return httpx.Response(200, json={
                "status": "success",
                "urls": [
                    {"partNumber": 1, "url": "https://s3.example.com/p1"},
                    {"partNumber": 2, "url": "https://s3.example.com/p2"},
                ],
            })
        if request.url.host == "s3.example.com":
            # Return without ETag header to trigger UploadError.
            return httpx.Response(200)
        if request.method == "DELETE" and "/uploads-new/sid-fail" in path:
            aborted["called"] = True
            return httpx.Response(200, json={"status": "success"})
        return httpx.Response(404)

    client = make_client(handler)
    async with client:
        with pytest.raises(UploadError):
            await client.uploads.upload_file(b"x" * 7, filename="p.bin")
    assert aborted["called"] is True
