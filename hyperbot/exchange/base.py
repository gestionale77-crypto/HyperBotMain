from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ExchangeClient(ABC):
    @abstractmethod
    async def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def subscribe_market_data(self, symbols: list[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_account_balance(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_positions(self) -> list[dict[str, Any]]:
        raise NotImplementedError
