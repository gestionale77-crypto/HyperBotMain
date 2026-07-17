from __future__ import annotations

from typing import Any

from hyperbot.core.config import Settings
from hyperbot.core.logging import StructuredLogMixin
from hyperbot.exchange.event_bus import EventBus
from hyperbot.exchange.hyperliquid import HyperLiquidClient
from hyperbot.exchange.websocket import HyperLiquidWebSocketClient


class TradingRuntime(StructuredLogMixin):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.exchange = HyperLiquidClient(settings)
        self.websocket = HyperLiquidWebSocketClient(settings.websocket_base_url)
        self.event_bus = EventBus()
        self._running = False
        self._started = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        try:
            await self.exchange.connect()
            await self.websocket.connect()
            await self.event_bus.start()
            await self.websocket.subscribe("trades", {"symbol": "BTC"})
            await self.websocket.subscribe("orderbook", {"symbol": "BTC"})
            await self.websocket.send_ping()
            self._running = True
            self._started = True
            self.log_event("runtime.start", status="ready")
        except Exception:
            await self.exchange.disconnect()
            await self.websocket.disconnect()
            await self.event_bus.stop()
            raise

    async def stop(self) -> None:
        if not self._running:
            return
        try:
            await self.event_bus.stop()
            await self.websocket.disconnect()
            await self.exchange.disconnect()
        finally:
            self._running = False
            self.log_event("runtime.stop", status="stopped")

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "exchange": "Hyperliquid",
            "event_queue": self.event_bus._queue.qsize(),
            "started": self._started,
        }
