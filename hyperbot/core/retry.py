from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay: float = 0.25
    max_delay: float = 5.0
    backoff_multiplier: float = 2.0
    jitter: float = 0.0

    def should_retry(self, attempt: int) -> bool:
        return attempt < self.max_attempts

    def next_delay(self, attempt: int) -> float:
        delay = min(self.base_delay * (self.backoff_multiplier ** (attempt - 1)), self.max_delay)
        if self.jitter <= 0:
            return round(delay, 6)
        jitter_range = delay * self.jitter
        return round(delay + random.uniform(-jitter_range, jitter_range), 6)


T = TypeVar("T")


async def retry_async(
    func: Callable[..., Awaitable[T]],
    *args: object,
    policy: RetryPolicy | None = None,
    **kwargs: object,
) -> T:
    policy = policy or RetryPolicy()
    attempt = 1
    while True:
        try:
            return await func(*args, **kwargs)
        except Exception:
            if not policy.should_retry(attempt):
                raise
            delay = policy.next_delay(attempt)
            await asyncio.sleep(delay)
            attempt += 1
