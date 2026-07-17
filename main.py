from __future__ import annotations

import asyncio
import signal

from hyperbot.core.config import Settings
from hyperbot.exchange.hyperliquid import HyperLiquidClient
from hyperbot.exchange.ws_manager import HyperliquidWSManager
from hyperbot.risk.engine import RiskEngine, RiskLimits
from hyperbot.storage.sqlite import SQLiteStore
from hyperbot.strategy.smart_dense_grid import SmartDenseGridStrategy


async def main() -> None:
    settings = Settings()

    print("=" * 55)
    print(" HYPERBOT - Smart Dense Grid")
    print(f" Mode     : {'PAPER' if settings.grid_paper_mode else 'LIVE'}")
    print(f" Network  : {'TESTNET' if settings.api_testnet else 'MAINNET'}")
    print("=" * 55)

    client = HyperLiquidClient(settings)
    await client.connect()

    store = SQLiteStore(settings.sqlite_path)
    ws = HyperliquidWSManager(settings)
    risk = RiskEngine(RiskLimits(max_leverage=settings.grid_leverage_max, max_drawdown=0.12, max_exposure=0.30))
    strategy = SmartDenseGridStrategy(client=client, risk_engine=risk, settings=settings, symbol="ETH")
    strategy.set_store(store)
    strategy.ws = ws.client

    ws.on("l2Book", lambda payload: None)
    ws.on("user", strategy.on_user_event)
    ws.on("userEvents", strategy.on_user_event)
    ws.on("orderUpdates", strategy.on_user_event)

    ws.subscribe_l2book("ETH")
    if client.wallet_address:
        ws.subscribe_user_events(client.wallet_address)
        ws.subscribe_order_updates(client.wallet_address)

    await ws.start()

    try:
        loaded = await strategy.load_state()
        if loaded:
            print(f"State loaded → center={strategy.state.center_price:.2f} | levels={len(strategy.state.levels)} | pnl={strategy.state.realized_pnl:.4f}")
            await strategy.reconcile_orders()
        else:
            print("No previous state found → building fresh grid")
            await strategy.start()
    except Exception as exc:
        print(f"Startup issue: {exc}")
        await strategy.start()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _handle_signal() -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    try:
        while not stop_event.is_set():
            await asyncio.sleep(20)
            status = strategy.status()
            print(
                f"[Status] mid={status['mid']:.2f} | center={status['center']:.2f} | "
                f"orders={status['open_orders']}/{status['levels']} | "
                f"pnl={status['realized_pnl']} | kill={status['kill_switch']}"
            )
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nShutdown requested...")
    finally:
        await strategy.stop()
        await ws.disconnect()
        await client.disconnect()
        print("Bot stopped correctly.")


if __name__ == "__main__":
    asyncio.run(main())
