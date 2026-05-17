"""File source abstractions used by the upload subsystem."""
from __future__ import annotations

import asyncio
import mimetypes
import os
from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class FileSource(Protocol):
    """Abstract source of bytes for an upload.

    Implementations must:

    * report a stable :meth:`size` (in bytes);
    * report a non-empty :meth:`filename`;
    * support random reads via :meth:`read_chunk(offset, length)` returning at
      most ``length`` bytes;
    * support a sequential :meth:`read_stream` for "single" / "s3-single" / TUS
      modes that don't need random access.
    """

    def filename(self) -> str: ...

    def size(self) -> int: ...

    async def read_chunk(self, offset: int, length: int) -> bytes: ...

    def read_stream(self) -> AsyncIterator[bytes]: ...

    def content_type(self) -> str | None: ...


class BytesSource:
    """In-memory bytes-backed file source."""

    def __init__(
        self,
        data: bytes | bytearray | memoryview,
        *,
        filename: str,
        content_type: str | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        if not filename:
            raise ValueError("filename must be non-empty")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        self._data = bytes(data)
        self._filename = filename
        self._content_type = content_type or _guess_mime(filename)
        self._chunk_size = chunk_size

    def filename(self) -> str:
        return self._filename

    def size(self) -> int:
        return len(self._data)

    async def read_chunk(self, offset: int, length: int) -> bytes:
        if offset < 0:
            raise ValueError("offset must be >= 0")
        if length < 0:
            raise ValueError("length must be >= 0")
        end = min(offset + length, len(self._data))
        return self._data[offset:end]

    async def read_stream(self) -> AsyncIterator[bytes]:
        for i in range(0, len(self._data), self._chunk_size):
            yield self._data[i : i + self._chunk_size]

    def content_type(self) -> str | None:
        return self._content_type


class PathSource:
    """Filesystem-path-backed file source."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        filename: str | None = None,
        content_type: str | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        self._path = os.fspath(path)
        if not os.path.isfile(self._path):
            raise FileNotFoundError(f"not a regular file: {self._path}")
        self._filename = filename or os.path.basename(self._path)
        if not self._filename:
            raise ValueError("filename must be non-empty")
        self._content_type = content_type or _guess_mime(self._filename)
        self._size = os.stat(self._path).st_size
        self._chunk_size = chunk_size

    def filename(self) -> str:
        return self._filename

    def size(self) -> int:
        return self._size

    async def read_chunk(self, offset: int, length: int) -> bytes:
        if offset < 0:
            raise ValueError("offset must be >= 0")
        if length < 0:
            raise ValueError("length must be >= 0")
        return await asyncio.to_thread(self._read_chunk_sync, offset, length)

    def _read_chunk_sync(self, offset: int, length: int) -> bytes:
        with open(self._path, "rb") as fh:
            fh.seek(offset)
            return fh.read(length)

    async def read_stream(self) -> AsyncIterator[bytes]:
        offset = 0
        while offset < self._size:
            chunk = await self.read_chunk(offset, self._chunk_size)
            if not chunk:
                break
            yield chunk
            offset += len(chunk)

    def content_type(self) -> str | None:
        return self._content_type


def make_source(
    source: FileSource | str | os.PathLike[str] | bytes | bytearray | memoryview,
    *,
    filename: str | None = None,
    content_type: str | None = None,
) -> FileSource:
    """Factory that turns common inputs into a :class:`FileSource`."""

    if isinstance(source, FileSource):
        return source
    if isinstance(source, (bytes, bytearray, memoryview)):
        if not filename:
            raise ValueError("filename is required when uploading from bytes")
        return BytesSource(source, filename=filename, content_type=content_type)
    if isinstance(source, (str, os.PathLike)):
        return PathSource(source, filename=filename, content_type=content_type)
    raise TypeError(f"unsupported source type: {type(source)!r}")


def _guess_mime(filename: str) -> str | None:
    mime, _ = mimetypes.guess_type(filename)
    return mime


__all__ = ["BytesSource", "FileSource", "PathSource", "make_source"]
