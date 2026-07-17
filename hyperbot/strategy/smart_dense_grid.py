from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from hyperbot.core.config import Settings
from hyperbot.core.logging import StructuredLogMixin
from hyperbot.exchange.hyperliquid import HyperLiquidClient
from hyperbot.risk.engine import RiskEngine
from hyperbot.strategy.base import Strategy


@dataclass
class GridLevel:
    price: float
    size: float
    side: str
    order_id: int | None = None
    filled: bool = False


@dataclass
class GridState:
    center_price: float
    levels: list[GridLevel] = field(default_factory=list)
    last_recenter: float = 0.0
    realized_pnl: float = 0.0
    current_leverage: float = 3.0


class SmartDenseGridStrategy(Strategy, StructuredLogMixin):
    def __init__(
        self,
        client: HyperLiquidClient,
        risk_engine: RiskEngine,
        settings: Settings,
        symbol: str = "ETH",
    ) -> None:
        self.client = client
        self.risk = risk_engine
        self.settings = settings
        self.symbol = symbol
        self.state = GridState(center_price=0.0)
        self._running = False
        self._last_mid = 0.0
        self.ws: Any | None = None

    def _calculate_levels(self, mid: float) -> list[GridLevel]:
        levels: list[GridLevel] = []
        half = self.settings.grid_levels // 2
        range_pct = self.settings.grid_range_pct
        power = self.settings.grid_density_power
        size_power = self.settings.grid_size_power
        base_size = self.settings.grid_base_size

        if self.settings.grid_compound and self.state.realized_pnl > 0:
            base_size *= 1.0 + min(self.state.realized_pnl * 0.1, 0.5)

        for i in range(1, half + 1):
            t = i / half
            density_factor = t**power
            dist = range_pct * density_factor
            size_mult = 1.0 + (t**size_power) * 1.5
            size = round(base_size * size_mult, 5)
            buy_price = mid * (1 - dist)
            sell_price = mid * (1 + dist)
            levels.append(GridLevel(price=round(buy_price, 2), size=size, side="buy"))
            levels.append(GridLevel(price=round(sell_price, 2), size=size, side="sell"))

        levels.sort(key=lambda item: item.price)
        return levels

    async def _get_mid_price(self) -> float:
        if self.ws is not None:
            mid_price = getattr(self.ws, "mid_price", None)
            if isinstance(mid_price, (int, float)) and float(mid_price) > 0:
                return float(mid_price)
        if self.client._info is not None:
            all_mids = self.client._info.all_mids()
            mid = float(all_mids.get(self.symbol, 0))
            if mid > 0:
                return mid
        raise ValueError(f"Invalid mid price for {self.symbol}")

    async def _estimate_volatility(self) -> float:
        return 0.025

    def _calculate_leverage(self, volatility: float) -> float:
        vol_clamped = max(0.008, min(volatility, 0.08))
        leverage = self.settings.grid_leverage_max - (
            (vol_clamped - 0.008) / (0.08 - 0.008)
        ) * (self.settings.grid_leverage_max - self.settings.grid_leverage_min)
        return round(max(self.settings.grid_leverage_min, min(leverage, self.settings.grid_leverage_max)), 1)

    async def build_grid(self, mid: float | None = None) -> None:
        if mid is None:
            mid = await self._get_mid_price()

        self.state.center_price = mid
        self.state.levels = self._calculate_levels(mid)
        self.state.last_recenter = time.time()
        vol = await self._estimate_volatility()
        self.state.current_leverage = self._calculate_leverage(vol)
        self.log_event(
            "grid.built",
            center=mid,
            levels=len(self.state.levels),
            leverage=self.state.current_leverage,
            paper=self.settings.grid_paper_mode,
        )
        await self._place_all_levels()

    async def _place_all_levels(self) -> None:
        for level in self.state.levels:
            if level.order_id is not None:
                continue
            decision = self.risk.can_place_order(
                side=level.side,
                size=level.size,
                price=level.price,
                current_leverage=self.state.current_leverage,
                symbol=self.symbol,
            )
            if not decision.allowed:
                self.log_event("grid.risk_blocked", reason=decision.reason, price=level.price)
                continue

            size = decision.suggested_size or level.size
            if self.settings.grid_paper_mode:
                level.order_id = int(time.time() * 1000) + abs(hash(level.price)) % 100000
                self.log_event("grid.paper_order", side=level.side, price=level.price, size=size)
            else:
                try:
                    result = await self.client.place_limit_order(
                        symbol=self.symbol,
                        side=level.side,
                        size=size,
                        price=level.price,
                        tif="Gtc",
                    )
                    if result.get("status") == "ok":
                        statuses = result.get("response", {}).get("data", {}).get("statuses", [])
                        if statuses:
                            status = statuses[0]
                            if "resting" in status:
                                level.order_id = status["resting"]["oid"]
                except Exception as exc:
                    self.log_event("grid.order_error", error=str(exc))

    async def check_recenter(self) -> bool:
        mid = await self._get_mid_price()
        self._last_mid = mid
        if self.state.center_price <= 0:
            return False
        distance = abs(mid - self.state.center_price) / self.state.center_price
        now = time.time()
        if distance >= self.settings.grid_recenter_threshold:
            if now - self.state.last_recenter > self.settings.grid_recenter_cooldown:
                self.log_event("grid.recenter", old_center=self.state.center_price, new_mid=mid, distance=distance)
                await self.cancel_all_levels()
                await self.build_grid(mid)
                return True
        return False

    async def cancel_all_levels(self) -> None:
        for level in self.state.levels:
            if level.order_id is None:
                continue
            if self.settings.grid_paper_mode:
                level.order_id = None
            else:
                try:
                    await self.client.cancel_order(symbol=self.symbol, oid=level.order_id)
                except Exception:
                    pass
                level.order_id = None
        self.state.levels.clear()

    async def on_l2book(self, data: dict[str, Any]) -> None:
        mid = data.get("mid", 0.0)
        if mid <= 0:
            return
        self._last_mid = mid
        if self.state.center_price > 0:
            distance = abs(mid - self.state.center_price) / self.state.center_price
            if distance >= self.settings.grid_recenter_threshold:
                now = time.time()
                if now - self.state.last_recenter > self.settings.grid_recenter_cooldown:
                    self.log_event("grid.recenter_triggered", distance=distance)
                    await self.cancel_all_levels()
                    await self.build_grid(mid)

    async def on_market_data(self, market_data: dict[str, Any]) -> None:
        await self.check_recenter()

    async def on_signal(self, signal: dict[str, Any]) -> None:
        return None

    async def start(self) -> None:
        self._running = True
        mid = await self._get_mid_price()
        await self.build_grid(mid)
        self.log_event("grid.started", symbol=self.symbol, paper=self.settings.grid_paper_mode)

    async def stop(self) -> None:
        self._running = False
        await self.cancel_all_levels()
        self.log_event("grid.stopped")
