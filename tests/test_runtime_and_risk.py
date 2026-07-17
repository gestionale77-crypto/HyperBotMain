from __future__ import annotations

import pytest

from hyperbot.core.config import Settings
from hyperbot.engine.runtime import TradingRuntime
from hyperbot.risk.engine import RiskDecision, RiskEngine, RiskLimits


@pytest.mark.asyncio
async def test_runtime_start_stop_is_idempotent() -> None:
    runtime = TradingRuntime(Settings())

    await runtime.start()
    await runtime.start()
    assert runtime.is_running is True

    await runtime.stop()
    await runtime.stop()
    assert runtime.is_running is False


def test_risk_engine_rejects_with_reason() -> None:
    engine = RiskEngine(RiskLimits(max_exposure=0.2))
    decision = engine.can_trade(
        equity=100.0,
        exposure=0.3,
        leverage=1.0,
        drawdown=0.01,
        daily_loss=0.0,
        liquidation_distance=0.2,
    )

    assert decision.allowed is False
    assert decision.reason == "max_exposure"


def test_risk_engine_kill_switch_blocks_trading() -> None:
    engine = RiskEngine()
    engine.emergency_kill_switch()
    decision = engine.can_trade(
        equity=100.0,
        exposure=0.1,
        leverage=1.0,
        drawdown=0.01,
        daily_loss=0.0,
        liquidation_distance=0.2,
    )

    assert decision.allowed is False
    assert decision.reason == "kill_switch"
