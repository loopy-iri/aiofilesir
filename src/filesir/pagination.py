"""Async pagination helpers."""
from __future__ import annotations

from typing import AsyncIterator, Awaitable, Callable, TypeVar

from .models import Page

T = TypeVar("T")

PageFetcher = Callable[[int, int], Awaitable[Page[T]]]


async def paginate(
    fetch_page: PageFetcher[T],
    *,
    per_page: int = 15,
) -> AsyncIterator[T]:
    """Yield every item across paginated responses.

    ``fetch_page`` must be an async callable accepting ``(page, per_page)`` and
    returning a :class:`Page` instance. The iterator terminates when the server
    reports ``current_page >= last_page``, when an empty page is returned, or
    when ``page * per_page >= total``.
    """

    if per_page < 1:
        raise ValueError("per_page must be >= 1")

    page = 1
    while True:
        result = await fetch_page(page, per_page)
        if not result.data:
            return
        for item in result.data:
            yield item
        if result.last_page is not None and page >= result.last_page:
            return
        if result.total is not None and page * per_page >= result.total:
            return
        page += 1


__all__ = ["paginate"]
