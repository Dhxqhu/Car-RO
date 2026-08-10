"""Tech day-start / day-end presence shifts (shop-wide on carro-server)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from typing import Any

from carro_server.events import now_iso


def ensure_shifts_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tech_shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tech_id TEXT NOT NULL,
            tech_name TEXT NOT NULL DEFAULT '',
            day TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tech_shifts_tech_day ON tech_shifts(tech_id, day)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tech_shifts_open ON tech_shifts(ended_at)"
    )


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "tech_id": str(row["tech_id"] or ""),
        "tech_name": str(row["tech_name"] or ""),
        "day": str(row["day"] or ""),
        "started_at": str(row["started_at"] or ""),
        "ended_at": str(row["ended_at"] or "") or None,
    }


def today_local() -> str:
    return date.today().isoformat()


def _normalize_iso(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        raise ValueError("Timestamp required")
    # Accept datetime-local style "YYYY-MM-DDTHH:MM" or with seconds
    if len(s) == 16 and "T" in s:
        s = s + ":00"
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            # Treat naive as local wall time → store with local offset
            local = datetime.now().astimezone()
            dt = dt.replace(tzinfo=local.tzinfo)
        return dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp: {raw}") from exc


def get_shift(conn: sqlite3.Connection, shift_id: int) -> dict[str, Any] | None:
    ensure_shifts_table(conn)
    row = conn.execute(
        "SELECT * FROM tech_shifts WHERE id = ?", (int(shift_id),)
    ).fetchone()
    return _row(row) if row else None


def get_open_shift(conn: sqlite3.Connection, tech_id: str) -> dict[str, Any] | None:
    ensure_shifts_table(conn)
    tech_id = (tech_id or "").strip()
    if not tech_id:
        return None
    row = conn.execute(
        """
        SELECT * FROM tech_shifts
        WHERE tech_id = ? AND (ended_at IS NULL OR ended_at = '')
        ORDER BY id DESC LIMIT 1
        """,
        (tech_id,),
    ).fetchone()
    return _row(row) if row else None


def list_active(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_shifts_table(conn)
    rows = conn.execute(
        """
        SELECT * FROM tech_shifts
        WHERE ended_at IS NULL OR ended_at = ''
        ORDER BY started_at ASC
        """
    ).fetchall()
    return [_row(r) for r in rows]


def list_shifts(
    conn: sqlite3.Connection,
    *,
    tech_id: str = "",
    day_from: str = "",
    day_to: str = "",
    limit: int = 500,
) -> list[dict[str, Any]]:
    ensure_shifts_table(conn)
    limit = max(1, min(int(limit or 500), 2000))
    clauses: list[str] = []
    args: list[Any] = []
    if (tech_id or "").strip():
        clauses.append("tech_id = ?")
        args.append(tech_id.strip())
    if (day_from or "").strip():
        clauses.append("day >= ?")
        args.append(day_from.strip())
    if (day_to or "").strip():
        clauses.append("day <= ?")
        args.append(day_to.strip())
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    args.append(limit)
    rows = conn.execute(
        f"SELECT * FROM tech_shifts{where} ORDER BY started_at DESC LIMIT ?",
        args,
    ).fetchall()
    return [_row(r) for r in rows]


def start_shift(
    conn: sqlite3.Connection,
    *,
    tech_id: str,
    tech_name: str = "",
    day: str | None = None,
    started_at: str | None = None,
) -> dict[str, Any]:
    ensure_shifts_table(conn)
    tech_id = (tech_id or "").strip()
    if not tech_id:
        raise ValueError("tech_id required")
    open_row = get_open_shift(conn, tech_id)
    if open_row:
        raise ValueError("Already on the clock — day-end first")
    at = _normalize_iso(started_at) if (started_at or "").strip() else now_iso()
    day_s = (day or "").strip()
    if not day_s:
        try:
            day_s = date.fromisoformat(at[:10]).isoformat()
        except ValueError:
            day_s = today_local()
    cur = conn.execute(
        """
        INSERT INTO tech_shifts (tech_id, tech_name, day, started_at, ended_at)
        VALUES (?, ?, ?, ?, '')
        """,
        (tech_id, (tech_name or "").strip() or tech_id, day_s, at),
    )
    mid = int(cur.lastrowid or 0)
    row = conn.execute("SELECT * FROM tech_shifts WHERE id = ?", (mid,)).fetchone()
    assert row is not None
    return _row(row)


def end_shift(
    conn: sqlite3.Connection,
    *,
    tech_id: str = "",
    shift_id: int | None = None,
    ended_at: str | None = None,
) -> dict[str, Any]:
    ensure_shifts_table(conn)
    open_row: dict[str, Any] | None = None
    if shift_id is not None:
        open_row = get_shift(conn, int(shift_id))
        if not open_row:
            raise ValueError("Shift not found")
        if open_row.get("ended_at"):
            raise ValueError("Shift already ended — edit times instead")
    else:
        tech_id = (tech_id or "").strip()
        if not tech_id:
            raise ValueError("tech_id required")
        open_row = get_open_shift(conn, tech_id)
        if not open_row:
            raise ValueError("Not on the clock")
    at = _normalize_iso(ended_at) if (ended_at or "").strip() else now_iso()
    started = open_row["started_at"]
    # Basic sanity: end after start
    try:
        t0 = datetime.fromisoformat(
            started.replace("Z", "+00:00") if started.endswith("Z") else started
        )
        t1 = datetime.fromisoformat(at.replace("Z", "+00:00") if at.endswith("Z") else at)
        if t1 < t0:
            raise ValueError("End time cannot be before start time")
    except ValueError as exc:
        if "cannot be before" in str(exc):
            raise
    conn.execute(
        "UPDATE tech_shifts SET ended_at = ? WHERE id = ?",
        (at, int(open_row["id"])),
    )
    row = conn.execute(
        "SELECT * FROM tech_shifts WHERE id = ?", (int(open_row["id"]),)
    ).fetchone()
    assert row is not None
    return _row(row)


def update_shift(
    conn: sqlite3.Connection,
    shift_id: int,
    *,
    started_at: str | None = None,
    ended_at: str | None = None,
    clear_end: bool = False,
    day: str | None = None,
    tech_name: str | None = None,
) -> dict[str, Any]:
    """Advisor correction for forgotten / wrong punches."""
    ensure_shifts_table(conn)
    row = get_shift(conn, int(shift_id))
    if not row:
        raise ValueError("Shift not found")
    start = row["started_at"]
    end = row.get("ended_at") or ""
    if started_at is not None and str(started_at).strip():
        start = _normalize_iso(str(started_at))
    if clear_end:
        # Re-open only if no other open shift for this tech
        other = get_open_shift(conn, row["tech_id"])
        if other and int(other["id"]) != int(shift_id):
            raise ValueError("Tech already has an open shift — end that one first")
        end = ""
    elif ended_at is not None:
        if str(ended_at).strip() == "":
            end = ""
        else:
            end = _normalize_iso(str(ended_at))
    if end:
        try:
            t0 = datetime.fromisoformat(
                start.replace("Z", "+00:00") if start.endswith("Z") else start
            )
            t1 = datetime.fromisoformat(
                end.replace("Z", "+00:00") if end.endswith("Z") else end
            )
            if t1 < t0:
                raise ValueError("End time cannot be before start time")
        except ValueError as exc:
            if "cannot be before" in str(exc):
                raise
            raise ValueError(str(exc)) from exc
    day_s = (day or "").strip() or row["day"]
    if not day_s:
        day_s = start[:10]
    name = row["tech_name"]
    if tech_name is not None and str(tech_name).strip():
        name = str(tech_name).strip()
    conn.execute(
        """
        UPDATE tech_shifts
        SET started_at = ?, ended_at = ?, day = ?, tech_name = ?
        WHERE id = ?
        """,
        (start, end or "", day_s, name, int(shift_id)),
    )
    updated = get_shift(conn, int(shift_id))
    assert updated is not None
    return updated


def delete_shift(conn: sqlite3.Connection, shift_id: int) -> bool:
    ensure_shifts_table(conn)
    cur = conn.execute("DELETE FROM tech_shifts WHERE id = ?", (int(shift_id),))
    return cur.rowcount > 0
