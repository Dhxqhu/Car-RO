"""Offline message outbox + soft-fail inbox cache."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from carro.core.db import LocalStore
from carro.core.models import now_iso
from carro.storage.remote import RemoteClient

log = logging.getLogger("carro.message_offline")


def _cache_get(store: LocalStore, key: str) -> dict[str, Any] | None:
    with store._connect() as conn:
        row = conn.execute(
            "SELECT data FROM message_cache WHERE cache_key = ?", (key,)
        ).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row["data"] or "{}")
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _cache_set(store: LocalStore, key: str, data: dict[str, Any]) -> None:
    with store._connect() as conn:
        conn.execute(
            """
            INSERT INTO message_cache (cache_key, data, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                data = excluded.data,
                updated_at = excluded.updated_at
            """,
            (key, json.dumps(data), now_iso()),
        )


def list_inbox(
    store: LocalStore,
    *,
    me_id: str,
    unread: bool = False,
    limit: int = 100,
) -> dict[str, Any]:
    remote = RemoteClient()
    key = f"inbox:{me_id}"
    if not remote.enabled:
        cached = _cache_get(store, key) or {"messages": []}
        pending = _pending_as_messages(store, me_id)
        msgs = list(cached.get("messages") or []) + pending
        if unread:
            msgs = [m for m in msgs if not m.get("read_at")]
        return {
            "messages": msgs[: max(1, int(limit))],
            "offline": False,
            "reason": "no_server",
            "note": "Shop messaging needs server_url.",
        }
    try:
        out = remote.list_messages(for_id=me_id, unread=unread, limit=limit)
        if isinstance(out, dict):
            _cache_set(store, key, out)
            # Append not-yet-synced outbound that belong in threads is handled in sent
            out = dict(out)
            out["offline"] = False
            return out
    except Exception as exc:
        log.info("inbox offline: %s", exc)
        cached = _cache_get(store, key) or {"messages": []}
        return {
            "messages": list(cached.get("messages") or [])[: max(1, int(limit))],
            "offline": True,
            "note": "Shop server unreachable — showing cached inbox. New messages sync on reconnect.",
        }
    return {"messages": [], "offline": True}


def list_sent(
    store: LocalStore,
    *,
    me_id: str,
    limit: int = 100,
) -> dict[str, Any]:
    remote = RemoteClient()
    key = f"sent:{me_id}"
    pending = _pending_as_messages(store, me_id)
    if not remote.enabled:
        cached = _cache_get(store, key) or {"messages": []}
        msgs = pending + list(cached.get("messages") or [])
        return {
            "messages": msgs[: max(1, int(limit))],
            "offline": False,
            "reason": "no_server",
        }
    try:
        out = remote.list_sent_messages(from_id=me_id, limit=limit)
        if isinstance(out, dict):
            _cache_set(store, key, out)
            merged = pending + list(out.get("messages") or [])
            return {
                "messages": merged[: max(1, int(limit))],
                "offline": False,
            }
    except Exception as exc:
        log.info("sent messages offline: %s", exc)
        cached = _cache_get(store, key) or {"messages": []}
        merged = pending + list(cached.get("messages") or [])
        return {
            "messages": merged[: max(1, int(limit))],
            "offline": True,
            "note": "Shop server unreachable — showing cached sent + queued messages.",
        }
    return {"messages": pending, "offline": True}


def _pending_as_messages(store: LocalStore, me_id: str) -> list[dict[str, Any]]:
    with store._connect() as conn:
        rows = conn.execute(
            "SELECT client_id, payload, created_at FROM pending_messages ORDER BY created_at ASC"
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            continue
        if str(payload.get("from_id") or "") != me_id:
            continue
        out.append(
            {
                "id": -abs(hash(str(row["client_id"]))) % 2_000_000_000 or -1,
                "client_id": str(row["client_id"]),
                "body": payload.get("body") or "",
                "from_id": payload.get("from_id"),
                "from_name": payload.get("from_name"),
                "from_role": payload.get("from_role"),
                "to_id": payload.get("to_id"),
                "to_name": payload.get("to_name"),
                "to_role": payload.get("to_role"),
                "ro_id": payload.get("ro_id") or "",
                "work_item_id": payload.get("work_item_id") or "",
                "reply_to": payload.get("reply_to"),
                "at": payload.get("at") or row["created_at"],
                "pending_sync": True,
            }
        )
    return out


def send_message(
    store: LocalStore,
    payload: dict[str, Any],
) -> dict[str, Any]:
    remote = RemoteClient()
    body = dict(payload)
    if not body.get("at"):
        body["at"] = now_iso()
    client_id = str(uuid.uuid4())
    if not remote.enabled:
        raise ValueError(
            "Shop messaging needs a server_url — messages are shared across bay PCs."
        )
    try:
        out = remote.send_message(body)
        # Refresh sent cache opportunistically
        me_id = str(body.get("from_id") or "")
        if me_id and isinstance(out, dict):
            try:
                sent = remote.list_sent_messages(from_id=me_id, limit=100)
                if isinstance(sent, dict):
                    _cache_set(store, f"sent:{me_id}", sent)
            except Exception:
                pass
        return out if isinstance(out, dict) else {"ok": True, "message": out}
    except Exception as exc:
        log.info("message queued offline: %s", exc)
        with store._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_messages (client_id, payload, created_at)
                VALUES (?, ?, ?)
                """,
                (client_id, json.dumps(body), now_iso()),
            )
        optimistic = {
            "id": -abs(hash(client_id)) % 2_000_000_000 or -1,
            "client_id": client_id,
            "body": body.get("body") or "",
            "from_id": body.get("from_id"),
            "from_name": body.get("from_name"),
            "from_role": body.get("from_role"),
            "to_id": body.get("to_id"),
            "to_name": body.get("to_name"),
            "to_role": body.get("to_role"),
            "ro_id": body.get("ro_id") or "",
            "work_item_id": body.get("work_item_id") or "",
            "reply_to": body.get("reply_to"),
            "at": body.get("at"),
            "pending_sync": True,
        }
        return {
            "ok": True,
            "message": optimistic,
            "pending_sync": True,
            "note": "Queued — will send when shop server is reachable.",
        }


def mark_read(
    store: LocalStore,
    message_id: int,
    *,
    for_id: str,
) -> dict[str, Any]:
    remote = RemoteClient()
    if not remote.enabled:
        raise ValueError("Shop messaging needs a server_url")
    try:
        return remote.mark_message_read(message_id, for_id=for_id)
    except Exception as exc:
        log.info("read ack queued: %s", exc)
        with store._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_message_acks (kind, payload, created_at)
                VALUES (?, ?, ?)
                """,
                (
                    "read",
                    json.dumps({"message_id": int(message_id), "for_id": for_id}),
                    now_iso(),
                ),
            )
        return {
            "ok": True,
            "pending_sync": True,
            "note": "Read ack queued until reconnect.",
        }


def mark_delivered(
    store: LocalStore,
    message_ids: list[int],
    *,
    for_id: str,
) -> dict[str, Any]:
    remote = RemoteClient()
    ids = [int(x) for x in message_ids if int(x) > 0]
    if not ids:
        return {"ok": True, "messages": [], "count": 0}
    if not remote.enabled:
        return {"ok": True, "messages": [], "count": 0, "reason": "no_server"}
    try:
        return remote.mark_messages_delivered(ids, for_id=for_id)
    except Exception as exc:
        detail = str(exc)
        if "404" in detail or "Not Found" in detail:
            return {
                "ok": True,
                "messages": [],
                "count": 0,
                "note": "delivered ack unsupported",
            }
        log.info("delivered ack queued: %s", exc)
        with store._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_message_acks (kind, payload, created_at)
                VALUES (?, ?, ?)
                """,
                (
                    "delivered",
                    json.dumps({"ids": ids, "for_id": for_id}),
                    now_iso(),
                ),
            )
        return {
            "ok": True,
            "messages": [],
            "count": 0,
            "pending_sync": True,
        }


def try_push_pending_messages(
    store: LocalStore, remote: RemoteClient | None = None
) -> dict[str, Any]:
    remote = remote or RemoteClient()
    if not remote.enabled:
        return {"ok": True, "skipped": True, "cleared": 0, "failed": 0}
    cleared = 0
    failed = 0
    with store._connect() as conn:
        msg_rows = conn.execute(
            "SELECT client_id, payload FROM pending_messages ORDER BY created_at ASC"
        ).fetchall()
        ack_rows = conn.execute(
            "SELECT id, kind, payload FROM pending_message_acks ORDER BY id ASC"
        ).fetchall()
    for row in msg_rows:
        client_id = str(row["client_id"])
        try:
            payload = json.loads(row["payload"] or "{}")
            remote.send_message(payload)
            with store._connect() as conn:
                conn.execute(
                    "DELETE FROM pending_messages WHERE client_id = ?", (client_id,)
                )
            cleared += 1
        except Exception as exc:
            failed += 1
            log.warning("pending message %s failed: %s", client_id, exc)
            break
    for row in ack_rows:
        try:
            payload = json.loads(row["payload"] or "{}")
            kind = str(row["kind"])
            if kind == "read":
                remote.mark_message_read(
                    int(payload.get("message_id") or 0),
                    for_id=str(payload.get("for_id") or ""),
                )
            elif kind == "delivered":
                remote.mark_messages_delivered(
                    list(payload.get("ids") or []),
                    for_id=str(payload.get("for_id") or ""),
                )
            with store._connect() as conn:
                conn.execute(
                    "DELETE FROM pending_message_acks WHERE id = ?",
                    (int(row["id"]),),
                )
            cleared += 1
        except Exception as exc:
            failed += 1
            log.warning("pending message ack failed: %s", exc)
            break
    return {"ok": failed == 0, "cleared": cleared, "failed": failed}
