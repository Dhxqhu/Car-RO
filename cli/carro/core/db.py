"""Local SQLite store for repair orders + photo metadata."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from carro.config import DATA_DIR, load_config
from carro.core.models import RepairOrder, new_ro_id, now_iso


class LocalStore:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (DATA_DIR / "carro.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS repair_orders (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ro_updated ON repair_orders(updated DESC)"
            )

    def list_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM repair_orders").fetchall()
        return [r["id"] for r in rows]

    def list_orders(self, limit: int | None = None) -> list[RepairOrder]:
        sql = "SELECT data FROM repair_orders ORDER BY updated DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [RepairOrder.from_dict(json.loads(r["data"])) for r in rows]

    def get(self, ro_id: str) -> RepairOrder | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM repair_orders WHERE id = ?", (ro_id,)
            ).fetchone()
        if not row:
            return None
        return RepairOrder.from_dict(json.loads(row["data"]))

    def save(self, order: RepairOrder) -> RepairOrder:
        order.updated = now_iso()
        if not order.created:
            order.created = order.updated
        payload = json.dumps(order.to_dict())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO repair_orders (id, data, updated, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    data = excluded.data,
                    updated = excluded.updated,
                    status = excluded.status
                """,
                (order.id, payload, order.updated, order.status),
            )
        return order

    def create(self, **fields) -> RepairOrder:
        ro_id = new_ro_id(self.list_ids())
        order = RepairOrder(id=ro_id, **fields)
        return self.save(order)

    def delete(self, ro_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM repair_orders WHERE id = ?", (ro_id,))
            return cur.rowcount > 0

    def prune(self, keep: int | None = None) -> list[str]:
        """Drop oldest ROs beyond keep count. Returns removed ids."""
        cfg = load_config()
        keep = int(keep if keep is not None else cfg.get("local_keep", 20))
        orders = self.list_orders()
        if len(orders) <= keep:
            return []
        removed = []
        for order in orders[keep:]:
            self.delete(order.id)
            # photo files
            photo_dir = DATA_DIR / "photos" / order.id
            if photo_dir.is_dir():
                for p in photo_dir.iterdir():
                    p.unlink(missing_ok=True)
                try:
                    photo_dir.rmdir()
                except OSError:
                    pass
            removed.append(order.id)
        return removed
