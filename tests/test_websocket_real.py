from __future__ import annotations

from hyperbot.exchange.websocket import HyperLiquidWebSocketClient


def test_websocket_subscriptions_are_reconstructed() -> None:
    client = HyperLiquidWebSocketClient("wss://example.test/ws", reconnect_delay=0.1, max_reconnect_delay=0.2)
    client.add_subscription("trades", {"symbol": "BTC"})
    client.add_subscription("orderbook", {"symbol": "BTC"})

    assert client.subscription_count() == 2

    restored = client.get_subscription_snapshot()

    assert restored[0]["channel"] == "trades"
    assert restored[1]["channel"] == "orderbook"
