from __future__ import annotations

from pathlib import Path

from hyperbot.storage.repository import SQLiteRepository


def test_repository_persists_orders(tmp_path: Path) -> None:
    db_path = tmp_path / "orders.db"
    repo = SQLiteRepository(str(db_path))

    repo.save_order(
        {
            "uuid": "order-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "status": "pending",
            "filled": 0.0,
            "remaining": 1.0,
            "fees": 0.0,
            "metadata": {"symbol": "BTC"},
        }
    )

    orders = repo.get_orders()

    assert len(orders) == 1
    assert orders[0]["uuid"] == "order-1"
    assert orders[0]["status"] == "pending"
