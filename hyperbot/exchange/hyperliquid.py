from __future__ import annotations

from typing import Any

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

from hyperbot.core.config import Settings
from hyperbot.core.logging import StructuredLogMixin
from hyperbot.exchange.base import ExchangeClient


class HyperLiquidClient(ExchangeClient, StructuredLogMixin):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._connected = False
        self.wallet_address: str | None = None
        self._info: Info | None = None
        self._exchange: Exchange | None = None
        self._account = None

    def authenticate(self) -> None:
        if not self.settings.api_private_key:
            raise ValueError("HYPERBOT_API_PRIVATE_KEY is required")

        self._account = Account.from_key(self.settings.api_private_key)

        if self.settings.account_address:
            self.wallet_address = self.settings.account_address
            self.log_event(
                "exchange.authenticate",
                mode="agent",
                agent=self._account.address,
                master=self.wallet_address,
            )
        else:
            self.wallet_address = self._account.address
            self.log_event("exchange.authenticate", mode="direct", wallet=self.wallet_address)

    async def connect(self) -> None:
        self.authenticate()
        base_url = constants.TESTNET_API_URL if self.settings.api_testnet else constants.MAINNET_API_URL

        try:
            self._info = Info(base_url, skip_ws=True)
            self._exchange = Exchange(
                wallet=self._account,
                base_url=base_url,
                account_address=self.wallet_address,
            )
            self._connected = True
            self.log_event(
                "exchange.connect",
                network="testnet" if self.settings.api_testnet else "mainnet",
                address=self.wallet_address,
            )
        except Exception as e:
            self._connected = False
            self.log_event("exchange.connect_error", error=str(e))
            raise

    async def disconnect(self) -> None:
        self._connected = False
        self._info = None
        self._exchange = None
        self.log_event("exchange.disconnect")

    def _ensure_connected(self) -> None:
        if not self._connected or self._exchange is None or self._info is None:
            raise RuntimeError("Client is not connected")

    async def get_account_balance(self) -> dict[str, Any]:
        self._ensure_connected()
        try:
            return self._info.user_state(self.wallet_address)
        except Exception as e:
            self.log_event("exchange.balance_error", error=str(e))
            raise

    async def get_positions(self) -> list[dict[str, Any]]:
        state = await self.get_account_balance()
        positions = []
        for asset_pos in state.get("assetPositions", []):
            pos = asset_pos.get("position", {})
            if float(pos.get("szi", 0)) != 0:
                positions.append(pos)
        return positions

    async def get_open_orders(self) -> list[dict[str, Any]]:
        self._ensure_connected()
        try:
            return self._info.open_orders(self.wallet_address)
        except Exception as e:
            self.log_event("exchange.open_orders_error", error=str(e))
            raise

    async def place_limit_order(
        self,
        *,
        symbol: str,
        side: str,
        size: float,
        price: float,
        reduce_only: bool = False,
        tif: str = "Gtc",
    ) -> dict[str, Any]:
        self._ensure_connected()
        is_buy = side.lower() in ("buy", "b", "long")

        try:
            result = self._exchange.order(
                name=symbol,
                is_buy=is_buy,
                sz=size,
                limit_px=price,
                order_type={"limit": {"tif": tif}},
                reduce_only=reduce_only,
            )
        except Exception as e:
            self.log_event("exchange.place_limit_error", error=str(e), symbol=symbol, side=side, price=price)
            return {"status": "error", "error": str(e)}

        if not isinstance(result, dict) or result.get("status") != "ok":
            self.log_event("exchange.place_limit_failed", result=str(result)[:300])
            return {"status": "error", "raw": result}

        self.log_event("exchange.place_limit_ok", symbol=symbol, side=side, size=size, price=price)
        return result

    async def place_market_order(
        self,
        *,
        symbol: str,
        side: str,
        size: float,
        reduce_only: bool = False,
        slippage: float = 0.01,
    ) -> dict[str, Any]:
        self._ensure_connected()
        is_buy = side.lower() in ("buy", "b", "long")

        try:
            result = self._exchange.market_open(
                name=symbol,
                is_buy=is_buy,
                sz=size,
                px=None,
                slippage=slippage,
            )
        except Exception as e:
            self.log_event("exchange.place_market_error", error=str(e))
            return {"status": "error", "error": str(e)}

        if not isinstance(result, dict) or result.get("status") != "ok":
            return {"status": "error", "raw": result}

        return result

    async def cancel_order(self, *, symbol: str, oid: int) -> dict[str, Any]:
        self._ensure_connected()
        try:
            result = self._exchange.cancel(symbol, oid)
            self.log_event("exchange.cancel_ok", symbol=symbol, oid=oid)
            return result
        except Exception as e:
            self.log_event("exchange.cancel_error", error=str(e), oid=oid)
            return {"status": "error", "error": str(e)}

    async def cancel_all_orders(self, symbol: str | None = None) -> dict[str, Any]:
        try:
            open_orders = await self.get_open_orders()
        except Exception as e:
            return {"status": "error", "error": str(e)}

        cancelled = 0
        errors = 0
        for order in open_orders:
            if symbol and order.get("coin") != symbol:
                continue
            res = await self.cancel_order(symbol=order["coin"], oid=order["oid"])
            if res.get("status") == "error":
                errors += 1
            else:
                cancelled += 1

        return {"cancelled": cancelled, "errors": errors}

    async def subscribe_market_data(self, symbols: list[str]) -> None:
        self.log_event("exchange.subscribe", symbols=symbols)