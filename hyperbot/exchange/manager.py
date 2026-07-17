from __future__ import annotations

import asyncio
import inspect
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    SUBMITTING = "SUBMITTING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    LIQUIDATED = "LIQUIDATED"


class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    POST_ONLY = "POST_ONLY"
    IOC = "IOC"
    FOK = "FOK"
    STOP = "STOP"
    TAKE_PROFIT = "TAKE_PROFIT"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(slots=True)
class FillRecord:
    fill_id: str
    filled_quantity: float
    fill_price: float
    fees: float = 0.0
    timestamp: str = ""


@dataclass(slots=True)
class OrderRecord:
    uuid: str
    symbol: str
    side: Side
    order_type: OrderType
    quantity: float
    remaining_quantity: float
    price: float | None
    leverage: float = 1.0
    status: OrderStatus = OrderStatus.CREATED
    filled_quantity: float = 0.0
    average_fill_price: float | None = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    funding_paid: float = 0.0
    fees: float = 0.0
    exchange_order_id: str | None = None
    client_order_id: str | None = None
    created_at: str = ""
    submitted_at: str = ""
    acknowledged_at: str = ""
    last_update: str = ""
    filled_at: str = ""
    cancelled_at: str = ""
    fills: list[FillRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class OrderManager:
    def __init__(self) -> None:
        self._orders_by_uuid: dict[str, OrderRecord] = {}
        self._orders_by_exchange_id: dict[str, OrderRecord] = {}
        self._orders_by_client_id: dict[str, OrderRecord] = {}
        self._callbacks: dict[str, list[Callable[[OrderRecord], Awaitable[None] | None]]] = {}

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _validate_order(self, *, quantity: float, price: float | None, leverage: float, order_type: OrderType) -> None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if leverage <= 0:
            raise ValueError("leverage must be positive")
        if price is not None and price <= 0:
            raise ValueError("price must be positive")
        if order_type is OrderType.LIMIT and price is None:
            raise ValueError("limit orders require a price")

    def register_callback(self, event: str, callback: Callable[[OrderRecord], Awaitable[None] | None]) -> None:
        self._callbacks.setdefault(event, []).append(callback)

    async def _emit(self, event: str, order: OrderRecord) -> None:
        callbacks = self._callbacks.get(event, [])
        if not callbacks:
            return
        await asyncio.gather(
            *(self._run_callback(callback, order) for callback in callbacks),
            return_exceptions=True,
        )

    async def _run_callback(self, callback: Callable[[OrderRecord], Awaitable[None] | None], order: OrderRecord) -> None:
        try:
            result = callback(order)
            if inspect.isawaitable(result):
                await result
        except Exception:
            return

    async def create_limit_order(
        self,
        *,
        symbol: str,
        side: Side,
        order_type: OrderType,
        quantity: float,
        price: float,
        client_order_id: str | None = None,
        leverage: float = 1.0,
    ) -> OrderRecord:
        self._validate_order(quantity=quantity, price=price, leverage=leverage, order_type=order_type)
        order = OrderRecord(
            uuid=str(uuid.uuid4()),
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            remaining_quantity=quantity,
            price=price,
            leverage=leverage,
            client_order_id=client_order_id or str(uuid.uuid4()),
            created_at=self._timestamp(),
        )
        self._orders_by_uuid[order.uuid] = order
        if order.client_order_id is not None:
            self._orders_by_client_id[order.client_order_id] = order
        await self._emit("on_create", order)
        return order

    async def create_market_order(
        self,
        *,
        symbol: str,
        side: Side,
        order_type: OrderType,
        quantity: float,
        client_order_id: str | None = None,
        leverage: float = 1.0,
    ) -> OrderRecord:
        self._validate_order(quantity=quantity, price=None, leverage=leverage, order_type=order_type)
        order = OrderRecord(
            uuid=str(uuid.uuid4()),
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            remaining_quantity=quantity,
            price=None,
            leverage=leverage,
            client_order_id=client_order_id or str(uuid.uuid4()),
            created_at=self._timestamp(),
        )
        self._orders_by_uuid[order.uuid] = order
        if order.client_order_id is not None:
            self._orders_by_client_id[order.client_order_id] = order
        await self._emit("on_create", order)
        return order

    async def place_limit(self, *, symbol: str, side: Side, quantity: float, price: float, client_order_id: str | None = None, leverage: float = 1.0) -> OrderRecord:
        return await self.create_limit_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=price,
            client_order_id=client_order_id,
            leverage=leverage,
        )

    async def place_market(self, *, symbol: str, side: Side, quantity: float, client_order_id: str | None = None, leverage: float = 1.0) -> OrderRecord:
        return await self.create_market_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            client_order_id=client_order_id,
            leverage=leverage,
        )

    async def cancel_order(self, uuid: str) -> OrderRecord | None:
        order = self._orders_by_uuid.get(uuid)
        if order is None:
            return None
        order.status = OrderStatus.CANCEL_REQUESTED
        order.last_update = self._timestamp()
        await self._emit("on_cancel", order)
        return order

    async def replace_order(self, uuid: str, *, price: float | None = None, quantity: float | None = None) -> OrderRecord | None:
        order = self._orders_by_uuid.get(uuid)
        if order is None:
            return None
        if price is not None:
            order.price = price
        if quantity is not None:
            self._validate_order(quantity=quantity, price=order.price if price is None else price, leverage=order.leverage, order_type=order.order_type)
            order.quantity = quantity
            order.remaining_quantity = max(quantity - order.filled_quantity, 0.0)
        order.last_update = self._timestamp()
        return order

    async def handle_fill(self, order_uuid: str, quantity: float, price: float, fees: float) -> OrderRecord | None:
        order = self._orders_by_uuid.get(order_uuid)
        if order is None:
            return None
        if quantity <= 0:
            raise ValueError("filled quantity must be positive")
        order.filled_quantity += quantity
        order.remaining_quantity = max(order.quantity - order.filled_quantity, 0.0)
        previous_notional = order.filled_quantity - quantity
        previous_notional *= order.average_fill_price or 0.0
        new_notional = previous_notional + (quantity * price)
        new_filled_quantity = order.filled_quantity
        order.average_fill_price = new_notional / new_filled_quantity if new_filled_quantity else None
        order.fees += fees
        order.filled_at = self._timestamp()
        if order.remaining_quantity <= 0:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
        order.last_update = self._timestamp()
        order.fills.append(FillRecord(fill_id=str(uuid.uuid4()), filled_quantity=quantity, fill_price=price, fees=fees, timestamp=self._timestamp()))
        await self._emit("on_fill", order)
        return order

    async def handle_cancel(self, uuid: str) -> OrderRecord | None:
        order = self._orders_by_uuid.get(uuid)
        if order is None:
            return None
        order.status = OrderStatus.CANCELLED
        order.cancelled_at = self._timestamp()
        order.last_update = self._timestamp()
        await self._emit("on_cancel", order)
        return order

    async def handle_reject(self, uuid: str) -> OrderRecord | None:
        order = self._orders_by_uuid.get(uuid)
        if order is None:
            return None
        order.status = OrderStatus.REJECTED
        order.last_update = self._timestamp()
        await self._emit("on_reject", order)
        return order

    async def handle_open(self, uuid: str) -> OrderRecord | None:
        order = self._orders_by_uuid.get(uuid)
        if order is None:
            return None
        order.status = OrderStatus.OPEN
        order.acknowledged_at = self._timestamp()
        order.last_update = self._timestamp()
        await self._emit("on_open", order)
        return order

    async def handle_order_update(self, uuid: str, *, status: OrderStatus | None = None, exchange_order_id: str | None = None) -> OrderRecord | None:
        order = self._orders_by_uuid.get(uuid)
        if order is None:
            return None
        if status is not None:
            order.status = status
        if exchange_order_id is not None:
            order.exchange_order_id = exchange_order_id
            self._orders_by_exchange_id[exchange_order_id] = order
        order.last_update = self._timestamp()
        return order

    async def sync_with_exchange(self) -> list[OrderRecord]:
        return list(self._orders_by_uuid.values())

    async def recover_after_restart(self) -> list[OrderRecord]:
        return list(self._orders_by_uuid.values())

    def get(self, uuid: str) -> OrderRecord | None:
        return self._orders_by_uuid.get(uuid)

    def get_by_exchange_id(self, exchange_order_id: str) -> OrderRecord | None:
        return self._orders_by_exchange_id.get(exchange_order_id)

    def get_by_client_id(self, client_order_id: str) -> OrderRecord | None:
        return self._orders_by_client_id.get(client_order_id)

    def list(self) -> list[OrderRecord]:
        return list(self._orders_by_uuid.values())
