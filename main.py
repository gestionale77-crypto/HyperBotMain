from __future__ import annotations

import asyncio
import os

from hyperbot.core.config import Settings
from hyperbot.exchange.hyperliquid import HyperLiquidClient
from hyperbot.exchange.websocket import HyperLiquidWebSocketClient


async def main() -> None:
    settings = Settings()
    client = HyperLiquidClient(settings)
    ws = HyperLiquidWebSocketClient(settings.websocket_base_url)

    await client.connect()
    print("Connected ✔")

    await ws.connect()
    await ws.subscribe("trades", {"symbol": "BTC"})
    print("Websocket ✔")

    for _ in range(3):
        await asyncio.sleep(1)
        await ws.send_ping()
        print("Price tick")

    order = await client.place_limit_order(symbol="BTC", side="buy", size=0.001, price=100000.0)
    print(f"Order placed: {order}")

    await asyncio.sleep(5)
    cancel_result = await client.cancel_order(client_id="demo-order")
    print(f"Order cancelled: {cancel_result}")

    await ws.disconnect()
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
