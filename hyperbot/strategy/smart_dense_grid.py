from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from hyperbot.core.config import Settings
from hyperbot.core.logging import StructuredLogMixin
from hyperbot.exchange.hyperliquid import HyperLiquidClient
from hyperbot.risk.engine import RiskEngine
from hyperbot.storage.sqlite import SQLiteStore
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
    total_fills: int = 0
    last_fill_time: float = 0.0


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
        self.store: SQLiteStore | None = None
        self._last_save: float = 0.0
        self._save_interval: float = 30.0
        self._last_compound: float = 0.0

    def set_store(self, store: SQLiteStore) -> None:
        self.store = store

    def _state_to_dict(self) -> dict[str, Any]:
        levels_data: list[dict[str, Any]] = []
        for level in self.state.levels:
            levels_data.append(
                {
                    "price": level.price,
                    "size": level.size,
                    "side": level.side,
                    "order_id": level.order_id,
                    "filled": level.filled,
                }
            )

        return {
            "center_price": self.state.center_price,
            "realized_pnl": self.state.realized_pnl,
            "current_leverage": self.state.current_leverage,
            "total_fills": getattr(self.state, "total_fills", 0),
            "last_recenter": self.state.last_recenter,
            "last_compound": getattr(self, "_last_compound", 0.0),
            "levels": levels_data,
        }

    async def save_state(self, force: bool = False) -> None:
        if not self.store:
            return

        now = time.time()
        if not force and (now - self._last_save) < self._save_interval:
            return

        try:
            self.store.save_grid_state(self.symbol, self._state_to_dict())
            self._last_save = now
            self.log_event("grid.state_saved", levels=len(self.state.levels), pnl=self.state.realized_pnl)
        except Exception as exc:
            self.log_event("grid.state_save_error", error=str(exc))

    async def load_state(self) -> bool:
        if not self.store:
            return False

        data = self.store.load_grid_state(self.symbol)
        if not data or data["center_price"] <= 0:
            return False

        try:
            self.state.center_price = data["center_price"]
            self.state.realized_pnl = data["realized_pnl"]
            self.state.current_leverage = data["current_leverage"]
            self.state.last_recenter = data.get("last_recenter", 0.0)
            self.state.total_fills = data.get("total_fills", 0)
            self._last_compound = data.get("last_compound", 0.0)
            self.state.levels = []
            for item in data.get("levels", []):
                self.state.levels.append(
                    GridLevel(
                        price=item["price"],
                        size=item["size"],
                        side=item["side"],
                        order_id=item.get("order_id"),
                        filled=item.get("filled", False),
                    )
                )
            self.log_event(
                "grid.state_loaded",
                center=self.state.center_price,
                levels=len(self.state.levels),
                pnl=self.state.realized_pnl,
            )
            return True
        except Exception as exc:
            self.log_event("grid.state_load_error", error=str(exc))
            return False

    async def reconcile_orders(self) -> None:
        if self.settings.grid_paper_mode:
            self.log_event("grid.reconcile_skip", reason="paper_mode")
            return

        try:
            open_orders = await self.client.get_open_orders()
            live_oids = {order["oid"] for order in open_orders if order.get("coin") == self.symbol}
        except Exception as exc:
            self.log_event("grid.reconcile_error", error=str(exc))
            return

        re_placed = 0
        for level in self.state.levels:
            if level.filled or level.order_id is None:
                continue
            if level.order_id not in live_oids:
                self.log_event("grid.order_missing", oid=level.order_id, price=level.price)
                level.order_id = None
                decision = self.risk.can_place_order(
                    side=level.side,
                    size=level.size,
                    price=level.price,
                    current_leverage=self.state.current_leverage,
                    symbol=self.symbol,
                )
                if not decision.allowed:
                    continue
                try:
                    result = await self.client.place_limit_order(
                        symbol=self.symbol,
                        side=level.side,
                        size=level.size,
                        price=level.price,
                        tif="Gtc",
                    )
                    if result.get("status") == "ok":
                        status = result["response"]["data"]["statuses"][0]
                        if "resting" in status:
                            level.order_id = status["resting"]["oid"]
                            re_placed += 1
                except Exception as exc:
                    self.log_event("grid.replace_error", error=str(exc))

        self.log_event("grid.reconciled", re_placed=re_placed, total_levels=len(self.state.levels))
        await self.save_state(force=True)

    async def force_rebuild(self) -> None:
        self.log_event("grid.force_rebuild")
        await self.cancel_all_levels()
        mid = self._last_mid or await self._get_mid_price()
        await self.build_grid(mid)
        await self.save_state(force=True)

    def status(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "paper": self.settings.grid_paper_mode,
            "center": self.state.center_price,
            "mid": self._last_mid,
            "levels": len(self.state.levels),
            "open_orders": sum(1 for level in self.state.levels if level.order_id is not None),
            "filled": sum(1 for level in self.state.levels if level.filled),
            "realized_pnl": round(self.state.realized_pnl, 4),
            "leverage": self.state.current_leverage,
            "kill_switch": not self.risk.trading_enabled,
        }

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
        await self.save_state(force=True)

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
                await self.save_state(force=True)
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
                    await self.save_state(force=True)

    async def on_user_event(self, data: dict[str, Any]) -> None:
        fills = data.get("fills") or data.get("data", {}).get("fills") or []
        if not fills and isinstance(data, list):
            fills = data
        for fill in fills:
            await self._process_fill(fill)

    async def _process_fill(self, fill: dict[str, Any]) -> None:
        try:
            coin = fill.get("coin") or fill.get("s")
            if coin and coin != self.symbol:
                return

            side = fill.get("side")
            px = float(fill.get("px") or fill.get("price") or 0)
            sz = float(fill.get("sz") or fill.get("size") or 0)
            closed_pnl = float(fill.get("closedPnl") or fill.get("closed_pnl") or 0)
            oid = fill.get("oid")

            if px <= 0 or sz <= 0:
                return

            is_buy = side in ("B", "buy", "Buy", "b")
            self.log_event(
                "grid.fill_received",
                side="buy" if is_buy else "sell",
                price=px,
                size=sz,
                closed_pnl=closed_pnl,
                oid=oid,
            )

            if closed_pnl != 0:
                self.state.realized_pnl += closed_pnl
                self.log_event("grid.pnl_updated", realized_pnl=self.state.realized_pnl)

            self.state.total_fills += 1
            self.state.last_fill_time = time.time()

            matched = False
            for level in self.state.levels:
                if level.order_id and oid and level.order_id == oid:
                    level.filled = True
                    level.order_id = None
                    matched = True
                    break
                if abs(level.price - px) / px < 0.001 and not level.filled:
                    level.filled = True
                    level.order_id = None
                    matched = True
                    break

            if matched:
                await self._replace_filled_level(px, is_buy)

            if self.settings.grid_compound and self.state.realized_pnl > 0:
                await self._maybe_compound()

            await self.save_state()
        except Exception as exc:
            self.log_event("grid.fill_error", error=str(exc), fill=str(fill)[:200])

    async def _replace_filled_level(self, filled_price: float, was_buy: bool) -> None:
        mid = self._last_mid or self.state.center_price
        if mid <= 0:
            return

        offset_pct = abs(filled_price - mid) / mid
        offset_pct = max(offset_pct, 0.003)

        if was_buy:
            new_price = filled_price * (1 + offset_pct * 0.8)
            new_side = "sell"
        else:
            new_price = filled_price * (1 - offset_pct * 0.8)
            new_side = "buy"

        base_size = self.settings.grid_base_size
        if self.settings.grid_compound and self.state.realized_pnl > 0:
            base_size *= 1.0 + min(self.state.realized_pnl * 0.08, 0.4)

        new_level = GridLevel(price=round(new_price, 2), size=round(base_size, 5), side=new_side)

        decision = self.risk.can_place_order(
            side=new_side,
            size=new_level.size,
            price=new_level.price,
            current_leverage=self.state.current_leverage,
            symbol=self.symbol,
        )
        if not decision.allowed:
            self.log_event("grid.replace_blocked", reason=decision.reason)
            return

        if self.settings.grid_paper_mode:
            new_level.order_id = int(time.time() * 1000) + abs(hash(new_level.price)) % 100000
            self.log_event("grid.paper_replace", side=new_side, price=new_level.price, size=new_level.size)
        else:
            try:
                result = await self.client.place_limit_order(
                    symbol=self.symbol,
                    side=new_side,
                    size=new_level.size,
                    price=new_level.price,
                    tif="Gtc",
                )
                if result.get("status") == "ok":
                    statuses = result.get("response", {}).get("data", {}).get("statuses", [])
                    if statuses:
                        status = statuses[0]
                        if "resting" in status:
                            new_level.order_id = status["resting"]["oid"]
            except Exception as exc:
                self.log_event("grid.replace_error", error=str(exc))
                return

        self.state.levels.append(new_level)
        self.state.levels.sort(key=lambda item: item.price)
        await self.save_state()

    async def _maybe_compound(self) -> None:
        if self.state.realized_pnl < 0.008:
            return

        now = time.time()
        if now - getattr(self, "_last_compound", 0) < 600:
            return

        self._last_compound = now
        self.log_event(
            "grid.compound_triggered",
            realized_pnl=self.state.realized_pnl,
            old_base_size=self.settings.grid_base_size,
        )

        multiplier = 1.0 + min(self.state.realized_pnl * 0.15, 0.40)
        self.settings.grid_base_size = round(self.settings.grid_base_size * multiplier, 5)
        await self.cancel_all_levels()
        await self.build_grid(self._last_mid or self.state.center_price)
        await self.save_state(force=True)

    async def on_market_data(self, market_data: dict[str, Any]) -> None:
        await self.check_recenter()

    async def on_signal(self, signal: dict[str, Any]) -> None:
        return None

    async def start(self) -> None:
        self._running = True
        loaded = await self.load_state()
        if loaded and len(self.state.levels) > 0:
            self.log_event("grid.resuming", levels=len(self.state.levels))
            await self.reconcile_orders()
        else:
            mid = await self._get_mid_price()
            await self.build_grid(mid)
        self.log_event("grid.started", **self.status())

    async def stop(self) -> None:
        self._running = False
        await self.save_state(force=True)
        self.log_event("grid.stopped", **self.status())
