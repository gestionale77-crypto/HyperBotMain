from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hyperbot.core.logging import StructuredLogMixin


@dataclass(slots=True)
class OrderRequest:
    symbol: str
    side: str
    qty: float
    order_type: str = "limit"
    reduce_only: bool = False
    post_only: bool = False
    time_in_force: str = "GTC"


class OrderManager(StructuredLogMixin):
    def __init__(self) -> None:
        self.orders: dict[str, OrderRequest] = {}

    def submit(self, request: OrderRequest) -> OrderRequest:
        self.orders[request.symbol] = request
        self.log_event("execution.submit", symbol=request.symbol, side=request.side)
        return request

    def cancel(self, symbol: str) -> None:
        self.orders.pop(symbol, None)
        self.log_event("execution.cancel", symbol=symbol)
