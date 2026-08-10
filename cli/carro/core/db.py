"""Local SQLite store for repair orders + photo metadata."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from carro.config import DATA_DIR, load_config, photos_dir
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
        from carro.core.work_items import apply_rollups

        apply_rollups(order)
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

    def search(
        self,
        query: str = "",
        *,
        make: str = "",
        model: str = "",
        year: str = "",
        name: str = "",
        vin: str = "",
        status: str = "",
        plate: str = "",
    ) -> list[RepairOrder]:
        """Case-insensitive filter. Free-text `query` matches any of the common fields."""
        q = query.strip().lower()
        filters = {
            "make": make.strip().lower(),
            "model": model.strip().lower(),
            "year": year.strip().lower(),
            "name": name.strip().lower(),
            "vin": vin.strip().lower(),
            "status": status.strip().lower(),
            "plate": plate.strip().lower(),
        }
        hits: list[RepairOrder] = []
        for order in self.list_orders():
            item_blob = " ".join(
                " ".join(
                    [
                        str(it.get("concern") or ""),
                        str(it.get("notes") or ""),
                        str(it.get("private_notes") or ""),
                        str(it.get("item_type") or ""),
                        str(it.get("status") or ""),
                        " ".join(
                            f"{(p.get('description') or '')} {(p.get('part_number') or '')} {(p.get('manufacturer') or '')}"
                            for p in (it.get("parts") or [])
                            if isinstance(p, dict)
                        ),
                    ]
                )
                for it in (order.work_items or [])
                if isinstance(it, dict)
            )
            blob = " ".join(
                [
                    order.id,
                    order.first_name,
                    order.last_name,
                    order.customer_label(),
                    order.year,
                    order.make,
                    order.model,
                    order.vin,
                    order.plate,
                    order.phone,
                    order.status,
                    order.complaint,
                    order.tech_notes,
                    item_blob,
                ]
            ).lower()
            if q and q not in blob:
                continue
            if filters["make"] and filters["make"] not in order.make.lower():
                continue
            if filters["model"] and filters["model"] not in order.model.lower():
                continue
            if filters["year"] and filters["year"] not in order.year.lower():
                continue
            if filters["vin"] and filters["vin"] not in order.vin.lower():
                continue
            if filters["plate"] and filters["plate"] not in order.plate.lower():
                continue
            if filters["status"] and filters["status"] != order.status.lower():
                continue
            if filters["name"]:
                cust = f"{order.first_name} {order.last_name} {order.customer_label()}".lower()
                if filters["name"] not in cust:
                    continue
            hits.append(order)
        return hits

    def prune(
        self,
        keep: int | None = None,
        photo_keep: int | None = None,
        billed_keep: int | None = None,
    ) -> list[str]:
        """
        Trim local cache to configured limits.
        - keep: max non-billed (active) ROs retained
        - billed_keep: max billed_out ROs retained (newest by billed_out_at / updated)
        - photo_keep: among retained ROs, only this many newest keep photo files on disk
        Returns removed RO ids (fully deleted).
        """
        from carro.config import (
            resolve_local_billed_keep,
            resolve_local_keep,
            resolve_local_photo_keep,
        )

        cfg = load_config()
        keep = int(keep if keep is not None else resolve_local_keep(cfg))
        billed_keep = int(
            billed_keep if billed_keep is not None else resolve_local_billed_keep(cfg)
        )
        photo_keep = int(
            photo_keep if photo_keep is not None else resolve_local_photo_keep(cfg)
        )
        orders = self.list_orders()
        removed: list[str] = []

        active = [o for o in orders if o.status != "billed_out"]
        billed = [o for o in orders if o.status == "billed_out"]
        billed.sort(
            key=lambda o: (o.billed_out_at or o.updated or o.created or ""),
            reverse=True,
        )

        retain_active = active[: max(0, keep)]
        retain_billed = billed[: max(0, billed_keep)]
        retain_ids = {o.id for o in retain_active} | {o.id for o in retain_billed}
        retained = [o for o in orders if o.id in retain_ids]

        photo_keep = max(0, min(photo_keep, len(retained)))
        # Strip photos from retained ROs outside the newest photo_keep window
        for order in retained[photo_keep:]:
            self._clear_local_photos(order, mark_meta=True)

        # Drop aged received part lines from retained ROs (server already has them via sync).
        from carro.config import resolve_local_parts_received_keep_hours
        from carro.core.work_items import prune_received_parts

        parts_hours = resolve_local_parts_received_keep_hours(cfg)
        for order in retained:
            if prune_received_parts(order, keep_hours=parts_hours):
                self.save(order)

        for order in orders:
            if order.id in retain_ids:
                continue
            self.delete(order.id)
            self._clear_local_photos(order, mark_meta=False)
            removed.append(order.id)
        return removed

    def _clear_local_photos(self, order: RepairOrder, *, mark_meta: bool) -> None:
        photo_dir = photos_dir() / order.id
        if not photo_dir.is_dir():
            return
        cleared = False
        for p in list(photo_dir.iterdir()):
            try:
                p.unlink(missing_ok=True)
                cleared = True
            except OSError:
                pass
        try:
            photo_dir.rmdir()
        except OSError:
            pass
        if mark_meta and cleared:
            for meta in order.photos:
                meta["local_cleared"] = True
            self.save(order)
