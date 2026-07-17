from __future__ import annotations

import asyncio
import fnmatch
import inspect
import itertools
import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventPriority(int, Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class EventType(str, Enum):
    MARKET_TICK = "market.tick"
    ORDER_FILLED = "order.filled"
    ORDER_OPEN = "order.open"
    ORDER_CANCELLED = "order.cancelled"
    POSITION_UPDATE = "position.update"
    RISK_EVENT = "risk.event"
    FUNDING_EVENT = "funding.event"
    LIQUIDATION_EVENT = "liquidation.event"


@dataclass(slots=True)
class EventPayload:
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EventEnvelope:
    event_id: str
    event_type: EventType
    payload: EventPayload
    priority: EventPriority = EventPriority.NORMAL
    created_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class Subscription:
    pattern: str
    handler: Callable[[EventEnvelope], Awaitable[None] | None]
    bus: "EventBus"

    def unsubscribe(self) -> None:
        self.bus.unsubscribe(self.pattern, self.handler)


class EventBus:
    def __init__(
        self,
        *,
        max_workers: int = 4,
        retry_attempts: int = 3,
        retry_delay: float = 0.1,
        max_queue_size: int = 10000,
        dead_letter_handler: Callable[[EventEnvelope, Exception], Awaitable[None] | None] | None = None,
    ) -> None:
        self.max_workers = max_workers
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.max_queue_size = max_queue_size
        self.dead_letter_handler = dead_letter_handler
        self._subscriptions: dict[str, list[Subscription]] = defaultdict(list)
        self._queue: asyncio.PriorityQueue[tuple[int, int, EventEnvelope]] = asyncio.PriorityQueue(maxsize=max_queue_size)
        self._stop_event = asyncio.Event()
        self._workers: list[asyncio.Task[None]] = []
        self._sequence_counter = itertools.count()
        self._logger = logging.getLogger("hyperbot.eventbus")

    def subscribe(self, pattern: str, handler: Callable[[EventEnvelope], Awaitable[None] | None]) -> Subscription:
        subscription = Subscription(pattern=pattern, handler=handler, bus=self)
        self._subscriptions[pattern].append(subscription)
        return subscription

    def unsubscribe(self, pattern: str, handler: Callable[[EventEnvelope], Awaitable[None] | None]) -> None:
        subscriptions = self._subscriptions.get(pattern, [])
        self._subscriptions[pattern] = [item for item in subscriptions if item.handler is not handler]

    async def publish(self, event: EventEnvelope) -> None:
        if not self._workers:
            await self.start()
        await self._queue.put((-event.priority.value, next(self._sequence_counter), event))

    async def start(self) -> None:
        if self._workers:
            return
        self._stop_event.clear()
        for _ in range(self.max_workers):
            self._workers.append(asyncio.create_task(self._run_worker()))

    async def stop(self) -> None:
        self._stop_event.set()
        await self._queue.join()
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def _run_worker(self) -> None:
        while True:
            if self._stop_event.is_set() and self._queue.empty():
                break
            try:
                _, _, event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            try:
                await self._dispatch(event)
            finally:
                self._queue.task_done()

    async def _dispatch(self, event: EventEnvelope) -> None:
        for pattern, subscriptions in self._subscriptions.items():
            if self._matches(pattern, event.event_type.value):
                await asyncio.gather(
                    *(self._run_handler(subscription.handler, event) for subscription in subscriptions),
                    return_exceptions=True,
                )

    async def _run_handler(self, handler: Callable[[EventEnvelope], Awaitable[None] | None], event: EventEnvelope) -> None:
        for attempt in range(self.retry_attempts):
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
                return
            except Exception as exc:  # pragma: no cover - defensive
                self._logger.exception("event_handler_failed event=%s attempt=%s", event.event_id, attempt + 1)
                if attempt == self.retry_attempts - 1:
                    if self.dead_letter_handler is not None:
                        result = self.dead_letter_handler(event, exc)
                        if inspect.isawaitable(result):
                            await result
                    break
                await asyncio.sleep(self.retry_delay * (2**attempt))

    def _matches(self, pattern: str, event_name: str) -> bool:
        if pattern == "*":
            return True
        return fnmatch.fnmatch(event_name, pattern)
