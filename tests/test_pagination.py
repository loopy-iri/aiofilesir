"""Tests for the generic pagination iterator."""
from __future__ import annotations

import pytest

from filesir.models import Page
from filesir.pagination import paginate


@pytest.mark.asyncio
async def test_paginate_yields_all_items_and_stops_on_last_page() -> None:
    pages = {
        1: Page[int](data=[1, 2, 3], total=6, current_page=1, per_page=3, last_page=2),
        2: Page[int](data=[4, 5, 6], total=6, current_page=2, per_page=3, last_page=2),
        3: Page[int](data=[99], total=6, current_page=3, per_page=3, last_page=2),
    }

    async def fetch(page: int, per_page: int) -> Page[int]:
        return pages[page]

    out: list[int] = []
    async for x in paginate(fetch, per_page=3):
        out.append(x)
    assert out == [1, 2, 3, 4, 5, 6]


@pytest.mark.asyncio
async def test_paginate_stops_on_empty_page() -> None:
    pages = {
        1: Page[int](data=[1]),
        2: Page[int](data=[]),
    }

    async def fetch(page: int, per_page: int) -> Page[int]:
        return pages[page]

    out: list[int] = [x async for x in paginate(fetch, per_page=1)]
    assert out == [1]


@pytest.mark.asyncio
async def test_paginate_invalid_per_page() -> None:
    async def fetch(page: int, per_page: int) -> Page[int]:
        return Page[int](data=[])

    with pytest.raises(ValueError):
        async for _ in paginate(fetch, per_page=0):
            pass
