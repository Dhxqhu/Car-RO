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
    lane_n = normalize_queue_lane(lane)
    item.queue_lane = lane_n
    if clear_pending:
        item.pending_queue_lane = ""
    if set_day:
        item.queue_day = today_local_iso()
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
    set_queue_lane(target, pending, clear_pending=True, set_day=True)
    req = normalize_next_day_request(target.next_day_request)
    if pending == "next_day" and req.get("status") == "approved":
        # Keep approved status for trail; clear pending arm already done
        pass
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
    """
    lane_n = normalize_queue_lane(lane)
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        raise ValueError(f"Work item not found: {item_id}")
    ensure_queue_defaults(target)
    if approve_request or lane_n == "next_day":
        req = normalize_next_day_request(target.next_day_request)
        if req.get("status") == "pending" or approve_request:
            req["status"] = "approved"
            target.next_day_request = req
    if item_is_current(order, item_id):
        target.pending_queue_lane = lane_n
        target.updated = now_iso()
    else:
        set_queue_lane(target, lane_n, clear_pending=True, set_day=True)
    order.work_items = work_items_to_dicts(items)


def decline_next_day_request(order: RepairOrder, item_id: str) -> None:
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
    """When assigning/picking up, default into today's daily queue."""
    ensure_queue_defaults(item)
    if not (item.queue_lane or "").strip() or item.queue_lane not in QUEUE_LANES:
        set_queue_lane(item, "daily")
    elif item.queue_lane == "daily" and not (item.queue_day or "").strip():
        item.queue_day = today_local_iso()


def rollover_queue_lanes(order: RepairOrder, *, today: str | None = None) -> int:
    """
    Calendar-day rollover (promote before defer so they don't swap):

    1. next_day + queue_day < today → daily (next-day pool becomes today's tasks)
    2. daily + queue_day < today + not current → next_day (left undone overnight)

    Long-term and in-progress (current) items are untouched.
    """
    today_s = (today or today_local_iso()).strip()
    items = ensure_work_items_on_order(order)
    cur = (order.current_item_id or "").strip()
    changed = 0

    for w in items:
        ensure_queue_defaults(w)
        st = (w.status or "").strip().lower()
        if st in ("done", "declined") or w.queue_lane != "next_day":
            continue
        qd = (w.queue_day or "").strip() or today_s
        if qd < today_s:
            set_queue_lane(w, "daily", clear_pending=False, set_day=True)
            changed += 1

    for w in items:
        ensure_queue_defaults(w)
        st = (w.status or "").strip().lower()
        if st in ("done", "declined") or w.queue_lane != "daily":
            continue
        if w.id == cur:
            continue
        qd = (w.queue_day or "").strip() or today_s
        if qd < today_s:
            set_queue_lane(w, "next_day", clear_pending=False, set_day=True)
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
