from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def gather_with_timeout(coro_factory: Callable[[], Awaitable[T]], timeout: float) -> T:
    return await asyncio.wait_for(coro_factory(), timeout=timeout)
