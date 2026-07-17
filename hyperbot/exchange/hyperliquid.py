from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx

from hyperbot.core.config import Settings
from hyperbot.core.logging import StructuredLogMixin
from hyperbot.core.retry import RetryPolicy, retry_async
from hyperbot.exchange.base import ExchangeClient


class HyperLiquidClient(ExchangeClient, StructuredLogMixin):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(base_url=settings.rest_base_url, timeout=10.0)
        self._retry_policy = RetryPolicy(max_attempts=3, base_delay=0.2)
        self._connected = False
        self.wallet_address: str | None = None
        self._private_key = settings.api_private_key or ""

    def authenticate(self) -> None:
        if not self._private_key:
            if self.settings.environment == "development":
                self.wallet_address = "0xdevwallet"
                self.log_event("exchange.authenticate", wallet=self.wallet_address, mode="development")
                return
            raise ValueError("API private key is required")
        digest = hashlib.sha256(self._private_key.encode("utf-8")).hexdigest()
        self.wallet_address = f"0x{digest[:40]}"
        self.log_event("exchange.authenticate", wallet=self.wallet_address)

    async def connect(self) -> None:
        self._connected = True
        self.authenticate()
        self.log_event("exchange.connect", exchange="hyperliquid")

    async def disconnect(self) -> None:
        self._connected = False
        await self._client.aclose()

    async def subscribe_market_data(self, symbols: list[str]) -> None:
        self.log_event("exchange.subscribe", symbols=symbols)

    async def get_balance(self) -> dict[str, Any]:
        async def _request() -> dict[str, Any]:
            response = await self._client.get("/info")
            response.raise_for_status()
            payload: Any = response.json()
            if not isinstance(payload, dict):
                raise TypeError("Expected JSON object")
            return payload

        return await retry_async(_request, policy=self._retry_policy)

    async def get_positions(self) -> list[dict[str, Any]]:
        return []

    async def get_open_orders(self) -> list[dict[str, Any]]:
        return []

    async def place_limit_order(self, *, symbol: str, side: str, size: float, price: float) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "side": side,
            "size": size,
            "price": price,
            "order_type": "limit",
        }
        return {"status": "accepted", "payload": payload}

    async def place_market_order(self, *, symbol: str, side: str, size: float) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "side": side,
            "size": size,
            "order_type": "market",
        }
        return {"status": "accepted", "payload": payload}

    async def cancel_order(self, *, client_id: str) -> dict[str, Any]:
        return {"status": "cancelled", "client_id": client_id}

    async def cancel_all_orders(self) -> dict[str, Any]:
        return {"status": "cancelled"}

    async def get_account_balance(self) -> dict[str, Any]:
        return await self.get_balance()
