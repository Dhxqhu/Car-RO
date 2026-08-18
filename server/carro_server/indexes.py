"""Denormalized RO / parts indexes for unbounded archive search."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any


def _norm(s: object) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip())


def _norm_upper(s: object) -> str:
    return _norm(s).upper()


def _norm_lower(s: object) -> str:
    return _norm(s).lower()


def ensure_index_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ro_index (
            id TEXT PRIMARY KEY,
            updated TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            vin TEXT NOT NULL DEFAULT '',
            vin_tail TEXT NOT NULL DEFAULT '',
            customer_name TEXT NOT NULL DEFAULT '',
            plate TEXT NOT NULL DEFAULT '',
            year TEXT NOT NULL DEFAULT '',
            make TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ro_index_vin ON ro_index(vin)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ro_index_vin_tail ON ro_index(vin_tail)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ro_index_customer ON ro_index(customer_name)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ro_index_status_updated ON ro_index(status, updated DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ro_index_updated ON ro_index(updated DESC)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ro_parts (
            ro_id TEXT NOT NULL,
            work_item_id TEXT NOT NULL,
            part_id TEXT NOT NULL,
            part_number TEXT NOT NULL DEFAULT '',
            manufacturer TEXT NOT NULL DEFAULT '',
            brand TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            requested_at TEXT NOT NULL DEFAULT '',
            ordered_at TEXT NOT NULL DEFAULT '',
            received_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            customer TEXT NOT NULL DEFAULT '',
            vehicle TEXT NOT NULL DEFAULT '',
            vin TEXT NOT NULL DEFAULT '',
            make TEXT NOT NULL DEFAULT '',
            concern TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (ro_id, work_item_id, part_id)
        )
        """
    )
    # Older DBs created before brand / wrong_count / oem / supplier existed.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ro_parts)").fetchall()}
    if "brand" not in cols:
        conn.execute("ALTER TABLE ro_parts ADD COLUMN brand TEXT NOT NULL DEFAULT ''")
    if "wrong_count" not in cols:
        conn.execute("ALTER TABLE ro_parts ADD COLUMN wrong_count INTEGER NOT NULL DEFAULT 0")
    if "wrong_note" not in cols:
        conn.execute("ALTER TABLE ro_parts ADD COLUMN wrong_note TEXT NOT NULL DEFAULT ''")
    if "oem_part_number" not in cols:
        conn.execute("ALTER TABLE ro_parts ADD COLUMN oem_part_number TEXT NOT NULL DEFAULT ''")
    if "supplier" not in cols:
        conn.execute("ALTER TABLE ro_parts ADD COLUMN supplier TEXT NOT NULL DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ro_parts_pn ON ro_parts(part_number)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ro_parts_oem ON ro_parts(oem_part_number)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ro_parts_supplier ON ro_parts(supplier)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ro_parts_mfr ON ro_parts(manufacturer)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ro_parts_brand ON ro_parts(brand)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ro_parts_pn_mfr ON ro_parts(part_number, manufacturer)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ro_parts_status ON ro_parts(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ro_parts_ro ON ro_parts(ro_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ro_parts_requested ON ro_parts(requested_at)"
    )


def _customer_name(ro: dict[str, Any]) -> str:
    last = _norm(ro.get("last_name"))
    first = _norm(ro.get("first_name"))
    if last and first:
        return _norm_lower(f"{last}, {first}")
    return _norm_lower(f"{last} {first}".strip())


def _vehicle_label(ro: dict[str, Any]) -> str:
    bits = [_norm(ro.get("year")), _norm(ro.get("make")), _norm(ro.get("model"))]
    return " ".join(b for b in bits if b) or ""


def sync_ro_projections(conn: sqlite3.Connection, ro: dict[str, Any]) -> None:
    """Replace ro_index row and all ro_parts rows for this RO."""
    ensure_index_tables(conn)
    ro_id = _norm(ro.get("id"))
    if not ro_id:
        return
    vin = _norm_upper(ro.get("vin"))
    vin_tail = vin[-8:] if len(vin) >= 8 else vin
    conn.execute(
        """
        INSERT INTO ro_index (
            id, updated, status, vin, vin_tail, customer_name,
            plate, year, make, model
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            updated = excluded.updated,
            status = excluded.status,
            vin = excluded.vin,
            vin_tail = excluded.vin_tail,
            customer_name = excluded.customer_name,
            plate = excluded.plate,
            year = excluded.year,
            make = excluded.make,
            model = excluded.model
        """,
        (
            ro_id,
            _norm(ro.get("updated") or ro.get("created")),
            _norm_lower(ro.get("status")),
            vin,
            vin_tail,
            _customer_name(ro),
            _norm_upper(ro.get("plate")),
            _norm(ro.get("year")),
            _norm_lower(ro.get("make")),
            _norm_lower(ro.get("model")),
        ),
    )
    conn.execute("DELETE FROM ro_parts WHERE ro_id = ?", (ro_id,))
    customer = _norm(f"{ro.get('last_name') or ''}, {ro.get('first_name') or ''}".strip(", "))
    vehicle = _vehicle_label(ro)
    make = _norm(ro.get("make"))
    rows: list[tuple[Any, ...]] = []
    for wi in ro.get("work_items") or []:
        if not isinstance(wi, dict):
            continue
        wid = _norm(wi.get("id"))
        concern = _norm(wi.get("concern"))[:160]
        for p in wi.get("parts") or []:
            if not isinstance(p, dict):
                continue
            pid = _norm(p.get("id"))
            if not pid:
                continue
            rows.append(
                (
                    ro_id,
                    wid,
                    pid,
                    _norm_upper(p.get("part_number")),
                    _norm_upper(p.get("oem_part_number")),
                    _norm_upper(p.get("manufacturer") or make),
                    _norm_upper(p.get("brand")),
                    _norm(p.get("supplier")),
                    _norm(p.get("description")),
                    _norm_lower(p.get("status") or "new_request"),
                    _norm(p.get("requested_at")),
                    _norm(p.get("ordered_at")),
                    _norm(p.get("received_at")),
                    _norm(p.get("updated_at") or p.get("requested_at")),
                    customer,
                    vehicle,
                    vin,
                    make,
                    concern,
                    max(0, int(p.get("wrong_count") or 0)),
                    _norm(p.get("wrong_note")),
                )
            )
    if rows:
        conn.executemany(
            """
            INSERT INTO ro_parts (
                ro_id, work_item_id, part_id, part_number, oem_part_number,
                manufacturer, brand, supplier,
                description, status, requested_at, ordered_at, received_at,
                updated_at, customer, vehicle, vin, make, concern,
                wrong_count, wrong_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def delete_ro_projections(conn: sqlite3.Connection, ro_id: str) -> None:
    ensure_index_tables(conn)
    rid = _norm(ro_id)
    conn.execute("DELETE FROM ro_index WHERE id = ?", (rid,))
    conn.execute("DELETE FROM ro_parts WHERE ro_id = ?", (rid,))


def backfill_projections(conn: sqlite3.Connection) -> dict[str, int]:
    """Rebuild projections from all repair_orders blobs. Safe to re-run."""
    ensure_index_tables(conn)
    rows = conn.execute("SELECT id, data FROM repair_orders").fetchall()
    ok = 0
    bad = 0
    for row in rows:
        try:
            data = json.loads(row["data"] if isinstance(row, sqlite3.Row) else row[1])
            if not isinstance(data, dict):
                bad += 1
                continue
            if not data.get("id"):
                data["id"] = row["id"] if isinstance(row, sqlite3.Row) else row[0]
            sync_ro_projections(conn, data)
            ok += 1
        except (TypeError, ValueError, json.JSONDecodeError):
            bad += 1
    # Drop orphan projections
    conn.execute(
        "DELETE FROM ro_index WHERE id NOT IN (SELECT id FROM repair_orders)"
    )
    conn.execute(
        "DELETE FROM ro_parts WHERE ro_id NOT IN (SELECT id FROM repair_orders)"
    )
    return {"indexed": ok, "errors": bad, "total": len(rows)}


def maybe_backfill_if_empty(conn: sqlite3.Connection) -> dict[str, int] | None:
    ensure_index_tables(conn)
    n_ro = conn.execute("SELECT COUNT(*) AS c FROM repair_orders").fetchone()["c"]
    n_idx = conn.execute("SELECT COUNT(*) AS c FROM ro_index").fetchone()["c"]
    if n_ro > 0 and n_idx == 0:
        return backfill_projections(conn)
    if n_ro > 0 and n_idx < n_ro:
        # Partial / stale — full rebuild
        return backfill_projections(conn)
    return None


def search_ro_ids(
    conn: sqlite3.Connection,
    *,
    q: str = "",
    make: str = "",
    model: str = "",
    year: str = "",
    name: str = "",
    vin: str = "",
    status: str = "",
    plate: str = "",
    limit: int = 500,
) -> list[str]:
    """Return matching RO ids using ro_index (plus optional q blob fallback)."""
    ensure_index_tables(conn)
    maybe_backfill_if_empty(conn)

    q_n = _norm_lower(q)
    make_n = _norm_lower(make)
    model_n = _norm_lower(model)
    year_n = _norm(year)
    name_n = _norm_lower(name)
    vin_n = _norm_upper(vin)
    status_n = _norm_lower(status)
    plate_n = _norm_upper(plate)

    # Structured filters via index
    clauses: list[str] = []
    args: list[Any] = []
    if make_n:
        clauses.append("make LIKE ?")
        args.append(f"%{make_n}%")
    if model_n:
        clauses.append("model LIKE ?")
        args.append(f"%{model_n}%")
    if year_n:
        clauses.append("year LIKE ?")
        args.append(f"%{year_n}%")
    if status_n:
        clauses.append("status = ?")
        args.append(status_n)
    if plate_n:
        clauses.append("plate LIKE ?")
        args.append(f"%{plate_n}%")
    if name_n:
        clauses.append("customer_name LIKE ?")
        args.append(f"%{name_n}%")
    if vin_n:
        if len(vin_n) >= 8:
            clauses.append("(vin = ? OR vin LIKE ? OR vin_tail = ? OR vin_tail LIKE ?)")
            args.extend([vin_n, f"%{vin_n}%", vin_n[-8:], f"%{vin_n}%"])
        else:
            clauses.append("(vin LIKE ? OR vin_tail LIKE ?)")
            args.extend([f"%{vin_n}%", f"%{vin_n}%"])

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT id FROM ro_index{where} ORDER BY updated DESC LIMIT ?"
    args.append(max(1, min(int(limit), 2000)))
    ids = [r["id"] for r in conn.execute(sql, args).fetchall()]

    if not q_n:
        return ids

    # Free-text q: filter candidate set (or all recent if no structured filters)
    if not ids and not clauses:
        ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM ro_index ORDER BY updated DESC LIMIT ?",
                (max(1, min(int(limit) * 5, 5000)),),
            ).fetchall()
        ]
    hits: list[str] = []
    for rid in ids:
        row = conn.execute(
            "SELECT data FROM repair_orders WHERE id = ?", (rid,)
        ).fetchone()
        if not row:
            continue
        try:
            o = json.loads(row["data"])
        except json.JSONDecodeError:
            continue
        blob = " ".join(
            str(o.get(k) or "")
            for k in (
                "id",
                "first_name",
                "last_name",
                "year",
                "make",
                "model",
                "vin",
                "plate",
                "phone",
                "status",
                "complaint",
                "tech_notes",
                "intake_notes",
            )
        ).lower()
        for it in o.get("work_items") or []:
            if isinstance(it, dict):
                blob += " " + f"{it.get('concern') or ''} {it.get('notes') or ''}".lower()
        if q_n in blob:
            hits.append(rid)
        if len(hits) >= limit:
            break
    return hits


def load_ros_by_ids(conn: sqlite3.Connection, ids: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rid in ids:
        row = conn.execute(
            "SELECT data FROM repair_orders WHERE id = ?", (rid,)
        ).fetchone()
        if not row:
            continue
        try:
            o = json.loads(row["data"])
            if isinstance(o, dict):
                out.append(o)
        except json.JSONDecodeError:
            continue
    return out


def search_parts(
    conn: sqlite3.Connection,
    *,
    part_number: str = "",
    manufacturer: str = "",
    status: str = "",
    ro_id: str = "",
    q: str = "",
    include_received: bool = False,
    limit: int = 500,
) -> list[dict[str, Any]]:
    ensure_index_tables(conn)
    maybe_backfill_if_empty(conn)

    clauses: list[str] = []
    args: list[Any] = []
    pn = _norm_upper(part_number)
    mfr = _norm_upper(manufacturer)
    st = _norm_lower(status)
    rid = _norm(ro_id)
    qn = _norm_lower(q)

    if pn:
        clauses.append("part_number LIKE ?")
        args.append(f"%{pn}%")
    if mfr:
        clauses.append("manufacturer LIKE ?")
        args.append(f"%{mfr}%")
    if st:
        clauses.append("status = ?")
        args.append(st)
    elif not include_received:
        clauses.append("status NOT IN ('received')")
    if rid:
        clauses.append("ro_id = ?")
        args.append(rid)
    if qn:
        clauses.append(
            "(LOWER(description) LIKE ? OR LOWER(part_number) LIKE ? OR LOWER(oem_part_number) LIKE ? OR LOWER(manufacturer) LIKE ? OR LOWER(brand) LIKE ? OR LOWER(supplier) LIKE ? OR LOWER(concern) LIKE ?)"
        )
        like = f"%{qn}%"
        args.extend([like, like, like, like, like, like, like])

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
        SELECT ro_id, work_item_id, part_id, part_number, oem_part_number,
               manufacturer, brand, supplier,
               description, status, requested_at, ordered_at, received_at,
               updated_at, customer, vehicle, vin, make, concern,
               wrong_count, wrong_note
        FROM ro_parts
        {where}
        ORDER BY COALESCE(NULLIF(requested_at, ''), updated_at) DESC
        LIMIT ?
    """
    args.append(max(1, min(int(limit), 2000)))
    rows = []
    for r in conn.execute(sql, args).fetchall():
        keys = r.keys()
        rows.append(
            {
                "ro_id": r["ro_id"],
                "work_item_id": r["work_item_id"],
                "part_id": r["part_id"],
                "part_number": r["part_number"],
                "oem_part_number": r["oem_part_number"] if "oem_part_number" in keys else "",
                "manufacturer": r["manufacturer"],
                "brand": r["brand"] if "brand" in keys else "",
                "supplier": r["supplier"] if "supplier" in keys else "",
                "description": r["description"],
                "status": r["status"],
                "requested_at": r["requested_at"],
                "ordered_at": r["ordered_at"],
                "received_at": r["received_at"],
                "updated_at": r["updated_at"],
                "customer": r["customer"],
                "vehicle": r["vehicle"],
                "vin": r["vin"],
                "make": r["make"],
                "concern": r["concern"],
                "item_type": "",
                "wrong_count": int(r["wrong_count"] or 0) if "wrong_count" in keys else 0,
                "wrong_note": r["wrong_note"] if "wrong_note" in keys else "",
            }
        )
    return rows


def parts_usage_by_month(
    conn: sqlite3.Connection,
    *,
    year: int,
    month: int,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Aggregate part lines in a calendar month for stocking decisions."""
    ensure_index_tables(conn)
    maybe_backfill_if_empty(conn)
    y, m = int(year), int(month)
    if m < 1 or m > 12:
        raise ValueError("month must be 1-12")
    start = f"{y:04d}-{m:02d}-01"
    if m == 12:
        end = f"{y + 1:04d}-01-01"
    else:
        end = f"{y:04d}-{m + 1:02d}-01"

    sql = """
        SELECT
            part_number,
            manufacturer,
            MAX(brand) AS brand,
            MAX(description) AS description,
            COUNT(*) AS use_count,
            COUNT(DISTINCT ro_id) AS ro_count,
            MAX(COALESCE(NULLIF(requested_at, ''), updated_at)) AS last_used_at
        FROM ro_parts
        WHERE COALESCE(NULLIF(requested_at, ''), updated_at) >= ?
          AND COALESCE(NULLIF(requested_at, ''), updated_at) < ?
        GROUP BY
            CASE WHEN TRIM(part_number) != '' THEN part_number ELSE UPPER(TRIM(description)) END,
            manufacturer,
            brand
        ORDER BY use_count DESC, ro_count DESC
        LIMIT ?
    """
    out = []
    for r in conn.execute(sql, (start, end, max(1, min(int(limit), 500)))).fetchall():
        out.append(
            {
                "part_number": r["part_number"] or "",
                "manufacturer": r["manufacturer"] or "",
                "brand": r["brand"] or "",
                "description": r["description"] or "",
                "use_count": int(r["use_count"] or 0),
                "ro_count": int(r["ro_count"] or 0),
                "last_used_at": r["last_used_at"] or "",
                "year": y,
                "month": m,
            }
        )
    return out


def distinct_part_suggestions(
    conn: sqlite3.Connection,
    *,
    q: str = "",
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Deduped catalog suggestions for add-part lookup."""
    ensure_index_tables(conn)
    maybe_backfill_if_empty(conn)
    qn = _norm_lower(q)
    if not qn:
        sql = """
            SELECT part_number, manufacturer, brand, MAX(description) AS description,
                   COUNT(*) AS use_count
            FROM ro_parts
            WHERE TRIM(part_number) != '' OR TRIM(description) != ''
            GROUP BY part_number, manufacturer, brand
            ORDER BY use_count DESC
            LIMIT ?
        """
        args: list[Any] = [max(1, min(int(limit), 100))]
    else:
        like = f"%{qn}%"
        sql = """
            SELECT part_number, manufacturer, brand, MAX(description) AS description,
                   COUNT(*) AS use_count
            FROM ro_parts
            WHERE LOWER(description) LIKE ?
               OR part_number LIKE ?
               OR manufacturer LIKE ?
               OR brand LIKE ?
            GROUP BY part_number, manufacturer, brand
            ORDER BY use_count DESC
            LIMIT ?
        """
        args = [like, like.upper(), like.upper(), like.upper(), max(1, min(int(limit), 100))]
    return [
        {
            "part_number": r["part_number"] or "",
            "manufacturer": r["manufacturer"] or "",
            "brand": r["brand"] or "",
            "description": r["description"] or "",
            "use_count": int(r["use_count"] or 0),
        }
        for r in conn.execute(sql, args).fetchall()
    ]
