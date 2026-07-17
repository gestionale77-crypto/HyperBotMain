from __future__ import annotations

from typing import Any, cast

from eth_account import Account
from hyperliquid.exchange import Exchange  # type: ignore[import-untyped]
from hyperliquid.info import Info  # type: ignore[import-untyped]
from hyperliquid.utils import constants  # type: ignore[import-untyped]

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
        self._account: Account | None = None

    def authenticate(self) -> None:
        if not self.settings.api_private_key:
            if self.settings.environment == "development":
                self.wallet_address = "0xdevwallet"
                self.log_event("exchange.authenticate", wallet=self.wallet_address, mode="development")
                return
            raise ValueError("API private key is required")

        account = Account.from_key(self.settings.api_private_key)
        self._account = account
        self.wallet_address = self.settings.account_address or account.address
        self.log_event(
            "exchange.authenticate",
            mode="agent" if self.settings.account_address else "direct",
            wallet=self.wallet_address,
            derived_address=account.address,
        )

    async def connect(self) -> None:
        self.authenticate()
        base_url = (
            constants.TESTNET_API_URL if self.settings.api_testnet else constants.MAINNET_API_URL
        )
        self._info = Info(base_url, skip_ws=True)
        if self.settings.environment == "development" and self._account is None:
            self._exchange = None
            self._connected = True
            self.log_event(
                "exchange.connect",
                exchange="hyperliquid",
                network="testnet" if self.settings.api_testnet else "mainnet",
                address=self.wallet_address,
                mode="development",
            )
            return

        assert self._account is not None
        self._exchange = Exchange(
            wallet=self._account,
            base_url=base_url,
            account_address=self.wallet_address,
        )
        self._connected = True
        self.log_event(
            "exchange.connect",
            exchange="hyperliquid",
            network="testnet" if self.settings.api_testnet else "mainnet",
            address=self.wallet_address,
        )

    async def disconnect(self) -> None:
        self._connected = False
        self._info = None
        self._exchange = None
        self.log_event("exchange.disconnect")

    async def subscribe_market_data(self, symbols: list[str]) -> None:
        self.log_event("exchange.subscribe", symbols=symbols)

    async def get_account_balance(self) -> dict[str, Any]:
        if not self._info or not self.wallet_address:
            raise RuntimeError("Client is not connected")
        state = self._info.user_state(self.wallet_address)
        return cast(dict[str, Any], state)

    async def get_positions(self) -> list[dict[str, Any]]:
        state = await self.get_account_balance()
        positions: list[dict[str, Any]] = []
        for asset_pos in state.get("assetPositions", []):
            position = asset_pos.get("position", {})
            if float(position.get("szi", 0)) != 0:
                positions.append(position)
        return positions

    async def get_open_orders(self) -> list[dict[str, Any]]:
        if not self._info or not self.wallet_address:
            raise RuntimeError("Client is not connected")
        orders = self._info.open_orders(self.wallet_address)
        return cast(list[dict[str, Any]], orders)

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
        if not self._exchange:
            raise RuntimeError("Client is not connected")
        is_buy = side.lower() in {"buy", "b", "long"}
        result = self._exchange.order(
            name=symbol,
            is_buy=is_buy,
            sz=size,
            limit_px=price,
            order_type={"limit": {"tif": tif}},
            reduce_only=reduce_only,
        )
        self.log_event(
            "exchange.place_limit",
            symbol=symbol,
            side=side,
            size=size,
            price=price,
            result=result.get("status"),
        )
        return cast(dict[str, Any], result)

    async def place_market_order(
        self,
        *,
        symbol: str,
        side: str,
        size: float,
        reduce_only: bool = False,
        slippage: float = 0.01,
    ) -> dict[str, Any]:
        if not self._exchange:
            raise RuntimeError("Client is not connected")
        is_buy = side.lower() in {"buy", "b", "long"}
        result = self._exchange.market_open(
            name=symbol,
            is_buy=is_buy,
            sz=size,
            px=None,
            slippage=slippage,
        )
        self.log_event(
            "exchange.place_market",
            symbol=symbol,
            side=side,
            size=size,
            result=result.get("status"),
        )
        return cast(dict[str, Any], result)

    async def cancel_order(self, *, symbol: str, oid: int) -> dict[str, Any]:
        if not self._exchange:
            raise RuntimeError("Client is not connected")
        result = self._exchange.cancel(symbol, oid)
        self.log_event("exchange.cancel", symbol=symbol, oid=oid, result=result.get("status"))
        return cast(dict[str, Any], result)

    async def cancel_all_orders(self, symbol: str | None = None) -> dict[str, Any]:
        open_orders = await self.get_open_orders()
        results: list[dict[str, Any]] = []
        for order in open_orders:
            if symbol and order.get("coin") != symbol:
                continue
            results.append(await self.cancel_order(symbol=order["coin"], oid=order["oid"]))
        return {"cancelled": len(results), "results": results}
