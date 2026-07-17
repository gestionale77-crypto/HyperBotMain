from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from hyperbot.core.logging import StructuredLogMixin
from hyperbot.exchange.websocket import HyperLiquidWebSocketClient


class HyperLiquidWebSocketManager(StructuredLogMixin):
    def __init__(self, client: HyperLiquidWebSocketClient) -> None:
        self.client = client
        self._running = False
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._running:
            return
        await self.client.connect()
        self._running = True
        self._task = asyncio.create_task(self._pump_events())
        self.log_event("ws.manager_started")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        await self.client.disconnect()
        self.log_event("ws.manager_stopped")

    async def subscribe(self, channel: str, payload: dict[str, Any] | None = None) -> None:
        if not self._running:
            await self.start()
        await self.client.subscribe(channel, payload)

    async def _pump_events(self) -> None:
        async for event in self.client.events():
            if not self._running:
                break
            await self._event_queue.put(event)

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        while self._running:
            item = await self._event_queue.get()
            yield item
