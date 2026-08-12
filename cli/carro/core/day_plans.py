"""Advisor day plans: quiet queue edits, batch notify Today now / Next day at 8am."""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from carro.config import DATA_DIR
from carro.core.models import now_iso

NEXT_DAY_NOTIFY_HOUR = 8

_lock = threading.Lock()
_path: Path | None = None
_notify_cb: Callable[..., None] | None = None


def set_day_plan_notify(cb: Callable[..., None] | None) -> None:
    """Engine registers `_notify_tech_message` so background flush can send."""
    global _notify_cb
    _notify_cb = cb


def flush_registered_next_day_sends(*, now: datetime | None = None) -> list[dict[str, Any]]:
    cb = _notify_cb
    if cb is None:
        return []
    return flush_due_next_day_sends(notify=cb, now=now)


def day_plan_path() -> Path:
    global _path
    if _path is None:
        _path = DATA_DIR / "day_plan.json"
    return _path


def _empty_state() -> dict[str, Any]:
    return {
        "last_sent_daily": {},
        "last_sent_next_day": {},
        "pending_next_day_send": {},
        "staged": {},
    }


def load_day_plan(*, path: Path | None = None) -> dict[str, Any]:
    p = path or day_plan_path()
    with _lock:
        if not p.is_file():
            return _empty_state()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _empty_state()
        if not isinstance(raw, dict):
            return _empty_state()
        out = _empty_state()
        for key in out:
            val = raw.get(key)
            out[key] = val if isinstance(val, dict) else {}
        return out


def save_day_plan(state: dict[str, Any], *, path: Path | None = None) -> None:
    p = path or day_plan_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    clean = _empty_state()
    for key in clean:
        val = state.get(key)
        clean[key] = val if isinstance(val, dict) else {}
    tmp = p.with_suffix(".tmp")
    with _lock:
        tmp.write_text(json.dumps(clean, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(p)


def _stage_key(ro_id: str, item_id: str) -> str:
    return f"{(ro_id or '').strip()}:{(item_id or '').strip()}"


def stage_item(
    *,
    ro_id: str,
    item_id: str,
    tech_id: str,
    tech_name: str = "",
    lane: str = "daily",
    path: Path | None = None,
    concern: str = "",
    vehicle: str = "",
    customer: str = "",
) -> dict[str, Any]:
    """Queue an unassigned item for a tech Today/Next day path; does not move the RO yet."""
    rid = (ro_id or "").strip()
    iid = (item_id or "").strip()
    tid = (tech_id or "").strip()
    if not rid or not iid:
        raise ValueError("ro_id and item_id required")
    if not tid:
        raise ValueError("tech_id required to stage")
    lane_n = (lane or "daily").strip().lower()
    if lane_n not in ("daily", "next_day"):
        raise ValueError("lane must be daily or next_day")
    state = load_day_plan(path=path)
    staged = state.setdefault("staged", {})
    entry = {
        "ro_id": rid,
        "item_id": iid,
        "tech_id": tid,
        "tech_name": (tech_name or tid).strip(),
        "lane": lane_n,
        "concern": (concern or "").strip()[:120],
        "vehicle": (vehicle or "").strip()[:80],
        "customer": (customer or "").strip()[:80],
        "staged_at": now_iso(),
    }
    staged[_stage_key(rid, iid)] = entry
    save_day_plan(state, path=path)
    return entry


def unstage_item(
    *,
    ro_id: str,
    item_id: str,
    path: Path | None = None,
) -> bool:
    rid = (ro_id or "").strip()
    iid = (item_id or "").strip()
    if not rid or not iid:
        raise ValueError("ro_id and item_id required")
    state = load_day_plan(path=path)
    staged = state.setdefault("staged", {})
    key = _stage_key(rid, iid)
    if key not in staged:
        return False
    staged.pop(key, None)
    save_day_plan(state, path=path)
    return True


def list_staged(
    state: dict[str, Any] | None = None,
    *,
    tech_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    state = state if state is not None else load_day_plan()
    want = {str(t).strip() for t in (tech_ids or []) if str(t).strip()}
    rows: list[dict[str, Any]] = []
    for key, entry in (state.get("staged") or {}).items():
        if not isinstance(entry, dict):
            continue
        tid = str(entry.get("tech_id") or "").strip()
        if want and tid not in want:
            continue
        row = dict(entry)
        row["key"] = key
        rows.append(row)
    rows.sort(
        key=lambda r: (
            str(r.get("tech_name") or "").lower(),
            0 if r.get("lane") == "daily" else 1,
            str(r.get("staged_at") or ""),
            str(r.get("ro_id") or ""),
        )
    )
    return rows


def apply_staged(
    store: Any,
    *,
    tech_ids: list[str] | None = None,
    path: Path | None = None,
    actor: str = "",
    actor_id: str = "",
) -> list[dict[str, Any]]:
    """
    Commit staged plans onto ROs (assign + queue lane). Returns applied entries.
    Does not notify — caller should rebuild board and call send notify path.
    """
    from carro.core.assignment import assign_work_item
    from carro.core.queue_lanes import advisor_set_queue_lane
    from carro.core.work_items import ensure_work_items_on_order

    state = load_day_plan(path=path)
    rows = list_staged(state, tech_ids=tech_ids)
    if not rows:
        return []
    applied: list[dict[str, Any]] = []
    for entry in rows:
        rid = str(entry.get("ro_id") or "").strip()
        iid = str(entry.get("item_id") or "").strip()
        tid = str(entry.get("tech_id") or "").strip()
        tname = str(entry.get("tech_name") or tid).strip()
        lane = str(entry.get("lane") or "daily").strip().lower()
        if not rid or not iid or not tid:
            continue
        order = store.get(rid)
        if not order:
            continue
        if not assign_work_item(
            order,
            iid,
            tech_id=tid,
            tech_name=tname,
            store=store,
        ):
            continue
        try:
            advisor_set_queue_lane(
                order,
                iid,
                lane,
                approve_request=(lane == "next_day"),
            )
        except Exception:
            # Assign succeeded; lane best-effort
            pass
        ensure_work_items_on_order(order)
        store.save(order)
        try:
            from carro.core.sync_ops import try_push_ro

            try_push_ro(store, order, actor=actor or "dayplan", actor_id=actor_id or "")
        except Exception:
            pass
        applied.append(entry)
        state.setdefault("staged", {}).pop(_stage_key(rid, iid), None)
    if applied:
        save_day_plan(state, path=path)
    return applied


def tomorrow_local_iso() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


def local_now() -> datetime:
    return datetime.now().astimezone()


def _vehicle_label(job: dict[str, Any]) -> str:
    bits = [
        str(job.get("year") or "").strip(),
        str(job.get("make") or "").strip(),
        str(job.get("model") or "").strip(),
    ]
    car = " ".join(b for b in bits if b)
    return car or str(job.get("ro_id") or "RO")


def cars_from_jobs(jobs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """One entry per RO, sorted by queue_order (tech car path)."""
    by_ro: dict[str, dict[str, Any]] = {}
    for j in jobs or []:
        if not isinstance(j, dict):
            continue
        rid = str(j.get("ro_id") or "").strip()
        if not rid:
            continue
        qo = 0
        try:
            qo = int(j.get("queue_order") or 0)
        except (TypeError, ValueError):
            qo = 0
        existing = by_ro.get(rid)
        if existing is None or (qo and (not existing["queue_order"] or qo < existing["queue_order"])):
            by_ro[rid] = {
                "ro_id": rid,
                "queue_order": qo,
                "label": _vehicle_label(j),
                "year": str(j.get("year") or ""),
                "make": str(j.get("make") or ""),
                "model": str(j.get("model") or ""),
            }
        elif existing is not None and not existing.get("label"):
            existing["label"] = _vehicle_label(j)
    rows = list(by_ro.values())
    rows.sort(
        key=lambda c: (
            int(c.get("queue_order") or 0) or 9999,
            str(c.get("ro_id") or ""),
        )
    )
    return rows


def fingerprint_cars(cars: list[dict[str, Any]] | None) -> list[list[Any]]:
    out: list[list[Any]] = []
    for c in cars or []:
        out.append([str(c.get("ro_id") or ""), int(c.get("queue_order") or 0)])
    return out


def snapshot_tech_paths(board: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """tech_id -> { name, daily: cars[], next_day: cars[] }."""
    techs: dict[str, dict[str, Any]] = {}

    def ensure(tid: str, name: str) -> dict[str, Any]:
        tid = (tid or "").strip()
        if not tid:
            return {"id": "", "name": name, "daily": [], "next_day": []}
        row = techs.setdefault(
            tid,
            {"id": tid, "name": (name or tid).strip(), "daily": [], "next_day": []},
        )
        if name and not row.get("name"):
            row["name"] = name
        return row

    for b in board.get("daily_by_tech") or []:
        if not isinstance(b, dict):
            continue
        tid = str(b.get("id") or "").strip()
        if not tid:
            continue
        row = ensure(tid, str(b.get("name") or ""))
        row["daily"] = cars_from_jobs(b.get("jobs") or [])

    for b in board.get("next_day_by_tech") or []:
        if not isinstance(b, dict):
            continue
        tid = str(b.get("id") or "").strip()
        if not tid:
            continue
        row = ensure(tid, str(b.get("name") or ""))
        row["next_day"] = cars_from_jobs(b.get("jobs") or [])

    return techs


def format_path_message(title: str, cars: list[dict[str, Any]]) -> str:
    n = len(cars or [])
    lines = [f"{title} · {n} car{'s' if n != 1 else ''}"]
    if not cars:
        lines.append("(empty)")
        return "\n".join(lines)
    for idx, c in enumerate(cars, start=1):
        num = int(c.get("queue_order") or 0) or idx
        rid = str(c.get("ro_id") or "")
        label = str(c.get("label") or rid)
        lines.append(f"#{num} {rid} · {label}".strip(" ·"))
    return "\n".join(lines)


def _sent_fp(entry: dict[str, Any] | None, *, key: str = "cars") -> list[list[Any]]:
    if not isinstance(entry, dict):
        return []
    return fingerprint_cars(entry.get(key) or entry.get("daily") or [])


def diff_dirty(
    board: dict[str, Any],
    state: dict[str, Any] | None = None,
    *,
    next_day_date: str | None = None,
) -> list[dict[str, Any]]:
    """Techs whose live path differs from last sent (or pending next-day snapshot)."""
    state = state if state is not None else load_day_plan()
    snaps = snapshot_tech_paths(board)
    last_daily = state.get("last_sent_daily") or {}
    last_nd = state.get("last_sent_next_day") or {}
    pending = state.get("pending_next_day_send") or {}
    nd_date = (next_day_date or tomorrow_local_iso()).strip()
    dirty: list[dict[str, Any]] = []

    all_ids = set(snaps) | set(last_daily) | set(last_nd) | set(pending)
    for tid in sorted(all_ids):
        snap = snaps.get(tid) or {
            "id": tid,
            "name": tid,
            "daily": [],
            "next_day": [],
        }
        daily_cars = snap.get("daily") or []
        nd_cars = snap.get("next_day") or []
        daily_fp = fingerprint_cars(daily_cars)
        nd_fp = fingerprint_cars(nd_cars)

        sent_d = last_daily.get(tid) if isinstance(last_daily.get(tid), dict) else None
        daily_changed = daily_fp != _sent_fp(sent_d)

        pend = pending.get(tid) if isinstance(pending.get(tid), dict) else None
        sent_n = last_nd.get(tid) if isinstance(last_nd.get(tid), dict) else None
        if pend and str(pend.get("for_date") or "") == nd_date:
            nd_changed = nd_fp != fingerprint_cars(pend.get("cars") or [])
        elif sent_n and str(sent_n.get("for_date") or "") == nd_date:
            nd_changed = nd_fp != _sent_fp(sent_n)
        else:
            # Never sent/queued for this date: dirty only if there is a path
            nd_changed = bool(nd_fp)

        if not daily_changed and not nd_changed:
            continue
        # Empty vs never-sent: ignore techs with no cars and no history
        if not daily_fp and not nd_fp and not sent_d and not sent_n and not pend:
            continue

        dirty.append(
            {
                "tech_id": tid,
                "tech_name": str(snap.get("name") or tid),
                "daily": daily_cars,
                "next_day": nd_cars,
                "daily_changed": daily_changed,
                "next_day_changed": nd_changed,
                "changed": {
                    "daily": daily_changed,
                    "next_day": nd_changed,
                },
            }
        )
    return dirty


def mark_dirty(*_tech_ids: str) -> None:
    """No-op placeholder — dirty is derived from board vs last_sent.

    Kept so call sites can document intent without persisting a separate dirty set.
    """
    return


def record_sent_daily(
    state: dict[str, Any],
    tech_id: str,
    cars: list[dict[str, Any]],
    *,
    at: str | None = None,
) -> None:
    tid = (tech_id or "").strip()
    if not tid:
        return
    daily = state.setdefault("last_sent_daily", {})
    daily[tid] = {"cars": list(cars or []), "at": at or now_iso()}


def queue_next_day_send(
    state: dict[str, Any],
    *,
    tech_id: str,
    tech_name: str,
    cars: list[dict[str, Any]],
    for_date: str | None = None,
    body: str = "",
) -> dict[str, Any]:
    tid = (tech_id or "").strip()
    if not tid:
        return {}
    for_d = (for_date or tomorrow_local_iso()).strip()
    entry = {
        "for_date": for_d,
        "tech_id": tid,
        "tech_name": (tech_name or tid).strip(),
        "cars": list(cars or []),
        "body": (body or "").strip()
        or format_path_message("Tomorrow's plan", cars or []),
        "queued_at": now_iso(),
        "deliver_at": f"{for_d}T{NEXT_DAY_NOTIFY_HOUR:02d}:00:00",
    }
    pending = state.setdefault("pending_next_day_send", {})
    pending[tid] = entry
    return entry


def pending_next_day_rows(state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    state = state if state is not None else load_day_plan()
    rows = []
    for tid, entry in (state.get("pending_next_day_send") or {}).items():
        if not isinstance(entry, dict):
            continue
        rows.append(
            {
                "tech_id": str(entry.get("tech_id") or tid),
                "tech_name": str(entry.get("tech_name") or tid),
                "for_date": str(entry.get("for_date") or ""),
                "deliver_at": str(entry.get("deliver_at") or ""),
                "cars": entry.get("cars") or [],
                "queued_at": str(entry.get("queued_at") or ""),
            }
        )
    rows.sort(key=lambda r: (r.get("tech_name") or "").lower())
    return rows


def due_next_day_sends(
    state: dict[str, Any],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Pending next-day messages ready to deliver (local date == for_date and hour >= 8)."""
    now = now or local_now()
    today = now.date().isoformat()
    hour = now.hour
    due: list[dict[str, Any]] = []
    for tid, entry in list((state.get("pending_next_day_send") or {}).items()):
        if not isinstance(entry, dict):
            continue
        for_d = str(entry.get("for_date") or "").strip()
        # Deliver on the morning of for_date (the "tomorrow" that became today).
        if for_d != today:
            continue
        if hour < NEXT_DAY_NOTIFY_HOUR:
            continue
        row = dict(entry)
        row["tech_id"] = str(entry.get("tech_id") or tid)
        due.append(row)
    return due


def apply_sent_next_day(
    state: dict[str, Any],
    entry: dict[str, Any],
    *,
    at: str | None = None,
) -> None:
    tid = str(entry.get("tech_id") or "").strip()
    if not tid:
        return
    for_d = str(entry.get("for_date") or "").strip()
    cars = entry.get("cars") or []
    last = state.setdefault("last_sent_next_day", {})
    last[tid] = {"for_date": for_d, "cars": list(cars), "at": at or now_iso()}
    pending = state.setdefault("pending_next_day_send", {})
    pending.pop(tid, None)


def build_day_plan_view(
    board: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from carro.core.queue_lanes import today_local_iso

    state = state if state is not None else load_day_plan()
    nd = tomorrow_local_iso()
    dirty = diff_dirty(board, state, next_day_date=nd)
    staged_rows = list_staged(state)
    return {
        "today": today_local_iso(),
        "next_day_date": nd,
        "next_day_notify_hour": NEXT_DAY_NOTIFY_HOUR,
        "dirty": dirty,
        "pending_next_day": pending_next_day_rows(state),
        "last_sent_at": _latest_sent_at(state),
        "staged": staged_rows,
        "staged_count": len(staged_rows),
    }


def _latest_sent_at(state: dict[str, Any]) -> str:
    latest = ""
    for bucket in (state.get("last_sent_daily"), state.get("last_sent_next_day")):
        if not isinstance(bucket, dict):
            continue
        for entry in bucket.values():
            if isinstance(entry, dict):
                at = str(entry.get("at") or "")
                if at > latest:
                    latest = at
    return latest


def flush_due_next_day_sends(
    *,
    notify: Callable[..., None],
    now: datetime | None = None,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Send due next-day plan messages via notify(to_id=, to_name=, body=, ...).
    Returns list of delivered entries.
    """
    state = load_day_plan(path=path)
    due = due_next_day_sends(state, now=now)
    if not due:
        return []
    delivered: list[dict[str, Any]] = []
    for entry in due:
        tid = str(entry.get("tech_id") or "").strip()
        if not tid:
            continue
        body = str(entry.get("body") or "").strip() or format_path_message(
            "Tomorrow's plan", entry.get("cars") or []
        )
        try:
            notify(
                to_id=tid,
                to_name=str(entry.get("tech_name") or ""),
                body=body,
                from_id="system",
                from_name="Day plan",
                from_role="advisor",
                ro_id="",
                work_item_id="",
            )
        except Exception:
            continue
        apply_sent_next_day(state, entry)
        delivered.append(entry)
    if delivered:
        save_day_plan(state, path=path)
    return delivered


def send_day_plans(
    board: dict[str, Any],
    *,
    tech_ids: list[str] | None = None,
    notify: Callable[..., None],
    advisor_id: str = "",
    advisor_name: str = "",
    path: Path | None = None,
    store: Any | None = None,
    board_builder: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Apply staged plans (if store given), then send Today now / queue Next-day for 8am.

    tech_ids empty = apply all staged + notify all dirty techs.
    When tech_ids is set, apply/send only those techs (force current paths after apply).
    """
    applied: list[dict[str, Any]] = []
    if store is not None:
        applied = apply_staged(
            store,
            tech_ids=tech_ids,
            path=path,
            actor=advisor_name,
            actor_id=advisor_id,
        )
        if board_builder is not None and applied:
            board = board_builder()

    state = load_day_plan(path=path)
    nd_date = tomorrow_local_iso()
    dirty = diff_dirty(board, state, next_day_date=nd_date)
    want = {str(t).strip() for t in (tech_ids or []) if str(t).strip()}

    if want:
        snaps = snapshot_tech_paths(board)
        dirty = []
        for tid in sorted(want):
            snap = snaps.get(tid) or {
                "id": tid,
                "name": tid,
                "daily": [],
                "next_day": [],
            }
            tname = str(snap.get("name") or tid)
            for e in applied:
                if str(e.get("tech_id") or "") == tid and e.get("tech_name"):
                    tname = str(e.get("tech_name") or tname)
                    break
            daily_cars = list(snap.get("daily") or [])
            nd_cars = list(snap.get("next_day") or [])
            if not daily_cars and not nd_cars:
                continue
            dirty.append(
                {
                    "tech_id": tid,
                    "tech_name": tname,
                    "daily": daily_cars,
                    "next_day": nd_cars,
                    "daily_changed": bool(daily_cars),
                    "next_day_changed": bool(nd_cars),
                }
            )
    elif applied:
        # After apply, ensure those techs are included even if already marked sent.
        snaps = snapshot_tech_paths(board)
        have = {str(d.get("tech_id") or "") for d in dirty}
        for e in applied:
            tid = str(e.get("tech_id") or "").strip()
            if not tid or tid in have:
                continue
            snap = snaps.get(tid) or {}
            daily_cars = list(snap.get("daily") or [])
            nd_cars = list(snap.get("next_day") or [])
            if not daily_cars and not nd_cars:
                continue
            dirty.append(
                {
                    "tech_id": tid,
                    "tech_name": str(e.get("tech_name") or snap.get("name") or tid),
                    "daily": daily_cars,
                    "next_day": nd_cars,
                    "daily_changed": bool(daily_cars),
                    "next_day_changed": bool(nd_cars),
                }
            )
            have.add(tid)

    sent_daily: list[dict[str, Any]] = []
    scheduled_next: list[dict[str, Any]] = []
    from_id = (advisor_id or "").strip() or "system"
    from_name = (advisor_name or "").strip() or "Desk"

    for d in dirty:
        tid = d["tech_id"]
        tname = d["tech_name"]
        if d.get("daily_changed"):
            cars = d.get("daily") or []
            body = format_path_message("Today's plan", cars)
            notify(
                to_id=tid,
                to_name=tname,
                body=body,
                from_id=from_id,
                from_name=from_name,
                from_role="advisor",
                ro_id="",
                work_item_id="",
            )
            record_sent_daily(state, tid, cars)
            sent_daily.append({"tech_id": tid, "tech_name": tname, "cars": cars})
        if d.get("next_day_changed"):
            cars = d.get("next_day") or []
            body = format_path_message("Tomorrow's plan", cars)
            entry = queue_next_day_send(
                state,
                tech_id=tid,
                tech_name=tname,
                cars=cars,
                for_date=nd_date,
                body=body,
            )
            scheduled_next.append(entry)

    save_day_plan(state, path=path)
    return {
        "sent_daily": sent_daily,
        "scheduled_next_day": scheduled_next,
        "applied_staged": applied,
        "next_day_notify_hour": NEXT_DAY_NOTIFY_HOUR,
        "next_day_date": nd_date,
        "view": build_day_plan_view(board, state=state),
    }
