"""Weekly tech report archives on carro-server."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from carro_server.events import now_iso


def ensure_weekly_reports_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS weekly_tech_reports (
            week_start TEXT PRIMARY KEY,
            week_end TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by TEXT NOT NULL DEFAULT '',
            created_by_id TEXT NOT NULL DEFAULT ''
        )
        """
    )


def get_report(conn: sqlite3.Connection, week_start: str) -> dict[str, Any] | None:
    ensure_weekly_reports_table(conn)
    week_start = (week_start or "").strip()
    if not week_start:
        return None
    row = conn.execute(
        "SELECT * FROM weekly_tech_reports WHERE week_start = ?",
        (week_start,),
    ).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row["payload"] or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {
        "week_start": str(row["week_start"] or ""),
        "week_end": str(row["week_end"] or ""),
        "payload": payload,
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
        "created_by": str(row["created_by"] or ""),
        "created_by_id": str(row["created_by_id"] or ""),
    }


def list_reports(conn: sqlite3.Connection, *, limit: int = 52) -> list[dict[str, Any]]:
    ensure_weekly_reports_table(conn)
    limit = max(1, min(int(limit or 52), 200))
    rows = conn.execute(
        """
        SELECT week_start, week_end, created_at, updated_at, created_by, created_by_id
        FROM weekly_tech_reports
        ORDER BY week_start DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "week_start": str(r["week_start"] or ""),
            "week_end": str(r["week_end"] or ""),
            "created_at": str(r["created_at"] or ""),
            "updated_at": str(r["updated_at"] or ""),
            "created_by": str(r["created_by"] or ""),
            "created_by_id": str(r["created_by_id"] or ""),
        }
        for r in rows
    ]


def upsert_report(
    conn: sqlite3.Connection,
    *,
    week_start: str,
    week_end: str,
    payload: dict[str, Any],
    created_by: str = "",
    created_by_id: str = "",
) -> dict[str, Any]:
    ensure_weekly_reports_table(conn)
    week_start = (week_start or "").strip()
    week_end = (week_end or "").strip()
    if not week_start or not week_end:
        raise ValueError("week_start and week_end required")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    at = now_iso()
    existing = conn.execute(
        "SELECT week_start FROM weekly_tech_reports WHERE week_start = ?",
        (week_start,),
    ).fetchone()
    body = json.dumps(payload, ensure_ascii=False)
    if existing:
        conn.execute(
            """
            UPDATE weekly_tech_reports
            SET week_end = ?, payload = ?, updated_at = ?
            WHERE week_start = ?
            """,
            (week_end, body, at, week_start),
        )
    else:
        conn.execute(
            """
            INSERT INTO weekly_tech_reports (
                week_start, week_end, payload, created_at, updated_at,
                created_by, created_by_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                week_start,
                week_end,
                body,
                at,
                at,
                (created_by or "").strip(),
                (created_by_id or "").strip(),
            ),
        )
    out = get_report(conn, week_start)
    assert out is not None
    return out
