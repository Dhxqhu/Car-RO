"""Advisor online presence (shop-wide) for At desk / Away from desk."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any


def ensure_advisor_presence_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS advisor_presence (
            advisor_id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            last_seen TEXT NOT NULL DEFAULT '',
            client_host TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_advisor_presence_seen ON advisor_presence(last_seen)"
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def heartbeat(
    conn: sqlite3.Connection,
    *,
    advisor_id: str,
    name: str = "",
    client_host: str = "",
) -> dict[str, Any]:
    ensure_advisor_presence_table(conn)
    aid = (advisor_id or "").strip()
    if not aid:
        raise ValueError("advisor_id required")
    ts = _now_iso()
    conn.execute(
        """
        INSERT INTO advisor_presence (advisor_id, name, last_seen, client_host)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(advisor_id) DO UPDATE SET
            name = excluded.name,
            last_seen = excluded.last_seen,
            client_host = excluded.client_host
        """,
        (aid, (name or "").strip(), ts, (client_host or "").strip()),
    )
    return {
        "advisor_id": aid,
        "name": (name or "").strip(),
        "last_seen": ts,
        "client_host": (client_host or "").strip(),
    }


def list_online(
    conn: sqlite3.Connection, *, within_seconds: int = 90
) -> list[dict[str, Any]]:
    ensure_advisor_presence_table(conn)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(15, int(within_seconds)))
    cutoff_s = cutoff.replace(microsecond=0).isoformat()
    rows = conn.execute(
        """
        SELECT advisor_id, name, last_seen, client_host
        FROM advisor_presence
        WHERE last_seen >= ?
        ORDER BY name COLLATE NOCASE
        """,
        (cutoff_s,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "advisor_id": r["advisor_id"],
                "name": r["name"],
                "last_seen": r["last_seen"],
                "client_host": r["client_host"],
            }
        )
    return out


def clear_presence(conn: sqlite3.Connection, advisor_id: str) -> None:
    ensure_advisor_presence_table(conn)
    conn.execute(
        "DELETE FROM advisor_presence WHERE advisor_id = ?",
        ((advisor_id or "").strip(),),
    )
