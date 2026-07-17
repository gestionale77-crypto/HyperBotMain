from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class SQLiteRepository:
    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database_path)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    uuid TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    exchange_id TEXT,
                    client_id TEXT,
                    status TEXT NOT NULL,
                    filled REAL NOT NULL DEFAULT 0,
                    remaining REAL NOT NULL DEFAULT 0,
                    fees REAL NOT NULL DEFAULT 0,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    size REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS balance (
                    account TEXT PRIMARY KEY,
                    equity REAL NOT NULL,
                    available REAL NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );
                """
            )

    def save_order(self, order: dict[str, Any]) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO orders (uuid, timestamp, exchange_id, client_id, status, filled, remaining, fees, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uuid) DO UPDATE SET
                    timestamp = excluded.timestamp,
                    exchange_id = excluded.exchange_id,
                    client_id = excluded.client_id,
                    status = excluded.status,
                    filled = excluded.filled,
                    remaining = excluded.remaining,
                    fees = excluded.fees,
                    metadata = excluded.metadata
                """,
                (
                    order["uuid"],
                    order["timestamp"],
                    order.get("exchange_id"),
                    order.get("client_id"),
                    order["status"],
                    order.get("filled", 0.0),
                    order.get("remaining", 0.0),
                    order.get("fees", 0.0),
                    json.dumps(order.get("metadata", {})),
                ),
            )

    def get_orders(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT uuid, timestamp, exchange_id, client_id, status, filled, remaining, fees, metadata FROM orders"
        ).fetchall()
        return [
            {
                "uuid": row[0],
                "timestamp": row[1],
                "exchange_id": row[2],
                "client_id": row[3],
                "status": row[4],
                "filled": row[5],
                "remaining": row[6],
                "fees": row[7],
                "metadata": json.loads(row[8]),
            }
            for row in rows
        ]
