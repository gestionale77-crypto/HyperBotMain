from __future__ import annotations

import pytest

from hyperbot.core.config import Settings
from hyperbot.exchange.websocket import HyperLiquidWebSocketClient
from hyperbot.risk.engine import RiskEngine, RiskLimits
from hyperbot.storage.sqlite import SQLiteStore
from hyperbot.strategy.smart_dense_grid import GridLevel, SmartDenseGridStrategy


class DummyClient:
    def __init__(self) -> None:
        self._info = None


def test_grid_levels_are_built_with_expected_shape() -> None:
    settings = Settings(grid_levels=8, grid_range_pct=0.04, grid_density_power=1.5, grid_base_size=0.01)
    strategy = SmartDenseGridStrategy(client=DummyClient(), risk_engine=RiskEngine(RiskLimits()), settings=settings, symbol="ETH")

    levels = strategy._calculate_levels(1000.0)

    assert len(levels) == 8
    assert levels[0].price < 1000.0
    assert levels[-1].price > 1000.0


def test_risk_engine_rejects_large_orders() -> None:
    engine = RiskEngine(RiskLimits(max_position_size=0.1))
    engine.update_account_state(equity=1000.0, exposure=50.0, open_orders=1)

    decision = engine.can_place_order(side="buy", size=0.2, price=100.0, current_leverage=2.0, symbol="ETH")

    assert decision.allowed is False
    assert decision.reason == "max_position_size"


@pytest.mark.asyncio
async def test_fill_processing_updates_realized_pnl_and_state() -> None:
    settings = Settings(grid_compound=True, grid_paper_mode=True, grid_base_size=0.01)
    strategy = SmartDenseGridStrategy(client=DummyClient(), risk_engine=RiskEngine(RiskLimits()), settings=settings, symbol="ETH")
    strategy.state.center_price = 1000.0
    strategy._last_mid = 1000.0
    strategy.state.levels = [
        type("Level", (), {"price": 1000.0, "size": 0.01, "side": "buy", "order_id": 1, "filled": False})()
    ]

    await strategy._process_fill({"coin": "ETH", "side": "B", "px": 1000.0, "sz": 0.01, "closedPnl": 0.01, "oid": 1})

    assert strategy.state.realized_pnl == pytest.approx(0.01)
    assert strategy.state.total_fills == 1
    assert strategy.state.last_fill_time > 0


def test_websocket_supports_l2book_and_user_event_subscriptions() -> None:
    client = HyperLiquidWebSocketClient("wss://example.test/ws")

    client.on("l2Book", lambda payload: None)
    client.on("user", lambda payload: None)
    client.on("userEvents", lambda payload: None)
    client.on("orderUpdates", lambda payload: None)

    client.subscribe_l2book("ETH")
    client.subscribe_user_events("0xabc")
    client.subscribe_order_updates("0xabc")

    assert client.subscription_count() == 3


@pytest.mark.asyncio
async def test_grid_state_can_be_saved_and_restored(tmp_path) -> None:
    db_path = tmp_path / "grid.sqlite"
    settings = Settings(grid_paper_mode=True)
    strategy = SmartDenseGridStrategy(client=DummyClient(), risk_engine=RiskEngine(RiskLimits()), settings=settings, symbol="ETH")
    strategy.set_store(SQLiteStore(str(db_path)))
    strategy.state.center_price = 1010.0
    strategy.state.realized_pnl = 0.25
    strategy.state.current_leverage = 4.0
    strategy.state.total_fills = 2
    strategy.state.levels = [GridLevel(price=1000.0, size=0.01, side="buy", order_id=111, filled=False)]

    await strategy.save_state(force=True)

    restored = SmartDenseGridStrategy(client=DummyClient(), risk_engine=RiskEngine(RiskLimits()), settings=settings, symbol="ETH")
    restored.set_store(SQLiteStore(str(db_path)))
    loaded = await restored.load_state()

    assert loaded is True
    assert restored.state.center_price == 1010.0
    assert restored.state.realized_pnl == 0.25
    assert restored.state.total_fills == 2
    assert len(restored.state.levels) == 1
