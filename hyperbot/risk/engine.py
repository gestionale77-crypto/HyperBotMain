from __future__ import annotations

from dataclasses import dataclass

from hyperbot.core.logging import StructuredLogMixin


@dataclass(slots=True)
class RiskLimits:
    max_leverage: float = 5.0
    max_drawdown: float = 0.10
    max_exposure: float = 0.25
    daily_loss_limit: float = 0.05
    liquidation_distance: float = 0.05
    max_position_size: float = float("inf")


@dataclass(slots=True)
class RiskDecision:
    allowed: bool
    reason: str | None = None
    suggested_size: float | None = None


class RiskEngine(StructuredLogMixin):
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()
        self._kill_switch = False
        self._peak_equity: float | None = None
        self._daily_pnl: float = 0.0
        self._account_state: dict[str, float] = {
            "equity": 0.0,
            "exposure": 0.0,
            "open_orders": 0.0,
            "position_size": 0.0,
        }

    @property
    def trading_enabled(self) -> bool:
        return not self._kill_switch

    def can_trade(
        self,
        *,
        equity: float,
        exposure: float,
        leverage: float,
        drawdown: float,
        daily_loss: float,
        liquidation_distance: float,
    ) -> RiskDecision:
        if self._kill_switch:
            self.log_event("risk.reject", reason="kill_switch")
            return RiskDecision(allowed=False, reason="kill_switch")
        if equity <= 0:
            self.log_event("risk.reject", reason="non_positive_equity", equity=equity)
            return RiskDecision(allowed=False, reason="non_positive_equity")
        if exposure > self.limits.max_exposure:
            self.log_event("risk.reject", reason="max_exposure", exposure=exposure, limit=self.limits.max_exposure)
            return RiskDecision(allowed=False, reason="max_exposure")
        if leverage > self.limits.max_leverage:
            self.log_event("risk.reject", reason="max_leverage", leverage=leverage, limit=self.limits.max_leverage)
            return RiskDecision(allowed=False, reason="max_leverage")
        if drawdown > self.limits.max_drawdown:
            self.log_event("risk.reject", reason="max_drawdown", drawdown=drawdown, limit=self.limits.max_drawdown)
            return RiskDecision(allowed=False, reason="max_drawdown")
        if daily_loss < -self.limits.daily_loss_limit:
            self.log_event("risk.reject", reason="daily_loss_limit", daily_loss=daily_loss, limit=self.limits.daily_loss_limit)
            return RiskDecision(allowed=False, reason="daily_loss_limit")
        if liquidation_distance < self.limits.liquidation_distance:
            self.log_event("risk.reject", reason="liquidation_distance", liquidation_distance=liquidation_distance, limit=self.limits.liquidation_distance)
            return RiskDecision(allowed=False, reason="liquidation_distance")
        return RiskDecision(allowed=True)

    def update_equity(self, equity: float) -> None:
        if self._peak_equity is None or equity > self._peak_equity:
            self._peak_equity = equity
        self._daily_pnl = 0.0 if self._peak_equity is None else self._daily_pnl

    def update_account_state(
        self,
        *,
        equity: float,
        exposure: float,
        open_orders: float | int = 0,
        position_size: float | None = None,
    ) -> None:
        self._account_state = {
            "equity": float(equity),
            "exposure": float(exposure),
            "open_orders": float(open_orders),
            "position_size": float(position_size if position_size is not None else self._account_state.get("position_size", 0.0)),
        }
        self.update_equity(float(equity))

    def can_place_order(
        self,
        *,
        side: str,
        size: float,
        price: float,
        current_leverage: float,
        symbol: str,
    ) -> RiskDecision:
        if self._kill_switch:
            return RiskDecision(allowed=False, reason="kill_switch")

        max_position_size = getattr(self.limits, "max_position_size", float("inf"))
        position_size = self._account_state.get("position_size", 0.0)
        if size + position_size > max_position_size:
            return RiskDecision(allowed=False, reason="max_position_size")

        if price <= 0:
            return RiskDecision(allowed=False, reason="invalid_price")

        decision = self.can_trade(
            equity=self._account_state.get("equity", 0.0),
            exposure=self._account_state.get("exposure", 0.0),
            leverage=current_leverage,
            drawdown=0.0,
            daily_loss=self._daily_pnl,
            liquidation_distance=0.2,
        )
        if not decision.allowed:
            return decision
        return RiskDecision(allowed=True, suggested_size=min(size, max_position_size - position_size))

    def update_daily_pnl(self, pnl: float) -> None:
        self._daily_pnl += pnl

    def emergency_kill_switch(self) -> RiskDecision:
        self._kill_switch = True
        self.log_event("risk.kill_switch", status="triggered")
        return RiskDecision(allowed=False, reason="kill_switch")
