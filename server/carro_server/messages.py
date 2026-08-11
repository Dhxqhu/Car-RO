"""Person-to-person shop messages (tech↔advisor, tech↔tech, advisor↔advisor)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from carro_server.events import now_iso

# Minimum seconds between renotify pings for the same unread message
RENOTIFY_MIN_GAP_SEC = 15 * 60


def ensure_messages_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shop_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TEXT NOT NULL,
            body TEXT NOT NULL,
            from_id TEXT NOT NULL,
            from_name TEXT NOT NULL,
            from_role TEXT NOT NULL,
            to_id TEXT NOT NULL,
            to_name TEXT NOT NULL,
            to_role TEXT NOT NULL,
            ro_id TEXT NOT NULL DEFAULT '',
            work_item_id TEXT NOT NULL DEFAULT '',
            reply_to INTEGER,
            read_at TEXT
        )
        """
    )
    cols = {
        str(r[1])
        for r in conn.execute("PRAGMA table_info(shop_messages)").fetchall()
    }
    if "last_notified_at" not in cols:
        conn.execute(
            "ALTER TABLE shop_messages ADD COLUMN last_notified_at TEXT NOT NULL DEFAULT ''"
        )
    if "renotify_count" not in cols:
        conn.execute(
            "ALTER TABLE shop_messages ADD COLUMN renotify_count INTEGER NOT NULL DEFAULT 0"
        )
    if "delivered_at" not in cols:
        conn.execute("ALTER TABLE shop_messages ADD COLUMN delivered_at TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_shop_messages_to ON shop_messages(to_id, at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_shop_messages_from ON shop_messages(from_id, at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_shop_messages_unread ON shop_messages(to_id, read_at)"
    )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    keys = set(row.keys())
    last_notified = ""
    if "last_notified_at" in keys:
        last_notified = str(row["last_notified_at"] or "").strip()
    if not last_notified:
        last_notified = str(row["at"] or "")
    renotify_count = 0
    if "renotify_count" in keys:
        try:
            renotify_count = max(0, int(row["renotify_count"] or 0))
        except (TypeError, ValueError):
            renotify_count = 0
    return {
        "id": int(row["id"]),
        "at": str(row["at"] or ""),
        "body": str(row["body"] or ""),
        "from_id": str(row["from_id"] or ""),
        "from_name": str(row["from_name"] or ""),
        "from_role": str(row["from_role"] or ""),
        "to_id": str(row["to_id"] or ""),
        "to_name": str(row["to_name"] or ""),
        "to_role": str(row["to_role"] or ""),
        "ro_id": str(row["ro_id"] or ""),
        "work_item_id": str(row["work_item_id"] or ""),
        "reply_to": int(row["reply_to"]) if row["reply_to"] is not None else None,
        "read_at": str(row["read_at"] or "") or None,
        "delivered_at": (
            str(row["delivered_at"] or "") or None
            if "delivered_at" in keys
            else None
        ),
        "last_notified_at": last_notified,
        "renotify_count": renotify_count,
    }


def list_inbox(
    conn: sqlite3.Connection,
    *,
    for_id: str,
    unread_only: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    ensure_messages_table(conn)
    for_id = (for_id or "").strip()
    if not for_id:
        return []
    limit = max(1, min(int(limit or 100), 500))
    if unread_only:
        rows = conn.execute(
            """
            SELECT * FROM shop_messages
            WHERE to_id = ? AND (read_at IS NULL OR read_at = '')
            ORDER BY at DESC
            LIMIT ?
            """,
            (for_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM shop_messages
            WHERE to_id = ?
            ORDER BY at DESC
            LIMIT ?
            """,
            (for_id, limit),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_sent(
    conn: sqlite3.Connection,
    *,
    from_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    ensure_messages_table(conn)
    from_id = (from_id or "").strip()
    if not from_id:
        return []
    limit = max(1, min(int(limit or 100), 500))
    rows = conn.execute(
        """
        SELECT * FROM shop_messages
        WHERE from_id = ?
        ORDER BY at DESC
        LIMIT ?
        """,
        (from_id, limit),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def unread_count(conn: sqlite3.Connection, *, for_id: str) -> int:
    ensure_messages_table(conn)
    for_id = (for_id or "").strip()
    if not for_id:
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM shop_messages
        WHERE to_id = ? AND (read_at IS NULL OR read_at = '')
        """,
        (for_id,),
    ).fetchone()
    return int(row["n"] if row else 0)


def send_message(
    conn: sqlite3.Connection,
    *,
    body: str,
    from_id: str,
    from_name: str,
    from_role: str,
    to_id: str,
    to_name: str,
    to_role: str,
    ro_id: str = "",
    work_item_id: str = "",
    reply_to: int | None = None,
) -> dict[str, Any]:
    ensure_messages_table(conn)
    text = (body or "").strip()
    if not text:
        raise ValueError("Message body is required")
    if len(text) > 4000:
        raise ValueError("Message too long (max 4000 characters)")
    from_id = (from_id or "").strip()
    to_id = (to_id or "").strip()
    if not from_id or not to_id:
        raise ValueError("from_id and to_id are required")
    if from_id == to_id:
        raise ValueError("Cannot message yourself")
    role_f = (from_role or "").strip().lower()
    role_t = (to_role or "").strip().lower()
    if role_f not in ("technician", "advisor"):
        raise ValueError("from_role must be technician or advisor")
    if role_t not in ("technician", "advisor"):
        raise ValueError("to_role must be technician or advisor")
    if reply_to is not None:
        try:
            reply_to = int(reply_to)
        except (TypeError, ValueError) as exc:
            raise ValueError("reply_to must be a message id") from exc
        exists = conn.execute(
            "SELECT id FROM shop_messages WHERE id = ?", (reply_to,)
        ).fetchone()
        if not exists:
            raise ValueError(f"reply_to message not found: {reply_to}")

    at = now_iso()
    cur = conn.execute(
        """
        INSERT INTO shop_messages (
            at, body, from_id, from_name, from_role,
            to_id, to_name, to_role, ro_id, work_item_id, reply_to, read_at,
            last_notified_at, renotify_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 0)
        """,
        (
            at,
            text,
            from_id,
            (from_name or "").strip() or from_id,
            role_f,
            to_id,
            (to_name or "").strip() or to_id,
            role_t,
            (ro_id or "").strip(),
            (work_item_id or "").strip(),
            reply_to,
            at,
        ),
    )
    mid = int(cur.lastrowid or 0)
    row = conn.execute("SELECT * FROM shop_messages WHERE id = ?", (mid,)).fetchone()
    assert row is not None
    return _row_to_dict(row)


def mark_read(
    conn: sqlite3.Connection,
    message_id: int,
    *,
    for_id: str,
) -> dict[str, Any] | None:
    ensure_messages_table(conn)
    for_id = (for_id or "").strip()
    row = conn.execute(
        "SELECT * FROM shop_messages WHERE id = ?", (int(message_id),)
    ).fetchone()
    if not row:
        return None
    if str(row["to_id"] or "") != for_id:
        raise PermissionError("Only the recipient can mark a message read")
    if row["read_at"]:
        return _row_to_dict(row)
    at = now_iso()
    # Read implies the message reached this machine.
    keys = set(row.keys())
    if "delivered_at" in keys and not str(row["delivered_at"] or "").strip():
        conn.execute(
            "UPDATE shop_messages SET read_at = ?, delivered_at = ? WHERE id = ?",
            (at, at, int(message_id)),
        )
    else:
        conn.execute(
            "UPDATE shop_messages SET read_at = ? WHERE id = ?",
            (at, int(message_id)),
        )
    row = conn.execute(
        "SELECT * FROM shop_messages WHERE id = ?", (int(message_id),)
    ).fetchone()
    return _row_to_dict(row) if row else None


def mark_delivered(
    conn: sqlite3.Connection,
    message_ids: list[int],
    *,
    for_id: str,
) -> list[dict[str, Any]]:
    """Recipient bay ack: message reached this machine (idempotent)."""
    ensure_messages_table(conn)
    for_id = (for_id or "").strip()
    if not for_id or not message_ids:
        return []
    at = now_iso()
    out: list[dict[str, Any]] = []
    for mid in message_ids:
        try:
            mid_i = int(mid)
        except (TypeError, ValueError):
            continue
        row = conn.execute(
            "SELECT * FROM shop_messages WHERE id = ?", (mid_i,)
        ).fetchone()
        if not row:
            continue
        if str(row["to_id"] or "") != for_id:
            continue
        keys = set(row.keys())
        already = ""
        if "delivered_at" in keys:
            already = str(row["delivered_at"] or "").strip()
        if already:
            out.append(_row_to_dict(row))
            continue
        conn.execute(
            "UPDATE shop_messages SET delivered_at = ? WHERE id = ? AND to_id = ?",
            (at, mid_i, for_id),
        )
        row = conn.execute(
            "SELECT * FROM shop_messages WHERE id = ?", (mid_i,)
        ).fetchone()
        if row:
            out.append(_row_to_dict(row))
    return out


def _parse_iso(ts: str) -> float | None:
    raw = (ts or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return None


def renotify(
    conn: sqlite3.Connection,
    message_id: int,
    *,
    from_id: str,
) -> dict[str, Any]:
    """
    Re-ping the recipient for an unread message (sender only).
    Raises ValueError on business-rule failures; PermissionError if not sender.
    """
    ensure_messages_table(conn)
    from_id = (from_id or "").strip()
    row = conn.execute(
        "SELECT * FROM shop_messages WHERE id = ?", (int(message_id),)
    ).fetchone()
    if not row:
        raise ValueError("Message not found")
    if str(row["from_id"] or "") != from_id:
        raise PermissionError("Only the sender can renotify")
    if row["read_at"]:
        raise ValueError("Message already read")
    last = str(row["last_notified_at"] or row["at"] or "")
    last_ts = _parse_iso(last)
    now = datetime.now(tz=timezone.utc).timestamp()
    if last_ts is not None and (now - last_ts) < RENOTIFY_MIN_GAP_SEC:
        wait = int(RENOTIFY_MIN_GAP_SEC - (now - last_ts))
        raise ValueError(f"Wait {max(1, wait)}s before renotifying again")
    at = now_iso()
    try:
        count = max(0, int(row["renotify_count"] or 0)) + 1
    except (TypeError, ValueError, KeyError):
        count = 1
    conn.execute(
        """
        UPDATE shop_messages
        SET last_notified_at = ?, renotify_count = ?
        WHERE id = ?
        """,
        (at, count, int(message_id)),
    )
    row = conn.execute(
        "SELECT * FROM shop_messages WHERE id = ?", (int(message_id),)
    ).fetchone()
    assert row is not None
    return _row_to_dict(row)
