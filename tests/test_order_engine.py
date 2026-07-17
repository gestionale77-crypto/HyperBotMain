from __future__ import annotations

import asyncio

import pytest

from hyperbot.exchange.manager import OrderManager, OrderStatus, OrderType, Side


@pytest.mark.asyncio
async def test_order_engine_lifecycle() -> None:
    manager = OrderManager()

    order = await manager.create_limit_order(
        symbol="BTC",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=0.001,
        price=100000.0,
        client_order_id="client-1",
    )

    assert order.status is OrderStatus.CREATED
    assert order.client_order_id == "client-1"

    await manager.handle_open(order.uuid)
    assert order.status is OrderStatus.OPEN

    await manager.handle_fill(order.uuid, 0.001, 100000.0, 0.0)
    assert order.status is OrderStatus.FILLED
    assert order.filled_quantity == 0.001


@pytest.mark.asyncio
async def test_order_engine_uses_weighted_average_fill_price() -> None:
    manager = OrderManager()

    order = await manager.create_limit_order(
        symbol="BTC",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10.0,
        price=100000.0,
    )

    await manager.handle_fill(order.uuid, 1.0, 100.0, 0.0)
    await manager.handle_fill(order.uuid, 9.0, 110.0, 0.0)

    assert order.average_fill_price == 109.0


@pytest.mark.asyncio
async def test_replace_order_preserves_filled_quantity() -> None:
    manager = OrderManager()

    order = await manager.create_limit_order(
        symbol="BTC",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10.0,
        price=100000.0,
    )

    await manager.handle_fill(order.uuid, 6.0, 100000.0, 0.0)
    await manager.replace_order(order.uuid, quantity=20.0)

    assert order.filled_quantity == 6.0
    assert order.remaining_quantity == 14.0
