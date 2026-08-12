"""Daily / next-day / long-term work-item queue lanes."""

from __future__ import annotations

from datetime import date
from typing import Any

from carro.core.models import RepairOrder, now_iso
from carro.core.work_items import ensure_work_items_on_order, work_items_to_dicts

QUEUE_LANES = ("daily", "next_day", "long_term")
NEXT_DAY_REQUEST_STATUSES = ("pending", "approved", "declined", "")


def today_local_iso() -> str:
    return date.today().isoformat()


def normalize_queue_lane(raw: object, *, default: str = "daily") -> str:
    st = str(raw or "").strip().lower()
    return st if st in QUEUE_LANES else default


def empty_next_day_request() -> dict[str, Any]:
    return {
        "status": "",
        "at": "",
        "by": "",
        "by_id": "",
        "note": "",
        "read_at": "",
    }


def normalize_next_day_request(raw: object) -> dict[str, Any]:
    out = empty_next_day_request()
    if not isinstance(raw, dict):
        return out
    st = str(raw.get("status") or "").strip().lower()
    out["status"] = st if st in ("pending", "approved", "declined") else ""
    out["at"] = str(raw.get("at") or "").strip()
    out["by"] = str(raw.get("by") or "").strip()
    out["by_id"] = str(raw.get("by_id") or "").strip()
    out["note"] = str(raw.get("note") or "").strip()
    out["read_at"] = str(raw.get("read_at") or "").strip()
    return out


def ensure_queue_defaults(item: Any) -> None:
    """Fill missing lane/day fields on a WorkItem (mutates)."""
    lane = normalize_queue_lane(getattr(item, "queue_lane", None) or "daily")
    item.queue_lane = lane
    pending = str(getattr(item, "pending_queue_lane", "") or "").strip().lower()
    item.pending_queue_lane = pending if pending in QUEUE_LANES else ""
    qd = str(getattr(item, "queue_day", "") or "").strip()
    if not qd and lane == "daily":
        qd = today_local_iso()
    item.queue_day = qd
    if not hasattr(item, "due_eod"):
        item.due_eod = False
    else:
        item.due_eod = bool(getattr(item, "due_eod", False))
    req = getattr(item, "next_day_request", None)
    if isinstance(req, dict):
        item.next_day_request = normalize_next_day_request(req)
    else:
        item.next_day_request = empty_next_day_request()


def set_queue_lane(
    item: Any,
    lane: str,
    *,
    clear_pending: bool = True,
    set_day: bool = True,
) -> None:
    from carro.core.work_items import stop_downtime

    lane_n = normalize_queue_lane(lane)
    item.queue_lane = lane_n
    if clear_pending:
        item.pending_queue_lane = ""
    if set_day:
        item.queue_day = today_local_iso()
    if lane_n in ("long_term", "next_day"):
        item.due_eod = False
        # Parked until later — do not leave between-session downtime running overnight.
        stop_downtime(item)
    if lane_n == "long_term":
        item.assigned_to_id = ""
        item.assigned_to_name = ""
        item.assigned_at = ""
    item.updated = now_iso()


def item_is_current(order: RepairOrder | dict[str, Any], item_id: str) -> bool:
    wid = (item_id or "").strip()
    if not wid:
        return False
    if isinstance(order, RepairOrder):
        return (order.current_item_id or "").strip() == wid
    return str(order.get("current_item_id") or "").strip() == wid


def apply_pending_queue_lane(order: RepairOrder, item_id: str) -> bool:
    """Apply pending_queue_lane on clock-out. Returns True if lane changed."""
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        return False
    ensure_queue_defaults(target)
    pending = (target.pending_queue_lane or "").strip().lower()
    if pending not in QUEUE_LANES:
        return False
    # Preserve assignee across next_day park (tech's next-day queue).
    keep_id = (target.assigned_to_id or "").strip()
    keep_name = (target.assigned_to_name or "").strip()
    keep_at = (target.assigned_at or "").strip()
    req = normalize_next_day_request(target.next_day_request)
    if pending == "next_day":
        req_id = str(req.get("by_id") or "").strip()
        req_name = str(req.get("by") or "").strip()
        if req_id or req_name:
            keep_id = req_id or keep_id
            keep_name = req_name or keep_name
            if not keep_at:
                keep_at = now_iso()
    set_queue_lane(target, pending, clear_pending=True, set_day=True)
    if pending == "next_day" and (keep_id or keep_name):
        target.assigned_to_id = keep_id
        target.assigned_to_name = keep_name
        target.assigned_at = keep_at or now_iso()
    order.work_items = work_items_to_dicts(items)
    return True


def advisor_set_queue_lane(
    order: RepairOrder,
    item_id: str,
    lane: str,
    *,
    approve_request: bool = False,
) -> None:
    """
    Advisor push to a lane. If the item is currently being worked, arm
    pending_queue_lane and apply on clock-out; otherwise apply immediately.

    Approving a pending next-day request assigns/keeps the job on the requesting
    tech so it lands in their next-day queue (not yanked back to daily).

    Long-term always parks unassigned (clears assignee + due_eod via set_queue_lane).
    Next-day keeps the item assignee; if the item has none, inherit the RO assignee
    so the car still lands on a tech's tomorrow path when one was selected on the RO.
    """
    lane_n = normalize_queue_lane(lane)
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        raise ValueError(f"Work item not found: {item_id}")
    ensure_queue_defaults(target)
    if lane_n == "next_day" and not (
        (target.assigned_to_id or "").strip() or (target.assigned_to_name or "").strip()
    ):
        ro_id = (order.assigned_to_id or "").strip()
        ro_name = (order.assigned_to_name or "").strip()
        if ro_id or ro_name:
            target.assigned_to_id = ro_id
            target.assigned_to_name = ro_name
            if not (target.assigned_at or "").strip():
                target.assigned_at = now_iso()
    req = normalize_next_day_request(target.next_day_request)
    was_pending = req.get("status") == "pending"
    if was_pending or (approve_request and lane_n == "next_day"):
        req["status"] = "approved"
        target.next_day_request = req
    # Pending ask approved → requesting tech owns the next-day queue slot.
    if lane_n == "next_day" and was_pending:
        req_id = str(req.get("by_id") or "").strip()
        req_name = str(req.get("by") or "").strip()
        if req_id or req_name:
            target.assigned_to_id = req_id or (target.assigned_to_id or "")
            target.assigned_to_name = req_name or (target.assigned_to_name or "")
            if not (target.assigned_at or "").strip():
                target.assigned_at = now_iso()
    if item_is_current(order, item_id):
        target.pending_queue_lane = lane_n
        if lane_n in ("long_term", "next_day"):
            target.due_eod = False
        if lane_n == "long_term":
            target.assigned_to_id = ""
            target.assigned_to_name = ""
            target.assigned_at = ""
        target.updated = now_iso()
    else:
        keep_id = (target.assigned_to_id or "").strip()
        keep_name = (target.assigned_to_name or "").strip()
        keep_at = (target.assigned_at or "").strip()
        set_queue_lane(target, lane_n, clear_pending=True, set_day=True)
        # set_queue_lane only clears assignee for long_term; restore next_day tech.
        if lane_n == "next_day" and (keep_id or keep_name):
            target.assigned_to_id = keep_id
            target.assigned_to_name = keep_name
            target.assigned_at = keep_at or now_iso()
    order.work_items = work_items_to_dicts(items)


def decline_next_day_request(order: RepairOrder, item_id: str) -> None:
    """Decline a tech next-day ask: stay on today, mark due EOD."""
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        raise ValueError(f"Work item not found: {item_id}")
    req = normalize_next_day_request(target.next_day_request)
    if req.get("status") != "pending":
        raise ValueError("No pending next-day request")
    req["status"] = "declined"
    target.next_day_request = req
    target.pending_queue_lane = ""
    # Stay on today's floor and finish today.
    ensure_queue_defaults(target)
    if (target.queue_lane or "").strip().lower() != "long_term":
        target.queue_lane = "daily"
    target.due_eod = True
    target.updated = now_iso()
    order.work_items = work_items_to_dicts(items)


def request_next_day(
    order: RepairOrder,
    item_id: str,
    *,
    tech_id: str = "",
    tech_name: str = "",
    note: str = "",
) -> None:
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        raise ValueError(f"Work item not found: {item_id}")
    ensure_queue_defaults(target)
    if (target.queue_lane or "") == "long_term":
        raise ValueError("Long-term items stay there until an advisor pulls them back")
    target.next_day_request = {
        "status": "pending",
        "at": now_iso(),
        "by": (tech_name or "").strip(),
        "by_id": (tech_id or "").strip(),
        "note": (note or "").strip(),
        "read_at": "",
    }
    target.updated = now_iso()
    order.work_items = work_items_to_dicts(items)


def mark_next_day_request_read(order: RepairOrder, item_id: str) -> None:
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        raise ValueError(f"Work item not found: {item_id}")
    req = normalize_next_day_request(target.next_day_request)
    if not req.get("status"):
        raise ValueError("No next-day request on this item")
    if not req.get("read_at"):
        req["read_at"] = now_iso()
        target.next_day_request = req
        target.updated = now_iso()
        order.work_items = work_items_to_dicts(items)


def ensure_daily_on_assign(item: Any) -> None:
    """On assign/pickup: long-term → today; next_day stays next_day (tech tomorrow path)."""
    ensure_queue_defaults(item)
    lane = normalize_queue_lane(item.queue_lane, default="daily")
    if lane == "long_term":
        set_queue_lane(item, "daily", clear_pending=True, set_day=True)
    elif lane == "next_day":
        # Keep tomorrow's lane so Assign from Unassigned next day lands on that tech's path.
        return
    elif not (item.queue_day or "").strip():
        item.queue_day = today_local_iso()


def rollover_queue_lanes(order: RepairOrder, *, today: str | None = None) -> int:
    """
    Calendar-day rollover at local midnight:

    1. next_day + queue_day < today → daily
       - Assigned items land in that tech's today queue
       - Unassigned items land in Needs attention / unassigned for advisor reassignment
    2. Unfinished Today (daily) work is cleared back to unassigned Needs attention
       (keeps daily lane; drops assignee). In-progress / current-timer jobs are left alone.
    3. Long-term is untouched.
    """
    today_s = (today or today_local_iso()).strip()
    items = ensure_work_items_on_order(order)
    changed = 0

    for w in items:
        ensure_queue_defaults(w)
        st = (w.status or "").strip().lower()
        if st in ("done", "declined"):
            continue

        # Promote yesterday's next-day into today.
        if w.queue_lane == "next_day":
            qd = (w.queue_day or "").strip() or today_s
            if qd < today_s:
                set_queue_lane(w, "daily", clear_pending=True, set_day=True)
                changed += 1
            continue

        # End of day: Today-lane leftovers return to unassigned Needs attention.
        if normalize_queue_lane(w.queue_lane, default="daily") != "daily":
            continue
        if st == "in_progress" or (w.timer_started_at or "").strip():
            continue
        if st in ("waiting_parts", "waiting_customer"):
            continue
        qd = (w.queue_day or "").strip()
        # Only clear assignee for prior calendar days (queue_day before today).
        if qd and qd < today_s and ((w.assigned_to_id or "").strip() or (w.assigned_to_name or "").strip()):
            w.assigned_to_id = ""
            w.assigned_to_name = ""
            w.due_eod = False
            w.updated = now_iso()
            changed += 1

    if changed:
        order.work_items = work_items_to_dicts(items)
        order.updated = now_iso()
    return changed


def rollover_all_orders(orders: list[RepairOrder], *, today: str | None = None) -> list[RepairOrder]:
    """Run rollover; return orders that changed (caller should save)."""
    today_s = today or today_local_iso()
    changed: list[RepairOrder] = []
    for order in orders:
        if (order.status or "") == "billed_out":
            continue
        n = rollover_queue_lanes(order, today=today_s)
        if n:
            changed.append(order)
    return changed


def floor_sort_key(job: dict[str, Any]) -> tuple:
    """Waiter > urgent > then updated desc (negate via reverse sort)."""
    waiter = 0 if job.get("waiter") else 1
    urgent = 0 if job.get("urgent") else 1
    updated = str(job.get("updated") or "")
    return (waiter, urgent, updated)


def set_ro_flags(
    order: RepairOrder,
    *,
    waiter: bool | None = None,
    urgent: bool | None = None,
) -> None:
    if waiter is not None:
        order.waiter = bool(waiter)
    if urgent is not None:
        order.urgent = bool(urgent)
    order.updated = now_iso()


def repark_siblings_long_term(order: RepairOrder, except_id: str = "") -> int:
    """
    After completing a long-term item, re-park remaining shop work as long_term.

    Only touches open / in_progress siblings (not waiting_parts / waiting_customer).
    Clears pending_queue_lane so a later clock-out cannot yank them to daily.
    Returns how many items were updated.
    """
    skip = (except_id or "").strip()
    items = ensure_work_items_on_order(order)
    changed = 0
    for w in items:
        if skip and w.id == skip:
            continue
        st = str(w.status or "").strip().lower()
        if st not in ("open", "in_progress"):
            continue
        ensure_queue_defaults(w)
        if normalize_queue_lane(w.queue_lane, default="daily") != "long_term":
            set_queue_lane(w, "long_term", clear_pending=True, set_day=True)
            changed += 1
        else:
            # Already long_term: still force unassigned park + clear pending/EOD.
            cleared = False
            if (w.pending_queue_lane or "").strip():
                w.pending_queue_lane = ""
                cleared = True
            if bool(getattr(w, "due_eod", False)):
                w.due_eod = False
                cleared = True
            if (w.assigned_to_id or "").strip() or (w.assigned_to_name or "").strip():
                w.assigned_to_id = ""
                w.assigned_to_name = ""
                w.assigned_at = ""
                cleared = True
            if cleared:
                w.updated = now_iso()
                changed += 1
    if changed:
        order.work_items = work_items_to_dicts(items)
    return changed


def order_open_items_all_long_term(order: RepairOrder | dict[str, Any]) -> bool:
    """True when every non-done/declined item is in the long_term lane (and at least one open)."""
    if isinstance(order, RepairOrder):
        items = ensure_work_items_on_order(order)
        rows = [
            {
                "status": w.status,
                "queue_lane": w.queue_lane,
            }
            for w in items
        ]
    else:
        rows = [it for it in (order.get("work_items") or []) if isinstance(it, dict)]
    open_rows = [
        r
        for r in rows
        if str(r.get("status") or "open").strip().lower() not in ("done", "declined")
    ]
    if not open_rows:
        return False
    return all(
        normalize_queue_lane(r.get("queue_lane"), default="daily") == "long_term"
        for r in open_rows
    )


def _item_open(item: Any) -> bool:
    return str(getattr(item, "status", "") or "open").strip().lower() not in (
        "done",
        "declined",
    )


def _tech_match(item: Any, tech_id: str, tech_name: str) -> bool:
    from carro.core.assignment import matches_tech

    return matches_tech(
        getattr(item, "assigned_to_id", "") or "",
        getattr(item, "assigned_to_name", "") or "",
        me_id=tech_id,
        me_name=tech_name,
    )


def _orders_with(
    store: Any,
    extra: RepairOrder | None = None,
    extras: list[RepairOrder] | None = None,
) -> list[RepairOrder]:
    overlay: dict[str, RepairOrder] = {}
    if extra is not None:
        overlay[extra.id] = extra
    for o in extras or []:
        overlay[o.id] = o
    orders = list(store.list_orders())
    for i, o in enumerate(orders):
        if o.id in overlay:
            orders[i] = overlay.pop(o.id)
    orders.extend(overlay.values())
    return orders


def collect_tech_lane_groups(
    orders: list[RepairOrder],
    *,
    tech_id: str,
    tech_name: str = "",
    lane: str,
) -> dict[str, dict[str, Any]]:
    """RO id → {order, items, queue_order, assigned_at} for one tech+lane."""
    lane_n = normalize_queue_lane(lane, default="daily")
    groups: dict[str, dict[str, Any]] = {}
    for order in orders:
        st = (order.status or "").strip().lower()
        if st in ("billed_out", "canceled", "no_call_no_show"):
            continue
        items = ensure_work_items_on_order(order)
        for w in items:
            if not _item_open(w):
                continue
            if normalize_queue_lane(w.queue_lane, default="daily") != lane_n:
                continue
            if not _tech_match(w, tech_id, tech_name):
                continue
            g = groups.setdefault(
                order.id,
                {
                    "order": order,
                    "items": [],
                    "queue_order": 0,
                    "assigned_at": "9999",
                },
            )
            g["items"].append(w)
            try:
                qo = int(getattr(w, "queue_order", 0) or 0)
            except (TypeError, ValueError):
                qo = 0
            if qo and (not g["queue_order"] or qo < int(g["queue_order"])):
                g["queue_order"] = qo
            at = str(getattr(w, "assigned_at", "") or "") or "9999"
            if at < str(g["assigned_at"]):
                g["assigned_at"] = at
    return groups


def _stamp_group(group: dict[str, Any], n: int) -> None:
    order: RepairOrder = group["order"]
    items = ensure_work_items_on_order(order)
    ids = {w.id for w in group["items"]}
    for w in items:
        if w.id in ids:
            w.queue_order = n
    order.work_items = work_items_to_dicts(items)
    group["queue_order"] = n


def ensure_queue_order_on_assign(store: Any, order: RepairOrder, item_id: str) -> None:
    """First item on this car for the tech gets next number; later items inherit it."""
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        return
    tid = (target.assigned_to_id or "").strip()
    tname = (target.assigned_to_name or "").strip()
    if not tid and not tname:
        target.queue_order = 0
        order.work_items = work_items_to_dicts(items)
        return
    lane = normalize_queue_lane(target.queue_lane, default="daily")
    sibling = 0
    for w in items:
        if w.id == item_id or not _item_open(w):
            continue
        if normalize_queue_lane(w.queue_lane, default="daily") != lane:
            continue
        if not _tech_match(w, tid, tname):
            continue
        try:
            qo = int(w.queue_order or 0)
        except (TypeError, ValueError):
            qo = 0
        if qo:
            sibling = qo
            break
    if sibling:
        target.queue_order = sibling
        order.work_items = work_items_to_dicts(items)
        return
    groups = collect_tech_lane_groups(
        _orders_with(store, order),
        tech_id=tid,
        tech_name=tname,
        lane=lane,
    )
    max_n = 0
    for rid, g in groups.items():
        if rid == order.id:
            continue
        max_n = max(max_n, int(g.get("queue_order") or 0))
    target.queue_order = max_n + 1
    order.work_items = work_items_to_dicts(items)


def rebalance_tech_lane(
    store: Any,
    *,
    tech_id: str,
    tech_name: str = "",
    lane: str,
    extra: RepairOrder | None = None,
    extras: list[RepairOrder] | None = None,
) -> list[RepairOrder]:
    groups = collect_tech_lane_groups(
        _orders_with(store, extra, extras),
        tech_id=tech_id,
        tech_name=tech_name,
        lane=lane,
    )
    ranked = sorted(
        groups.values(),
        key=lambda g: (
            int(g.get("queue_order") or 0) or 9999,
            str(g.get("assigned_at") or ""),
            str(g["order"].id),
        ),
    )
    touched: list[RepairOrder] = []
    for i, g in enumerate(ranked, 1):
        _stamp_group(g, i)
        touched.append(g["order"])
    return touched


def set_tech_queue(
    store: Any,
    *,
    tech_id: str,
    tech_name: str = "",
    lane: str,
    ro_ids: list[str],
) -> list[RepairOrder]:
    """Advisor restacks cars on a tech's today or next-day path."""
    lane_n = normalize_queue_lane(lane, default="daily")
    if lane_n not in ("daily", "next_day"):
        raise ValueError("lane must be daily or next_day")
    groups = collect_tech_lane_groups(
        store.list_orders(),
        tech_id=tech_id,
        tech_name=tech_name,
        lane=lane_n,
    )
    seen: set[str] = set()
    n = 1
    touched: list[RepairOrder] = []
    for ro_id in ro_ids:
        g = groups.get((ro_id or "").strip())
        if not g:
            continue
        _stamp_group(g, n)
        touched.append(g["order"])
        seen.add(g["order"].id)
        n += 1
    rest = sorted(
        (g for rid, g in groups.items() if rid not in seen),
        key=lambda g: (int(g.get("queue_order") or 0) or 9999, str(g["order"].id)),
    )
    for g in rest:
        _stamp_group(g, n)
        touched.append(g["order"])
        n += 1
    return touched


def move_ro_group_lane(
    store: Any,
    order: RepairOrder,
    item_id: str,
    lane: str,
    *,
    approve_request: bool = False,
) -> list[RepairOrder]:
    """Move every item this tech has on this RO into daily/next_day/long_term."""
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        raise ValueError(f"Work item not found: {item_id}")
    tid = (target.assigned_to_id or "").strip()
    tname = (target.assigned_to_name or "").strip()
    old_lane = normalize_queue_lane(target.queue_lane, default="daily")
    lane_n = normalize_queue_lane(lane)
    siblings = [
        w
        for w in items
        if _item_open(w)
        and _tech_match(w, tid, tname)
        and normalize_queue_lane(w.queue_lane, default="daily") == old_lane
    ]
    if not siblings:
        siblings = [target]
    for w in siblings:
        advisor_set_queue_lane(
            order,
            w.id,
            lane_n,
            approve_request=approve_request and w.id == item_id,
        )
    sibling_ids = {s.id for s in siblings}
    items = ensure_work_items_on_order(order)
    if lane_n in ("daily", "next_day") and (tid or tname):
        groups = collect_tech_lane_groups(
            _orders_with(store, order),
            tech_id=tid,
            tech_name=tname,
            lane=lane_n,
        )
        max_n = 0
        for rid, g in groups.items():
            if rid == order.id:
                continue
            max_n = max(max_n, int(g.get("queue_order") or 0))
        n = max_n + 1
        for w in items:
            if w.id in sibling_ids or (
                _item_open(w)
                and _tech_match(w, tid, tname)
                and normalize_queue_lane(w.queue_lane, default="daily") == lane_n
            ):
                w.queue_order = n
        order.work_items = work_items_to_dicts(items)
    else:
        for w in items:
            if w.id in sibling_ids:
                w.queue_order = 0
        order.work_items = work_items_to_dicts(items)
    touched = [order]
    if tid or tname:
        if old_lane in ("daily", "next_day") and old_lane != lane_n:
            touched.extend(
                rebalance_tech_lane(
                    store, tech_id=tid, tech_name=tname, lane=old_lane, extra=order
                )
            )
        if lane_n in ("daily", "next_day"):
            touched.extend(
                rebalance_tech_lane(
                    store, tech_id=tid, tech_name=tname, lane=lane_n, extra=order
                )
            )
    out: list[RepairOrder] = []
    seen: set[str] = set()
    for o in touched:
        if o.id in seen:
            continue
        seen.add(o.id)
        out.append(o)
    return out


def sync_queue_after_assign(
    store: Any,
    order: RepairOrder,
    item_id: str,
    *,
    prev_tech_id: str = "",
    prev_tech_name: str = "",
    prev_lane: str = "daily",
) -> list[RepairOrder]:
    """Stamp queue_order on assign/unassign and compact the previous tech's path."""
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        return [order]
    tid = (target.assigned_to_id or "").strip()
    tname = (target.assigned_to_name or "").strip()
    lane = normalize_queue_lane(target.queue_lane, default="daily")
    if tid or tname:
        ensure_queue_order_on_assign(store, order, item_id)
    else:
        target.queue_order = 0
        order.work_items = work_items_to_dicts(items)
    from carro.core.assignment import matches_tech

    same = matches_tech(
        prev_tech_id, prev_tech_name, me_id=tid, me_name=tname
    )
    prev_n = normalize_queue_lane(prev_lane, default="daily")
    touched = [order]
    if (prev_tech_id or prev_tech_name) and (not same or prev_n != lane):
        if prev_n in ("daily", "next_day"):
            touched.extend(
                rebalance_tech_lane(
                    store,
                    tech_id=prev_tech_id,
                    tech_name=prev_tech_name,
                    lane=prev_n,
                    extra=order,
                )
            )
    out: list[RepairOrder] = []
    seen: set[str] = set()
    for o in touched:
        if o.id in seen:
            continue
        seen.add(o.id)
        out.append(o)
    return out


def rebalance_after_rollover(store: Any, changed: list[RepairOrder]) -> list[RepairOrder]:
    """After next_day → daily, compact each affected tech's today path."""
    techs: dict[str, tuple[str, str]] = {}
    for order in changed:
        for w in ensure_work_items_on_order(order):
            if not _item_open(w):
                continue
            if normalize_queue_lane(w.queue_lane, default="daily") != "daily":
                continue
            tid = (w.assigned_to_id or "").strip()
            tname = (w.assigned_to_name or "").strip()
            if not tid and not tname:
                continue
            techs[f"{tid}|{tname}"] = (tid, tname)
    touched: list[RepairOrder] = []
    for tid, tname in techs.values():
        touched.extend(
            rebalance_tech_lane(
                store,
                tech_id=tid,
                tech_name=tname,
                lane="daily",
                extra=changed[0] if changed else None,
                extras=changed,
            )
        )
    out: list[RepairOrder] = []
    seen: set[str] = set()
    for o in touched:
        if o.id in seen:
            continue
        seen.add(o.id)
        out.append(o)
    return out
