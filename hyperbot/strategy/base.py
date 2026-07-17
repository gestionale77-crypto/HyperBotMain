from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Strategy(ABC):
    @abstractmethod
    async def on_market_data(self, market_data: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def on_signal(self, signal: dict[str, Any]) -> None:
        raise NotImplementedError
