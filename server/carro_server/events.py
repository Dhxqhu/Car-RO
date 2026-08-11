"""Server-side RO event log for advisor/tech live updates."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any


def ensure_events_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ro_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TEXT NOT NULL,
            type TEXT NOT NULL,
            ro_id TEXT NOT NULL,
            item_id TEXT,
            actor TEXT,
            summary TEXT,
            payload TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ro_events_at ON ro_events(at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ro_events_ro ON ro_events(ro_id, at DESC)"
    )


def now_iso() -> str:
    # Match shop RO timestamps (local wall clock), not UTC — bell display
    # used to look ~4h ahead in US Eastern when this was timezone.utc.
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def append_event(
    conn: sqlite3.Connection,
    *,
    type: str,
    ro_id: str,
    item_id: str = "",
    actor: str = "",
    summary: str = "",
    payload: dict[str, Any] | None = None,
    at: str | None = None,
) -> int:
    ensure_events_table(conn)
    cur = conn.execute(
        """
        INSERT INTO ro_events (at, type, ro_id, item_id, actor, summary, payload)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            at or now_iso(),
            type,
            ro_id,
            item_id or "",
            actor or "",
            (summary or "")[:240],
            json.dumps(payload or {}),
        ),
    )
    return int(cur.lastrowid or 0)


def diff_ro_events(
    before: dict[str, Any] | None,
    after: dict[str, Any],
    *,
    actor: str = "",
) -> list[dict[str, Any]]:
    """Build event records from before/after RO JSON (no carro.core dependency)."""
    ro_id = str(after.get("id") or "")
    at = now_iso()
    events: list[dict[str, Any]] = []
    if before is None:
        events.append(
            {
                "type": "ro_created",
                "ro_id": ro_id,
                "item_id": "",
                "actor": actor,
                "at": at,
                "summary": f"Created {ro_id}",
            }
        )
    else:
        if (
            str(before.get("assigned_to_id") or "") != str(after.get("assigned_to_id") or "")
            or str(before.get("assigned_to_name") or "")
            != str(after.get("assigned_to_name") or "")
        ):
            who = (
                str(after.get("assigned_to_name") or after.get("assigned_to_id") or "unassigned")
            ).strip()
            events.append(
                {
                    "type": "ro_assigned",
                    "ro_id": ro_id,
                    "item_id": "",
                    "actor": actor,
                    "at": at,
                    "summary": who,
                }
            )

        b_cur = (
            str(before.get("current_tech_id") or ""),
            str(before.get("current_tech_name") or ""),
        )
        a_cur = (
            str(after.get("current_tech_id") or ""),
            str(after.get("current_tech_name") or ""),
        )
        if b_cur != a_cur:
            if a_cur[0] or a_cur[1]:
                events.append(
                    {
                        "type": "ro_current_started",
                        "ro_id": ro_id,
                        "item_id": "",
                        "actor": actor,
                        "at": at,
                        "summary": (a_cur[1] or a_cur[0]).strip(),
                    }
                )
            else:
                events.append(
                    {
                        "type": "ro_current_cleared",
                        "ro_id": ro_id,
                        "item_id": "",
                        "actor": actor,
                        "at": at,
                        "summary": (b_cur[1] or b_cur[0] or "cleared").strip(),
                    }
                )

        b_status = str(before.get("status") or "")
        a_status = str(after.get("status") or "")
        if b_status != a_status:
            if a_status == "waiting_customer":
                who = str(
                    after.get("approval_requested_by")
                    or after.get("approval_requested_by_id")
                    or actor
                    or ""
                ).strip()
                events.append(
                    {
                        "type": "ro_approval_requested",
                        "ro_id": ro_id,
                        "item_id": "",
                        "actor": actor,
                        "at": at,
                        "summary": who or "Customer approval requested",
                    }
                )
            elif a_status == "done":
                events.append(
                    {
                        "type": "ro_ready_to_bill",
                        "ro_id": ro_id,
                        "item_id": "",
                        "actor": actor,
                        "at": at,
                        "summary": "Ready for advisor billing",
                    }
                )
            elif a_status == "billed_out":
                events.append(
                    {
                        "type": "ro_billed_out",
                        "ro_id": ro_id,
                        "item_id": "",
                        "actor": actor,
                        "at": at,
                        "summary": "Billed out / closed",
                    }
                )
            elif b_status in ("done", "billed_out") and a_status not in (
                "done",
                "billed_out",
            ):
                events.append(
                    {
                        "type": "ro_reopened",
                        "ro_id": ro_id,
                        "item_id": "",
                        "actor": actor,
                        "at": at,
                        "summary": f"Reopened ({b_status} → {a_status})",
                    }
                )
            elif a_status == "waiting_parts":
                who = str(
                    after.get("parts_requested_by")
                    or after.get("parts_requested_by_id")
                    or actor
                    or ""
                ).strip()
                events.append(
                    {
                        "type": "ro_parts_requested",
                        "ro_id": ro_id,
                        "item_id": "",
                        "actor": actor,
                        "at": at,
                        "summary": who or "Parts order requested",
                    }
                )
            else:
                events.append(
                    {
                        "type": "ro_status_changed",
                        "ro_id": ro_id,
                        "item_id": "",
                        "actor": actor,
                        "at": at,
                        "summary": f"{b_status or '—'} → {a_status or '—'}",
                    }
                )

        for key in ("vin", "mileage", "year", "make", "model", "plate"):
            if str(before.get(key) or "") != str(after.get(key) or ""):
                events.append(
                    {
                        "type": "ro_vehicle_updated",
                        "ro_id": ro_id,
                        "item_id": "",
                        "actor": actor,
                        "at": at,
                        "summary": f"{key}: {before.get(key) or '—'} → {after.get(key) or '—'}",
                    }
                )
                break

        if bool(before.get("waiter")) != bool(after.get("waiter")):
            events.append(
                {
                    "type": "ro_waiter_flag",
                    "ro_id": ro_id,
                    "item_id": "",
                    "actor": actor,
                    "at": at,
                    "summary": "Waiter on" if after.get("waiter") else "Waiter off",
                }
            )
        if bool(before.get("urgent")) != bool(after.get("urgent")):
            events.append(
                {
                    "type": "ro_urgent_flag",
                    "ro_id": ro_id,
                    "item_id": "",
                    "actor": actor,
                    "at": at,
                    "summary": "Urgent on" if after.get("urgent") else "Urgent off",
                }
            )

    b_items = {
        str(it.get("id")): it
        for it in (before or {}).get("work_items") or []
        if isinstance(it, dict) and it.get("id")
    }
    a_items = {
        str(it.get("id")): it
        for it in after.get("work_items") or []
        if isinstance(it, dict) and it.get("id")
    }
    for wid, w in a_items.items():
        if wid not in b_items:
            events.append(
                {
                    "type": "item_added",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": at,
                    "summary": str(w.get("concern") or wid)[:120],
                }
            )
            # New item created already assigned (e.g. found-issue approve → tech)
            # must also emit item_assigned so the tech bell can route it.
            aid = str(w.get("assigned_to_id") or "").strip()
            aname = str(w.get("assigned_to_name") or "").strip()
            if aid or aname:
                who = (aname or aid or "unassigned").strip()
                events.append(
                    {
                        "type": "item_assigned",
                        "ro_id": ro_id,
                        "item_id": wid,
                        "actor": actor,
                        "at": at,
                        "summary": who,
                        "payload": {
                            "assigned_to_id": aid,
                            "assigned_to_name": aname,
                        },
                    }
                )
            continue
        old = b_items[wid]
        if str(old.get("concern") or "") != str(w.get("concern") or ""):
            events.append(
                {
                    "type": "item_concern_updated",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": at,
                    "summary": str(w.get("concern") or "")[:120],
                }
            )
        if str(old.get("notes") or "") != str(w.get("notes") or ""):
            events.append(
                {
                    "type": "item_notes_updated",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": at,
                    "summary": str(w.get("notes") or "")[:120],
                }
            )
        if str(old.get("status") or "") != str(w.get("status") or ""):
            old_st = str(old.get("status") or "").strip().lower()
            new_st = str(w.get("status") or "").strip().lower()
            events.append(
                {
                    "type": "item_status_changed",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": at,
                    "summary": f"{old.get('status')} → {w.get('status')}",
                }
            )
            # Wait cleared (parts in / customer approved) → notify assignee only when reassigned.
            if old_st in ("waiting_parts", "waiting_customer") and new_st == "open":
                who = str(
                    w.get("assigned_to_name") or w.get("assigned_to_id") or ""
                ).strip()
                concern = str(w.get("concern") or wid)[:80]
                reason = (
                    "Parts received"
                    if old_st == "waiting_parts"
                    else "Customer approved"
                )
                events.append(
                    {
                        "type": "item_wait_cleared",
                        "ro_id": ro_id,
                        "item_id": wid,
                        "actor": actor,
                        "at": at,
                        "summary": (
                            f"{reason} · {who} · {concern}"
                            if who
                            else f"{reason} · Unassigned · {concern}"
                        ),
                        "payload": {
                            "assigned_to_id": str(w.get("assigned_to_id") or ""),
                            "assigned_to_name": str(w.get("assigned_to_name") or ""),
                            "from_status": old_st,
                        },
                    }
                )
        if (
            str(old.get("assigned_to_id") or "") != str(w.get("assigned_to_id") or "")
            or str(old.get("assigned_to_name") or "") != str(w.get("assigned_to_name") or "")
        ):
            who = str(w.get("assigned_to_name") or w.get("assigned_to_id") or "unassigned").strip()
            events.append(
                {
                    "type": "item_assigned",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": at,
                    "summary": who,
                    "payload": {
                        "assigned_to_id": str(w.get("assigned_to_id") or ""),
                        "assigned_to_name": str(w.get("assigned_to_name") or ""),
                    },
                }
            )
        old_eod = bool(old.get("due_eod"))
        new_eod = bool(w.get("due_eod"))
        if not old_eod and new_eod:
            who = str(w.get("assigned_to_name") or w.get("assigned_to_id") or "").strip()
            concern = str(w.get("concern") or wid)[:80]
            events.append(
                {
                    "type": "item_due_eod",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": at,
                    "summary": (
                        f"Needs done by end of day · {who} · {concern}"
                        if who
                        else f"Needs done by end of day · {concern}"
                    ),
                    "payload": {
                        "assigned_to_id": str(w.get("assigned_to_id") or ""),
                        "assigned_to_name": str(w.get("assigned_to_name") or ""),
                    },
                }
            )
        old_req = old.get("next_day_request") if isinstance(old.get("next_day_request"), dict) else {}
        new_req = w.get("next_day_request") if isinstance(w.get("next_day_request"), dict) else {}
        old_req_st = str(old_req.get("status") or "")
        new_req_st = str(new_req.get("status") or "")
        if old_req_st != new_req_st and new_req_st == "pending":
            who = str(new_req.get("by") or actor or "").strip()
            who_id = str(new_req.get("by_id") or "").strip()
            concern = str(w.get("concern") or wid)[:80]
            if bool(w.get("due_eod")) or bool(old.get("due_eod")):
                summary = (
                    f"EOD job — {who or 'Tech'} requested next day · {concern} "
                    "— contact customer if needed"
                )
            else:
                summary = f"{who or 'Tech'} requested next day · {concern}"
            events.append(
                {
                    "type": "next_day_requested",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": at,
                    "summary": summary,
                    "payload": {
                        "requested_by_id": who_id,
                        "requested_by_name": who,
                        "assigned_to_id": str(w.get("assigned_to_id") or ""),
                        "assigned_to_name": str(w.get("assigned_to_name") or ""),
                    },
                }
            )
        elif old_req_st != new_req_st and new_req_st == "approved":
            by_id = str(new_req.get("by_id") or "").strip()
            by_name = str(new_req.get("by") or "").strip()
            events.append(
                {
                    "type": "next_day_approved",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": at,
                    "summary": f"Next day approved · {str(w.get('concern') or wid)[:80]}",
                    "payload": {
                        "requested_by_id": by_id,
                        "requested_by_name": by_name,
                        "to_id": by_id or str(w.get("assigned_to_id") or ""),
                        "assigned_to_id": str(w.get("assigned_to_id") or ""),
                        "assigned_to_name": str(w.get("assigned_to_name") or ""),
                    },
                }
            )
        elif old_req_st != new_req_st and new_req_st == "declined":
            by_id = str(new_req.get("by_id") or "").strip()
            by_name = str(new_req.get("by") or "").strip()
            events.append(
                {
                    "type": "next_day_declined",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": at,
                    "summary": f"Next day declined · {str(w.get('concern') or wid)[:80]}",
                    "payload": {
                        "requested_by_id": by_id,
                        "requested_by_name": by_name,
                        "to_id": by_id or str(w.get("assigned_to_id") or ""),
                        "assigned_to_id": str(w.get("assigned_to_id") or ""),
                        "assigned_to_name": str(w.get("assigned_to_name") or ""),
                    },
                }
            )
        old_lane = str(old.get("queue_lane") or "daily")
        new_lane = str(w.get("queue_lane") or "daily")
        if old_lane != new_lane:
            events.append(
                {
                    "type": "item_queue_lane",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": at,
                    "summary": f"{old_lane} → {new_lane}",
                }
            )
    for wid in b_items:
        if wid not in a_items:
            events.append(
                {
                    "type": "item_removed",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": at,
                    "summary": wid,
                }
            )

    # Advisor merge: one item_merged event; drop per-source item_removed noise.
    b_actions = (before or {}).get("advisor_actions") if before else None
    a_actions = after.get("advisor_actions")
    b_action_n = len(b_actions) if isinstance(b_actions, list) else 0
    if isinstance(a_actions, list) and len(a_actions) > b_action_n:
        for entry in a_actions[b_action_n:]:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("action") or "") != "item_merged":
                continue
            target = str(entry.get("work_item_id") or "").strip()
            detail = str(entry.get("detail") or "").strip()
            sources = [s.strip() for s in detail.split(",") if s.strip()]
            events.append(
                {
                    "type": "item_merged",
                    "ro_id": ro_id,
                    "item_id": target,
                    "actor": actor or str(entry.get("advisor_name") or ""),
                    "at": at,
                    "summary": str(entry.get("note") or f"{detail} → {target}")[:160],
                }
            )
            if sources:
                events = [
                    e
                    for e in events
                    if not (
                        e.get("type") == "item_removed"
                        and str(e.get("item_id") or "") in sources
                    )
                ]

    def _fi_map(raw: object) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        if not isinstance(raw, list):
            return out
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            fid = str(entry.get("id") or "").strip()
            if fid:
                out[fid] = entry
        return out

    b_fi = _fi_map((before or {}).get("found_issues") if before else None)
    a_fi = _fi_map(after.get("found_issues"))
    for fid, fi in a_fi.items():
        new_st = str(fi.get("status") or "").strip().lower()
        if fid not in b_fi:
            # Drafts stay quiet until the tech forwards them to the advisor.
            if new_st == "draft":
                continue
            if new_st == "pending":
                events.append(
                    {
                        "type": "found_issue_created",
                        "ro_id": ro_id,
                        "item_id": fid,
                        "actor": actor,
                        "at": at,
                        "summary": str(fi.get("description") or fid)[:120],
                    }
                )
            continue
        old = b_fi[fid]
        old_st = str(old.get("status") or "").strip().lower()
        if old_st != new_st and old_st == "draft" and new_st == "pending":
            events.append(
                {
                    "type": "found_issue_created",
                    "ro_id": ro_id,
                    "item_id": fid,
                    "actor": actor,
                    "at": at,
                    "summary": str(fi.get("description") or fid)[:120],
                }
            )
        elif old_st != new_st and new_st == "converted":
            events.append(
                {
                    "type": "found_issue_approved",
                    "ro_id": ro_id,
                    "item_id": fid,
                    "actor": actor,
                    "at": at,
                    "summary": (
                        f"Customer approved: {str(fi.get('description') or fid)[:80]}"
                        + (
                            f" → {fi.get('work_item_id')}"
                            if fi.get("work_item_id")
                            else ""
                        )
                    ),
                }
            )
        elif old_st != new_st and new_st == "declined":
            events.append(
                {
                    "type": "found_issue_declined",
                    "ro_id": ro_id,
                    "item_id": fid,
                    "actor": actor,
                    "at": at,
                    "summary": str(fi.get("description") or fid)[:120],
                }
            )

    b_photos_raw = ((before or {}).get("photos") or []) if before else []
    a_photos_raw = after.get("photos") or []
    b_photos = len(b_photos_raw) if isinstance(b_photos_raw, list) else 0
    a_photos = len(a_photos_raw) if isinstance(a_photos_raw, list) else 0
    if a_photos > b_photos:

        def _photo_key(p: object) -> str:
            if not isinstance(p, dict):
                return ""
            return str(
                p.get("id") or p.get("relpath") or p.get("filename") or ""
            ).strip()

        before_keys = {
            _photo_key(p)
            for p in (b_photos_raw if isinstance(b_photos_raw, list) else [])
            if _photo_key(p)
        }
        new_photos = [
            p
            for p in (a_photos_raw if isinstance(a_photos_raw, list) else [])
            if isinstance(p, dict) and _photo_key(p) and _photo_key(p) not in before_keys
        ]
        if not new_photos:
            # Count grew but keys unknown — treat trailing rows as new.
            new_photos = [
                p
                for p in (a_photos_raw if isinstance(a_photos_raw, list) else [])[
                    b_photos:
                ]
                if isinstance(p, dict)
            ]
        draft_fi_ids = {
            fid
            for fid, fi in a_fi.items()
            if str(fi.get("status") or "").strip().lower() == "draft"
        }

        def _linked_to_draft(p: dict[str, Any]) -> bool:
            fi_id = str(p.get("found_issue_id") or "").strip()
            return bool(fi_id and fi_id in draft_fi_ids)

        # Draft found-issue pics stay quiet until the tech hits Send to advisor.
        if new_photos and all(_linked_to_draft(p) for p in new_photos):
            pass
        else:
            events.append(
                {
                    "type": "photo_added",
                    "ro_id": ro_id,
                    "item_id": "",
                    "actor": actor,
                    "at": at,
                    "summary": f"{a_photos - b_photos} photo(s)",
                }
            )
    return events


def list_events(
    conn: sqlite3.Connection,
    *,
    since: str = "",
    since_id: int = 0,
    ro_id: str = "",
    limit: int = 100,
    exclude_actor: str = "",
    exclude_actor_id: str = "",
) -> list[dict[str, Any]]:
    """
    Return events. exclude_actor / exclude_actor_id drop the caller's own
    changes so tech↔tech (and later advisor) notifications never ping the maker.
    """
    ensure_events_table(conn)
    # Over-fetch then filter so exclude doesn't starve the page
    fetch_limit = max(1, min(int(limit) * 3 if (exclude_actor or exclude_actor_id) else int(limit), 500))
    sql = "SELECT id, at, type, ro_id, item_id, actor, summary, payload FROM ro_events WHERE 1=1"
    args: list[Any] = []
    if since_id > 0:
        sql += " AND id > ?"
        args.append(since_id)
    elif since:
        sql += " AND at > ?"
        args.append(since)
    if ro_id:
        sql += " AND ro_id = ?"
        args.append(ro_id)
    sql += " ORDER BY id ASC LIMIT ?"
    args.append(fetch_limit)
    rows = conn.execute(sql, args).fetchall()
    ex_name = exclude_actor.strip().lower()
    ex_id = exclude_actor_id.strip().lower()
    out = []
    for r in rows:
        try:
            payload = json.loads(r["payload"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        actor = r["actor"] or ""
        actor_id = str(payload.get("actor_id") or "")
        if ex_id and actor_id.strip().lower() == ex_id:
            continue
        if ex_name and actor.strip().lower() == ex_name:
            continue
        out.append(
            {
                "id": r["id"],
                "at": r["at"],
                "type": r["type"],
                "ro_id": r["ro_id"],
                "item_id": r["item_id"] or None,
                "actor": actor,
                "actor_id": actor_id or None,
                "summary": r["summary"] or "",
                "payload": payload,
            }
        )
        if len(out) >= max(1, min(int(limit), 500)):
            break
    return out
