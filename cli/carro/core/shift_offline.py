"""Local-first tech shifts with outbox drain when shop server returns."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime
from typing import Any

from carro.core.db import LocalStore
from carro.core.models import now_iso
from carro.storage.remote import RemoteClient

log = logging.getLogger("carro.shift_offline")


def _local_day_for_timestamp(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return date.today().isoformat()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        if len(s) >= 5 and s[-5] in "+-" and s[-3] != ":":
            s = f"{s[:-2]}:{s[-2:]}"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.date().isoformat()
        return dt.astimezone().date().isoformat()
    except ValueError:
        return date.today().isoformat()


def _normalize_iso(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        raise ValueError("Timestamp required")
    if len(s) == 16 and "T" in s:
        s = s + ":00"
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        if len(s) >= 5 and s[-5] in "+-" and s[-3] != ":":
            s = f"{s[:-2]}:{s[-2:]}"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            local = datetime.now().astimezone()
            dt = dt.replace(tzinfo=local.tzinfo)
        return dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp: {raw}") from exc


def _row_to_public(row: sqlite3_row_like) -> dict[str, Any]:
    local_id = int(row["local_id"])
    server_id = row["server_id"]
    pending = bool(int(row["pending_sync"] or 0))
    pub_id = int(server_id) if server_id is not None else -local_id
    ended = str(row["ended_at"] or "") or None
    return {
        "id": pub_id,
        "local_id": local_id,
        "client_id": str(row["client_id"] or ""),
        "server_id": int(server_id) if server_id is not None else None,
        "tech_id": str(row["tech_id"] or ""),
        "tech_name": str(row["tech_name"] or ""),
        "day": str(row["day"] or ""),
        "started_at": str(row["started_at"] or ""),
        "ended_at": ended,
        "pending_sync": pending,
    }


# Typing without importing sqlite3.Row everywhere
sqlite3_row_like = Any


def _enqueue_op(store: LocalStore, op: str, payload: dict[str, Any]) -> str:
    client_op_id = str(uuid.uuid4())
    with store._connect() as conn:
        conn.execute(
            """
            INSERT INTO pending_shift_ops (client_op_id, op, payload, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (client_op_id, op, json.dumps(payload), now_iso()),
        )
    return client_op_id


def _get_by_local_id(store: LocalStore, local_id: int) -> dict[str, Any] | None:
    with store._connect() as conn:
        row = conn.execute(
            "SELECT * FROM local_shifts WHERE local_id = ?", (int(local_id),)
        ).fetchone()
    return _row_to_public(row) if row else None


def _get_by_server_id(store: LocalStore, server_id: int) -> dict[str, Any] | None:
    with store._connect() as conn:
        row = conn.execute(
            "SELECT * FROM local_shifts WHERE server_id = ?", (int(server_id),)
        ).fetchone()
    return _row_to_public(row) if row else None


def _get_by_client_id(store: LocalStore, client_id: str) -> dict[str, Any] | None:
    with store._connect() as conn:
        row = conn.execute(
            "SELECT * FROM local_shifts WHERE client_id = ?", (client_id,)
        ).fetchone()
    return _row_to_public(row) if row else None


def resolve_shift(store: LocalStore, shift_id: int) -> dict[str, Any] | None:
    sid = int(shift_id)
    if sid < 0:
        return _get_by_local_id(store, -sid)
    return _get_by_server_id(store, sid)


def get_open_shift_local(store: LocalStore, tech_id: str) -> dict[str, Any] | None:
    tech_id = (tech_id or "").strip()
    if not tech_id:
        return None
    with store._connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM local_shifts
            WHERE tech_id = ? AND (ended_at IS NULL OR ended_at = '')
            ORDER BY local_id DESC LIMIT 1
            """,
            (tech_id,),
        ).fetchone()
    return _row_to_public(row) if row else None


def list_local_shifts(
    store: LocalStore,
    *,
    tech_id: str = "",
    day_from: str = "",
    day_to: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
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
    args.append(max(1, int(limit)))
    with store._connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM local_shifts{where} ORDER BY started_at DESC LIMIT ?",
            args,
        ).fetchall()
    return [_row_to_public(r) for r in rows]


def list_active_local(store: LocalStore) -> list[dict[str, Any]]:
    with store._connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM local_shifts
            WHERE ended_at IS NULL OR ended_at = ''
            ORDER BY started_at DESC
            """
        ).fetchall()
    return [_row_to_public(r) for r in rows]


def upsert_from_remote(store: LocalStore, shift: dict[str, Any]) -> dict[str, Any]:
    """Cache a server shift locally (does not mark pending)."""
    server_id = int(shift.get("id") or 0)
    if server_id <= 0:
        raise ValueError("server shift id required")
    tech_id = str(shift.get("tech_id") or "").strip()
    tech_name = str(shift.get("tech_name") or "").strip()
    day = str(shift.get("day") or "").strip()
    started_at = str(shift.get("started_at") or "").strip()
    ended_at = str(shift.get("ended_at") or "") or ""
    if not day and started_at:
        day = _local_day_for_timestamp(started_at)
    existing = _get_by_server_id(store, server_id)
    client_id = (existing or {}).get("client_id") or f"srv-{server_id}"
    with store._connect() as conn:
        if existing:
            conn.execute(
                """
                UPDATE local_shifts
                SET tech_id = ?, tech_name = ?, day = ?, started_at = ?,
                    ended_at = ?, pending_sync = 0, updated_at = ?
                WHERE server_id = ?
                """,
                (
                    tech_id,
                    tech_name,
                    day,
                    started_at,
                    ended_at,
                    now_iso(),
                    server_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO local_shifts (
                    client_id, server_id, tech_id, tech_name, day,
                    started_at, ended_at, pending_sync, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    client_id,
                    server_id,
                    tech_id,
                    tech_name,
                    day,
                    started_at,
                    ended_at,
                    now_iso(),
                ),
            )
    out = _get_by_server_id(store, server_id)
    assert out is not None
    return out


def start_shift_local(
    store: LocalStore,
    *,
    tech_id: str,
    tech_name: str = "",
    started_at: str = "",
    day: str = "",
) -> dict[str, Any]:
    tech_id = (tech_id or "").strip()
    if not tech_id:
        raise ValueError("tech_id required")
    open_row = get_open_shift_local(store, tech_id)
    if open_row:
        raise ValueError("Already on the clock — day-end first")
    if (started_at or "").strip():
        at = _normalize_iso(started_at)
    else:
        at = _normalize_iso(
            datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
        )
    day_s = (day or "").strip() or _local_day_for_timestamp(at)
    client_id = str(uuid.uuid4())
    with store._connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO local_shifts (
                client_id, server_id, tech_id, tech_name, day,
                started_at, ended_at, pending_sync, updated_at
            ) VALUES (?, NULL, ?, ?, ?, ?, '', 1, ?)
            """,
            (client_id, tech_id, (tech_name or "").strip() or tech_id, day_s, at, now_iso()),
        )
        local_id = int(cur.lastrowid or 0)
    _enqueue_op(
        store,
        "start",
        {
            "client_id": client_id,
            "local_id": local_id,
            "tech_id": tech_id,
            "tech_name": (tech_name or "").strip() or tech_id,
            "started_at": at,
            "day": day_s,
        },
    )
    out = _get_by_local_id(store, local_id)
    assert out is not None
    return out


def end_shift_local(
    store: LocalStore,
    *,
    tech_id: str = "",
    shift_id: int | None = None,
    ended_at: str = "",
) -> dict[str, Any]:
    target: dict[str, Any] | None = None
    if shift_id is not None:
        target = resolve_shift(store, int(shift_id))
        if not target:
            raise ValueError("Shift not found")
        if target.get("ended_at"):
            raise ValueError("Shift already ended — edit times instead")
    else:
        tech_id = (tech_id or "").strip()
        if not tech_id:
            raise ValueError("tech_id required")
        target = get_open_shift_local(store, tech_id)
        if not target:
            raise ValueError("Not on the clock")
    at = (
        _normalize_iso(ended_at)
        if (ended_at or "").strip()
        else _normalize_iso(
            datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
        )
    )
    started = str(target.get("started_at") or "")
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
    local_id = int(target["local_id"])
    with store._connect() as conn:
        conn.execute(
            """
            UPDATE local_shifts
            SET ended_at = ?, pending_sync = 1, updated_at = ?
            WHERE local_id = ?
            """,
            (at, now_iso(), local_id),
        )
    _enqueue_op(
        store,
        "end",
        {
            "client_id": target.get("client_id"),
            "local_id": local_id,
            "server_id": target.get("server_id"),
            "tech_id": target.get("tech_id"),
            "ended_at": at,
        },
    )
    out = _get_by_local_id(store, local_id)
    assert out is not None
    return out


def patch_shift_local(
    store: LocalStore,
    shift_id: int,
    *,
    started_at: str | None = None,
    ended_at: str | None = None,
    clear_end: bool = False,
    day: str | None = None,
) -> dict[str, Any]:
    target = resolve_shift(store, int(shift_id))
    if not target:
        raise ValueError("Shift not found")
    start = str(target.get("started_at") or "")
    end = str(target.get("ended_at") or "") or ""
    if started_at is not None and str(started_at).strip():
        start = _normalize_iso(str(started_at))
    if clear_end:
        other = get_open_shift_local(store, str(target.get("tech_id") or ""))
        if other and int(other["local_id"]) != int(target["local_id"]):
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
    day_s = (day or "").strip() if day is not None else ""
    if not day_s:
        day_s = _local_day_for_timestamp(start)
    local_id = int(target["local_id"])
    with store._connect() as conn:
        conn.execute(
            """
            UPDATE local_shifts
            SET started_at = ?, ended_at = ?, day = ?, pending_sync = 1, updated_at = ?
            WHERE local_id = ?
            """,
            (start, end, day_s, now_iso(), local_id),
        )
    # Only queue remote patch when we already have a server id
    if target.get("server_id"):
        _enqueue_op(
            store,
            "patch",
            {
                "client_id": target.get("client_id"),
                "local_id": local_id,
                "server_id": target.get("server_id"),
                "started_at": start,
                "ended_at": end or None,
                "clear_end": clear_end,
                "day": day_s,
            },
        )
    else:
        # Still offline-only: ensure start/end ops reflect corrected times.
        # Rewrite by enqueueing a patch that drain will skip until server_id exists;
        # start/end ops already carry timestamps — update local row is enough until sync.
        pass
    out = _get_by_local_id(store, local_id)
    assert out is not None
    return out


def delete_shift_local(store: LocalStore, shift_id: int) -> dict[str, Any]:
    target = resolve_shift(store, int(shift_id))
    if not target:
        raise ValueError("Shift not found")
    local_id = int(target["local_id"])
    server_id = target.get("server_id")
    with store._connect() as conn:
        conn.execute("DELETE FROM local_shifts WHERE local_id = ?", (local_id,))
        # Drop pending start/end for this client so we do not resurrect
        rows = conn.execute("SELECT id, op, payload FROM pending_shift_ops").fetchall()
        for row in rows:
            try:
                payload = json.loads(row["payload"] or "{}")
            except Exception:
                continue
            if payload.get("client_id") == target.get("client_id") or (
                payload.get("local_id") == local_id
            ):
                conn.execute(
                    "DELETE FROM pending_shift_ops WHERE id = ?", (int(row["id"]),)
                )
    if server_id:
        _enqueue_op(
            store,
            "delete",
            {"server_id": int(server_id), "client_id": target.get("client_id")},
        )
    return {"ok": True, "id": int(shift_id)}


def start_shift(
    store: LocalStore,
    *,
    tech_id: str,
    tech_name: str = "",
    started_at: str = "",
    day: str = "",
) -> dict[str, Any]:
    """Apply locally; push immediately when reachable; else queue."""
    remote = RemoteClient()
    local = start_shift_local(
        store,
        tech_id=tech_id,
        tech_name=tech_name,
        started_at=started_at,
        day=day,
    )
    if not remote.enabled:
        _mark_local_clean(store, int(local["local_id"]))
        _drop_ops_for_client(store, str(local.get("client_id") or ""))
        local = _get_by_local_id(store, int(local["local_id"])) or local
        local["pending_sync"] = False
        return {"ok": True, "shift": local, "synced": False, "reason": "no_server"}
    try:
        out = remote.start_shift(
            tech_id=tech_id,
            tech_name=tech_name or str(local.get("tech_name") or ""),
            started_at=str(local.get("started_at") or ""),
            day=str(local.get("day") or ""),
        )
        shift = out.get("shift") if isinstance(out, dict) else None
        if isinstance(shift, dict):
            _apply_server_id(store, local, shift)
            _drop_ops_for_client(store, str(local.get("client_id") or ""), ops=("start",))
            synced = upsert_from_remote(store, shift)
            return {"ok": True, "shift": synced, "synced": True}
        return {"ok": True, "shift": local, "synced": False}
    except RuntimeError as exc:
        # Business rule (already on clock) — surface to caller
        if "Already on the clock" in str(exc) or "already" in str(exc).lower():
            # Roll back local open we just created if server rejects
            with store._connect() as conn:
                conn.execute(
                    "DELETE FROM local_shifts WHERE local_id = ?",
                    (int(local["local_id"]),),
                )
            _drop_ops_for_client(store, str(local.get("client_id") or ""))
            raise
        # Network-ish wrapped as RuntimeError from HTTP body — keep queued
        log.info("shift start deferred: %s", exc)
        return {"ok": True, "shift": local, "synced": False, "pending": True}
    except Exception as exc:
        log.info("shift start queued offline: %s", exc)
        return {"ok": True, "shift": local, "synced": False, "pending": True}


def end_shift(
    store: LocalStore,
    *,
    tech_id: str = "",
    shift_id: int | None = None,
    ended_at: str = "",
) -> dict[str, Any]:
    remote = RemoteClient()
    local = end_shift_local(
        store, tech_id=tech_id, shift_id=shift_id, ended_at=ended_at
    )
    if not remote.enabled:
        _mark_local_clean(store, int(local["local_id"]))
        _drop_ops_for_client(store, str(local.get("client_id") or ""), ops=("end",))
        local = _get_by_local_id(store, int(local["local_id"])) or local
        local["pending_sync"] = False
        return {"ok": True, "shift": local, "synced": False, "reason": "no_server"}
    server_id = local.get("server_id")
    try:
        out = remote.end_shift(
            tech_id=str(local.get("tech_id") or tech_id or ""),
            shift_id=int(server_id) if server_id else None,
            ended_at=str(local.get("ended_at") or ""),
        )
        shift = out.get("shift") if isinstance(out, dict) else None
        if isinstance(shift, dict):
            synced = upsert_from_remote(store, shift)
            _drop_ops_for_client(store, str(local.get("client_id") or ""), ops=("end",))
            return {"ok": True, "shift": synced, "synced": True}
        return {"ok": True, "shift": local, "synced": False}
    except RuntimeError as exc:
        if "Not on the clock" in str(exc) or "already ended" in str(exc).lower():
            raise
        log.info("shift end deferred: %s", exc)
        return {"ok": True, "shift": local, "synced": False, "pending": True}
    except Exception as exc:
        log.info("shift end queued offline: %s", exc)
        return {"ok": True, "shift": local, "synced": False, "pending": True}


def _apply_server_id(
    store: LocalStore, local: dict[str, Any], remote_shift: dict[str, Any]
) -> None:
    server_id = int(remote_shift.get("id") or 0)
    if server_id <= 0:
        return
    with store._connect() as conn:
        conn.execute(
            """
            UPDATE local_shifts
            SET server_id = ?, pending_sync = 0, updated_at = ?,
                started_at = COALESCE(?, started_at),
                ended_at = COALESCE(?, ended_at),
                day = COALESCE(?, day),
                tech_name = COALESCE(?, tech_name)
            WHERE local_id = ?
            """,
            (
                server_id,
                now_iso(),
                remote_shift.get("started_at"),
                remote_shift.get("ended_at") or "",
                remote_shift.get("day"),
                remote_shift.get("tech_name"),
                int(local["local_id"]),
            ),
        )


def _mark_local_clean(store: LocalStore, local_id: int) -> None:
    with store._connect() as conn:
        conn.execute(
            "UPDATE local_shifts SET pending_sync = 0, updated_at = ? WHERE local_id = ?",
            (now_iso(), int(local_id)),
        )


def _drop_ops_for_client(
    store: LocalStore, client_id: str, ops: tuple[str, ...] | None = None
) -> None:
    if not client_id:
        return
    with store._connect() as conn:
        rows = conn.execute("SELECT id, op, payload FROM pending_shift_ops").fetchall()
        for row in rows:
            if ops and str(row["op"]) not in ops:
                continue
            try:
                payload = json.loads(row["payload"] or "{}")
            except Exception:
                continue
            if payload.get("client_id") == client_id:
                conn.execute(
                    "DELETE FROM pending_shift_ops WHERE id = ?", (int(row["id"]),)
                )


def try_push_pending_shifts(
    store: LocalStore, remote: RemoteClient | None = None
) -> dict[str, Any]:
    """Drain pending_shift_ops in order, preserving original timestamps."""
    remote = remote or RemoteClient()
    if not remote.enabled:
        return {"ok": True, "skipped": True, "cleared": 0, "failed": 0}
    with store._connect() as conn:
        rows = conn.execute(
            "SELECT id, client_op_id, op, payload FROM pending_shift_ops ORDER BY id ASC"
        ).fetchall()
        ops = [
            {
                "id": int(r["id"]),
                "client_op_id": r["client_op_id"],
                "op": r["op"],
                "payload": json.loads(r["payload"] or "{}"),
            }
            for r in rows
        ]
    cleared = 0
    failed = 0
    for item in ops:
        op = str(item["op"])
        payload = item["payload"] if isinstance(item["payload"], dict) else {}
        try:
            if op == "start":
                _drain_start(store, remote, payload)
            elif op == "end":
                _drain_end(store, remote, payload)
            elif op == "patch":
                _drain_patch(store, remote, payload)
            elif op == "delete":
                sid = int(payload.get("server_id") or 0)
                if sid > 0:
                    remote.delete_shift(sid)
            else:
                log.warning("unknown shift op %s", op)
            with store._connect() as conn:
                conn.execute(
                    "DELETE FROM pending_shift_ops WHERE id = ?", (int(item["id"]),)
                )
            cleared += 1
        except Exception as exc:
            failed += 1
            log.warning("pending shift op %s failed (will retry): %s", op, exc)
            # Stop ordered drain on first failure to preserve start-before-end
            break
    return {"ok": failed == 0, "cleared": cleared, "failed": failed}


def _drain_start(
    store: LocalStore, remote: RemoteClient, payload: dict[str, Any]
) -> None:
    client_id = str(payload.get("client_id") or "")
    local = _get_by_client_id(store, client_id) if client_id else None
    try:
        out = remote.start_shift(
            tech_id=str(payload.get("tech_id") or ""),
            tech_name=str(payload.get("tech_name") or ""),
            started_at=str(payload.get("started_at") or ""),
            day=str(payload.get("day") or ""),
        )
        shift = out.get("shift") if isinstance(out, dict) else None
        if isinstance(shift, dict) and local:
            _apply_server_id(store, local, shift)
            upsert_from_remote(store, {**shift, **{"id": shift.get("id")}})
        elif isinstance(shift, dict):
            upsert_from_remote(store, shift)
    except RuntimeError as exc:
        msg = str(exc)
        if "Already on the clock" in msg or "already" in msg.lower():
            # Adopt server open shift
            tech_id = str(payload.get("tech_id") or "")
            open_remote = remote.get_open_shift(tech_id)
            shift = open_remote.get("shift") if isinstance(open_remote, dict) else None
            if isinstance(shift, dict) and local:
                _apply_server_id(store, local, shift)
                upsert_from_remote(store, shift)
            elif isinstance(shift, dict):
                upsert_from_remote(store, shift)
            else:
                raise
        else:
            raise


def _drain_end(store: LocalStore, remote: RemoteClient, payload: dict[str, Any]) -> None:
    client_id = str(payload.get("client_id") or "")
    local = _get_by_client_id(store, client_id) if client_id else None
    server_id = payload.get("server_id") or (local or {}).get("server_id")
    if not server_id and local:
        # Start may have just assigned server_id
        server_id = local.get("server_id")
    if not server_id:
        tech_id = str(payload.get("tech_id") or (local or {}).get("tech_id") or "")
        open_remote = remote.get_open_shift(tech_id)
        shift = open_remote.get("shift") if isinstance(open_remote, dict) else None
        if isinstance(shift, dict):
            server_id = shift.get("id")
            if local:
                _apply_server_id(store, local, shift)
    ended_at = str(payload.get("ended_at") or "")
    out = remote.end_shift(
        tech_id=str(payload.get("tech_id") or ""),
        shift_id=int(server_id) if server_id else None,
        ended_at=ended_at,
    )
    shift = out.get("shift") if isinstance(out, dict) else None
    if isinstance(shift, dict):
        upsert_from_remote(store, shift)
    elif local:
        _mark_local_clean(store, int(local["local_id"]))


def _drain_patch(
    store: LocalStore, remote: RemoteClient, payload: dict[str, Any]
) -> None:
    server_id = int(payload.get("server_id") or 0)
    if server_id <= 0:
        return
    clear_end = bool(payload.get("clear_end"))
    remote.update_shift(
        server_id,
        started_at=payload.get("started_at"),
        ended_at=payload.get("ended_at"),
        clear_end=clear_end,
        day=payload.get("day"),
        edited_by="offline-sync",
    )
    client_id = str(payload.get("client_id") or "")
    local = _get_by_client_id(store, client_id) if client_id else None
    if local:
        _mark_local_clean(store, int(local["local_id"]))


def get_open_shift(
    store: LocalStore, tech_id: str, *, prefer_remote: bool = True
) -> dict[str, Any]:
    """Return {shift} merging remote when reachable."""
    remote = RemoteClient()
    local = get_open_shift_local(store, tech_id)
    if prefer_remote and remote.enabled:
        try:
            remote_out = remote.get_open_shift(tech_id)
            shift = remote_out.get("shift") if isinstance(remote_out, dict) else None
            if isinstance(shift, dict):
                cached = upsert_from_remote(store, shift)
                # Prefer local pending open if it is not yet on server
                if local and local.get("pending_sync") and not local.get("server_id"):
                    return {"shift": local, "offline": False}
                return {"shift": cached, "offline": False}
            if shift is None:
                # Server says no open — keep local pending start
                if local and not local.get("ended_at"):
                    return {"shift": local, "offline": False}
                return {"shift": None, "offline": False}
        except Exception:
            pass
    return {"shift": local, "offline": True if remote.enabled else False}


def list_shifts_merged(
    store: LocalStore,
    *,
    tech_id: str = "",
    day_from: str = "",
    day_to: str = "",
    limit: int = 200,
) -> dict[str, Any]:
    remote = RemoteClient()
    local_rows = list_local_shifts(
        store, tech_id=tech_id, day_from=day_from, day_to=day_to, limit=limit
    )
    if remote.enabled:
        try:
            remote_out = remote.list_shifts(
                tech_id=tech_id, day_from=day_from, day_to=day_to, limit=limit
            )
            remote_rows = list(remote_out.get("shifts") or [])
            by_key: dict[str, dict[str, Any]] = {}
            for s in remote_rows:
                if not isinstance(s, dict):
                    continue
                cached = upsert_from_remote(store, s)
                key = f"s:{cached.get('server_id')}"
                by_key[key] = cached
            for s in local_rows:
                if s.get("server_id"):
                    key = f"s:{s['server_id']}"
                    # Prefer local if pending (edits not yet pushed)
                    if s.get("pending_sync"):
                        by_key[key] = s
                    elif key not in by_key:
                        by_key[key] = s
                else:
                    by_key[f"c:{s.get('client_id')}"] = s
            merged = sorted(
                by_key.values(),
                key=lambda x: str(x.get("started_at") or ""),
                reverse=True,
            )[: max(1, int(limit))]
            return {"shifts": merged, "offline": False}
        except Exception:
            return {"shifts": local_rows, "offline": True}
    return {"shifts": local_rows, "offline": False, "reason": "no_server"}


def list_active_merged(store: LocalStore) -> dict[str, Any]:
    remote = RemoteClient()
    local_rows = list_active_local(store)
    if remote.enabled:
        try:
            remote_out = remote.list_active_shifts()
            remote_rows = list(remote_out.get("shifts") or [])
            by_tech: dict[str, dict[str, Any]] = {}
            for s in remote_rows:
                if isinstance(s, dict):
                    cached = upsert_from_remote(store, s)
                    by_tech[str(cached.get("tech_id") or "")] = cached
            for s in local_rows:
                tid = str(s.get("tech_id") or "")
                if s.get("pending_sync") and not s.get("server_id"):
                    by_tech[tid] = s
                elif tid not in by_tech:
                    by_tech[tid] = s
            return {"shifts": list(by_tech.values()), "offline": False}
        except Exception:
            return {"shifts": local_rows, "offline": True}
    return {"shifts": local_rows, "offline": False, "reason": "no_server"}
