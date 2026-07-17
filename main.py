from __future__ import annotations

import asyncio
import json

from hyperbot.core.config import Settings
from hyperbot.exchange.hyperliquid import HyperLiquidClient


async def main() -> None:
    settings = Settings()
    client = HyperLiquidClient(settings)

    print("Connecting...")
    await client.connect()
    print(f"Connected ✔  Address: {client.wallet_address}")
    print(f"Network: {'TESTNET' if settings.api_testnet else 'MAINNET'}")

    balance = await client.get_account_balance()
    print("\n=== Account State ===")
    print(json.dumps(balance.get("marginSummary", {}), indent=2))

    positions = await client.get_positions()
    print(f"\nOpen positions: {len(positions)}")

    print("\nPlacing test limit order (ETH)...")
    order = await client.place_limit_order(
        symbol="ETH",
        side="buy",
        size=0.01,
        price=1000.0,
        reduce_only=False,
        tif="Gtc",
    )
    print(json.dumps(order, indent=2))

    if order.get("status") == "ok":
        statuses = order.get("response", {}).get("data", {}).get("statuses", [])
        for status in statuses:
            if "resting" in status:
                oid = status["resting"]["oid"]
                print(f"\nCancelling order {oid}...")
                cancel = await client.cancel_order(symbol="ETH", oid=oid)
                print(json.dumps(cancel, indent=2))
                break

    await client.disconnect()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
