from __future__ import annotations

from hyperbot.core.config import Settings
from hyperbot.exchange.ws_manager import HyperliquidWSManager


def test_ws_manager_registers_handlers_and_subscriptions() -> None:
    settings = Settings(websocket_base_url="wss://example.test/ws")
    manager = HyperliquidWSManager(settings)

    manager.on("l2Book", lambda payload: None)
    manager.subscribe_l2book("ETH")
    manager.subscribe_user_events("0xabc")

    assert manager.client.subscription_count() == 2
