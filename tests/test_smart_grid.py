from __future__ import annotations

import pytest

from hyperbot.core.config import Settings
from hyperbot.risk.engine import RiskEngine, RiskLimits
from hyperbot.strategy.smart_dense_grid import SmartDenseGridStrategy


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
