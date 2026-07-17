from __future__ import annotations

from typing import Any, Callable

from hyperbot.core.config import Settings
from hyperbot.core.logging import StructuredLogMixin
from hyperbot.exchange.websocket import HyperLiquidWebSocketClient


class HyperliquidWSManager(StructuredLogMixin):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = HyperLiquidWebSocketClient(settings.websocket_base_url)
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        await self.client.connect()
        self._running = True
        self.log_event("ws.started")

    async def stop(self) -> None:
        if not self._running:
            return
        await self.client.disconnect()
        self._running = False
        self.log_event("ws.stopped")

    def on(self, event_name: str, handler: Callable[[dict[str, Any]], Any]) -> None:
        self.client.on(event_name, handler)

    def subscribe_l2book(self, symbol: str) -> None:
        self.client.subscribe_l2book(symbol)

    def subscribe_user_events(self, wallet: str) -> None:
        self.client.subscribe_user_events(wallet)

    def subscribe_order_updates(self, wallet: str) -> None:
        self.client.subscribe_order_updates(wallet)
