from __future__ import annotations

from hyperbot.core.config import Settings
from hyperbot.exchange.hyperliquid import HyperLiquidClient
from hyperbot.exchange.websocket import HyperLiquidWebSocketClient


def test_authentication_derives_wallet_address() -> None:
    settings = Settings(api_private_key="0x" + "1" * 64)
    client = HyperLiquidClient(settings)

    client.authenticate()

    assert client.wallet_address is not None
    assert client.wallet_address.startswith("0x")


def test_websocket_backoff_grows_exponentially() -> None:
    client = HyperLiquidWebSocketClient("wss://example.test/ws", reconnect_delay=0.1, max_reconnect_delay=0.4)

    assert client.get_backoff_delay(1) == 0.1
    assert client.get_backoff_delay(2) == 0.2
    assert client.get_backoff_delay(3) == 0.4


def test_authentication_falls_back_in_development() -> None:
    settings = Settings(api_private_key=None, environment="development")
    client = HyperLiquidClient(settings)

    client.authenticate()

    assert client.wallet_address is not None
    assert client.wallet_address.startswith("0x")
