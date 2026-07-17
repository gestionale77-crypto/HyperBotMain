from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets
from websockets.legacy.client import WebSocketClientProtocol


class HyperLiquidWebSocketClient:
    def __init__(self, url: str, *, reconnect_delay: float = 0.5, max_reconnect_delay: float = 8.0) -> None:
        self.url = url
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self._connected = False
        self._stop_event = asyncio.Event()
        self._subscriptions: list[dict[str, Any]] = []
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._reconnect_attempt = 0
        self._ws: Any | None = None
        self._listener_task: asyncio.Task[None] | None = None
        self._handlers: dict[str, list[Callable[[dict[str, Any]], Any]]] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    def add_subscription(self, channel: str, payload: dict[str, Any] | None = None) -> None:
        self._subscriptions.append({"channel": channel, "payload": payload or {}})

    def clear_subscriptions(self) -> None:
        self._subscriptions.clear()

    def subscription_count(self) -> int:
        return len(self._subscriptions)

    def get_subscription_snapshot(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._subscriptions]

    async def connect(self) -> None:
        self._stop_event.clear()
        if self._connected and self._ws is not None:
            return
        try:
            self._ws = await asyncio.wait_for(websockets.connect(self.url), timeout=5.0)
            self._connected = True
            self._reconnect_attempt = 0
            self._listener_task = asyncio.create_task(self._listen_loop())
            for subscription in self._subscriptions:
                await self._send_subscription(subscription)
        except Exception:
            self._connected = False
            raise

    async def disconnect(self) -> None:
        self._connected = False
        self._stop_event.set()
        if self._listener_task is not None:
            self._listener_task.cancel()
            self._listener_task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    def get_backoff_delay(self, attempt: int) -> float:
        delay = min(self.reconnect_delay * (2 ** (attempt - 1)), self.max_reconnect_delay)
        return float(round(delay, 6))

    async def subscribe(self, channel: str, payload: dict[str, Any] | None = None) -> None:
        self.add_subscription(channel, payload)
        if self._connected and self._ws is not None:
            await self._send_subscription({"channel": channel, "payload": payload or {}})
        await self._emit_event({"type": "subscription", "channel": channel, "payload": payload or {}})

    async def unsubscribe(self, channel: str) -> None:
        self._subscriptions = [item for item in self._subscriptions if item.get("channel") != channel]
        await self._emit_event({"type": "unsubscription", "channel": channel})

    async def send_ping(self) -> None:
        if self._connected and self._ws is not None:
            await self._ws.send(json.dumps({"method": "ping"}))
            await self._emit_event({"type": "heartbeat", "message": "ping"})

    def on(self, event_name: str, handler: Callable[[dict[str, Any]], Any]) -> None:
        self._handlers.setdefault(event_name, []).append(handler)

    def _dispatch(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type") or event.get("channel") or "message")
        for handler in list(self._handlers.get(event_type, [])):
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception:
                pass

    async def _emit_event(self, event: dict[str, Any]) -> None:
        await self._event_queue.put(event)
        self._dispatch(event)

    async def _send_subscription(self, subscription: dict[str, Any]) -> None:
        if self._ws is None:
            return
        payload = {
            "method": "subscribe",
            "channel": subscription["channel"],
            "payload": subscription.get("payload", {}),
        }
        await self._ws.send(json.dumps(payload))

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            event = await self._event_queue.get()
            yield event

    async def handle_message(self, message: str | bytes) -> None:
        text = message.decode("utf-8") if isinstance(message, bytes) else message
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"raw": text}

        event = {"type": "message", "payload": parsed}
        if isinstance(parsed, dict):
            if parsed.get("channel"):
                event = {"type": parsed["channel"], "payload": parsed}
            elif parsed.get("data", {}).get("channel"):
                event = {"type": parsed["data"]["channel"], "payload": parsed}
            elif parsed.get("type"):
                event = {"type": parsed["type"], "payload": parsed}

        await self._emit_event(event)

    async def _listen_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._ws is None:
                await asyncio.sleep(0.1)
                continue
            try:
                message = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
                await self.handle_message(message)
            except asyncio.TimeoutError:
                await self.send_ping()
            except Exception:
                self._connected = False
                if not self._stop_event.is_set():
                    await self.reconnect()
                break

    def subscribe_l2book(self, symbol: str) -> None:
        self.add_subscription("l2Book", {"symbol": symbol})

    def subscribe_user_events(self, wallet: str) -> None:
        self.add_subscription("userEvents", {"wallet": wallet})

    def subscribe_order_updates(self, wallet: str) -> None:
        self.add_subscription("orderUpdates", {"wallet": wallet})

    async def reconnect(self) -> None:
        self._reconnect_attempt += 1
        delay = self.get_backoff_delay(self._reconnect_attempt)
        await asyncio.sleep(delay)
        try:
            await self.connect()
        except Exception:
            self._connected = False
