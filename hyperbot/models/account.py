from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AccountSnapshot:
    equity: float
    available_balance: float
    margin_used: float
    leverage: float
