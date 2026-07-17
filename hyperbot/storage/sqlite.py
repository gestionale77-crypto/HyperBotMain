from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class SQLiteStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS system_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS grid_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    symbol TEXT NOT NULL,
                    center_price REAL NOT NULL,
                    realized_pnl REAL NOT NULL DEFAULT 0,
                    current_leverage REAL NOT NULL DEFAULT 3.0,
                    total_fills INTEGER NOT NULL DEFAULT 0,
                    last_recenter REAL NOT NULL DEFAULT 0,
                    last_compound REAL NOT NULL DEFAULT 0,
                    levels_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def add_event(self, event: str, payload: str) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO system_events (event, payload) VALUES (?, ?)",
                (event, payload),
            )

    def save_grid_state(self, symbol: str, state: dict[str, Any]) -> None:
        levels_json = json.dumps(state.get("levels", []), default=str)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO grid_state (
                    id, symbol, center_price, realized_pnl, current_leverage,
                    total_fills, last_recenter, last_compound, levels_json, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    symbol = excluded.symbol,
                    center_price = excluded.center_price,
                    realized_pnl = excluded.realized_pnl,
                    current_leverage = excluded.current_leverage,
                    total_fills = excluded.total_fills,
                    last_recenter = excluded.last_recenter,
                    last_compound = excluded.last_compound,
                    levels_json = excluded.levels_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    symbol,
                    state["center_price"],
                    state["realized_pnl"],
                    state["current_leverage"],
                    state.get("total_fills", 0),
                    state.get("last_recenter", 0.0),
                    state.get("last_compound", 0.0),
                    levels_json,
                ),
            )

    def load_grid_state(self, symbol: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM grid_state WHERE id = 1 AND symbol = ?",
            (symbol,),
        ).fetchone()
        if not row:
            return None

        levels = json.loads(row["levels_json"])
        return {
            "center_price": row["center_price"],
            "realized_pnl": row["realized_pnl"],
            "current_leverage": row["current_leverage"],
            "total_fills": row["total_fills"],
            "last_recenter": row["last_recenter"],
            "last_compound": row["last_compound"],
            "levels": levels,
        }

    def clear_grid_state(self) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM grid_state WHERE id = 1")
