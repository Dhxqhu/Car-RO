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
            cols = {
                r["name"]
                for r in conn.execute("PRAGMA table_info(repair_orders)").fetchall()
            }
            if "needs_sync" not in cols:
                # Existing rows start clean; local edits flip this on.
                conn.execute(
                    "ALTER TABLE repair_orders ADD COLUMN needs_sync INTEGER NOT NULL DEFAULT 0"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ro_updated ON repair_orders(updated DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ro_needs_sync ON repair_orders(needs_sync)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_deletes (
                    id TEXT PRIMARY KEY,
                    deleted_at TEXT NOT NULL
                )
                """
            )
            # Offline shifts / messages (shop server unreachable; local engine up).
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS local_shifts (
                    local_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id TEXT NOT NULL UNIQUE,
                    server_id INTEGER,
                    tech_id TEXT NOT NULL,
                    tech_name TEXT NOT NULL DEFAULT '',
                    day TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL DEFAULT '',
                    pending_sync INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_local_shifts_tech "
                "ON local_shifts(tech_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_local_shifts_server "
                "ON local_shifts(server_id)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_shift_ops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_op_id TEXT NOT NULL UNIQUE,
                    op TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_messages (
                    client_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_message_acks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS message_cache (
                    cache_key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
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

    def save(
        self,
        order: RepairOrder,
        *,
        mark_pending_sync: bool = True,
    ) -> RepairOrder:
        """
        Persist RO locally. By default marks needs_sync so a later push retries
        if the shop server was unreachable at edit time.
        Pass mark_pending_sync=False when caching a copy that already came from the server.
        """
        from carro.core.work_items import apply_rollups

        apply_rollups(order)
        order.updated = now_iso()
        if not order.created:
            order.created = order.updated
        payload = json.dumps(order.to_dict())
        needs = 1 if mark_pending_sync else 0
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO repair_orders (id, data, updated, status, needs_sync)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    data = excluded.data,
                    updated = excluded.updated,
                    status = excluded.status,
                    needs_sync = CASE
                        WHEN excluded.needs_sync = 1 THEN 1
                        ELSE repair_orders.needs_sync
                    END
                """,
                (order.id, payload, order.updated, order.status, needs),
            )
            # Explicit clear when caching a remote copy with no local dirty flag.
            if not mark_pending_sync:
                conn.execute(
                    "UPDATE repair_orders SET needs_sync = 0 WHERE id = ?",
                    (order.id,),
                )
        return order

    def create(self, **fields) -> RepairOrder:
        ro_id = new_ro_id(self.list_ids())
        order = RepairOrder(id=ro_id, **fields)
        return self.save(order)

    def delete(self, ro_id: str, *, queue_remote: bool = False) -> bool:
        """
        Delete locally. If queue_remote=True, remember the id so sync can DELETE
        on the shop server once connectivity returns.
        """
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM repair_orders WHERE id = ?", (ro_id,))
            if queue_remote and cur.rowcount > 0:
                conn.execute(
                    """
                    INSERT INTO pending_deletes (id, deleted_at)
                    VALUES (?, ?)
                    ON CONFLICT(id) DO UPDATE SET deleted_at = excluded.deleted_at
                    """,
                    (ro_id, now_iso()),
                )
            return cur.rowcount > 0

    def mark_synced(self, ro_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE repair_orders SET needs_sync = 0 WHERE id = ?",
                (ro_id,),
            )

    def mark_needs_sync(self, ro_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE repair_orders SET needs_sync = 1 WHERE id = ?",
                (ro_id,),
            )

    def needs_sync(self, ro_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT needs_sync FROM repair_orders WHERE id = ?",
                (ro_id,),
            ).fetchone()
        return bool(row and int(row["needs_sync"] or 0))

    def list_pending_sync_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM repair_orders WHERE needs_sync = 1 ORDER BY updated DESC"
            ).fetchall()
        return [r["id"] for r in rows]

    def list_pending_orders(self) -> list[RepairOrder]:
        ids = self.list_pending_sync_ids()
        out: list[RepairOrder] = []
        for rid in ids:
            order = self.get(rid)
            if order:
                out.append(order)
        return out

    def list_pending_deletes(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM pending_deletes ORDER BY deleted_at"
            ).fetchall()
        return [r["id"] for r in rows]

    def clear_pending_delete(self, ro_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM pending_deletes WHERE id = ?", (ro_id,))

    def pending_shift_ops_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM pending_shift_ops"
            ).fetchone()
        return int(row["n"] if row else 0)

    def pending_messages_count(self) -> int:
        with self._connect() as conn:
            msgs = conn.execute(
                "SELECT COUNT(*) AS n FROM pending_messages"
            ).fetchone()
            acks = conn.execute(
                "SELECT COUNT(*) AS n FROM pending_message_acks"
            ).fetchone()
        return int(msgs["n"] if msgs else 0) + int(acks["n"] if acks else 0)

    def sync_status(self) -> dict:
        pending_ros = self.list_pending_sync_ids()
        pending_dels = self.list_pending_deletes()
        pending_shifts = self.pending_shift_ops_count()
        pending_msgs = self.pending_messages_count()
        return {
            "pending_ros": len(pending_ros),
            "pending_deletes": len(pending_dels),
            "pending_shifts": pending_shifts,
            "pending_messages": pending_msgs,
            "pending_total": (
                len(pending_ros)
                + len(pending_dels)
                + pending_shifts
                + pending_msgs
            ),
            "pending_ro_ids": pending_ros[:50],
            "pending_delete_ids": pending_dels[:50],
        }

    def pending_sync_count(self) -> int:
        return int(self.sync_status().get("pending_total") or 0)

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
                            f"{(p.get('description') or '')} {(p.get('part_number') or '')} {(p.get('manufacturer') or '')} {(p.get('brand') or '')}"
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
        from carro.core.models import CLOSED_STATUSES

        orders = self.list_orders()
        removed: list[str] = []

        active = [o for o in orders if (o.status or "") not in CLOSED_STATUSES]
        closed = [o for o in orders if (o.status or "") in CLOSED_STATUSES]

        def _closed_sort_key(o: RepairOrder) -> str:
            return (
                o.billed_out_at
                or o.canceled_at
                or o.no_call_no_show_at
                or o.updated
                or o.created
                or ""
            )

        closed.sort(key=_closed_sort_key, reverse=True)

        retain_active = active[: max(0, keep)]
        retain_billed = closed[: max(0, billed_keep)]
        retain_ids = {o.id for o in retain_active} | {o.id for o in retain_billed}
        # Never drop ROs that have not reached the shop server yet.
        retain_ids |= set(self.list_pending_sync_ids())
        retained = [o for o in orders if o.id in retain_ids]

        photo_keep = max(0, min(photo_keep, len(retained)))
        # Strip photos from retained ROs outside the newest photo_keep window
        for order in retained[photo_keep:]:
            if self.needs_sync(order.id):
                continue
            self._clear_local_photos(order, mark_meta=True)

        # Drop aged received part lines from retained ROs (server already has them via sync).
        from carro.config import resolve_local_parts_received_keep_hours
        from carro.core.work_items import prune_received_parts

        parts_hours = resolve_local_parts_received_keep_hours(cfg)
        for order in retained:
            if self.needs_sync(order.id):
                continue
            if prune_received_parts(order, keep_hours=parts_hours):
                self.save(order, mark_pending_sync=False)

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
            self.save(order, mark_pending_sync=False)
