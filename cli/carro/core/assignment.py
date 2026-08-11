"""RO / work-item technician assignment helpers."""

from __future__ import annotations

from typing import Any

from carro.core.models import RepairOrder, now_iso
from carro.core.work_items import ensure_work_items_on_order, work_items_to_dicts


def assign_ro(
    order: RepairOrder,
    *,
    tech_id: str = "",
    tech_name: str = "",
    set_status_assigned: bool = True,
) -> None:
    """Assign (or clear) the whole RO to a technician."""
    tid = (tech_id or "").strip()
    tname = (tech_name or "").strip()
    if not tid and not tname:
        order.assigned_to_id = ""
        order.assigned_to_name = ""
        order.assigned_at = ""
        return
    order.assigned_to_id = tid
    order.assigned_to_name = tname
    order.assigned_at = now_iso()
    if set_status_assigned and order.status in ("", "open"):
        order.status = "assigned"


def clear_current_task(order: RepairOrder) -> None:
    from carro.core.queue_lanes import apply_pending_queue_lane
    from carro.core.work_items import stop_all_work_timers

    wid = (order.current_item_id or "").strip()
    # Bank any running work-item timers before leaving the bay task
    stop_all_work_timers(order)
    if wid:
        apply_pending_queue_lane(order, wid)
    order.current_tech_id = ""
    order.current_tech_name = ""
    order.current_since = ""
    order.current_item_id = ""


def set_current_task(
    order: RepairOrder,
    *,
    tech_id: str,
    tech_name: str,
    item_id: str = "",
    also_assign: bool = True,
) -> None:
    """
    Current bay work is always a work item (itemized concern), never just the RO/car.
    Starts that item's timer; banks other item timers on this RO.
    """
    from carro.core.work_items import (
        ensure_work_items_on_order,
        pick_default_work_item_id,
        start_work_timer,
    )

    tid = (tech_id or "").strip()
    tname = (tech_name or "").strip()
    if not tid and not tname:
        clear_current_task(order)
        return

    ensure_work_items_on_order(order)
    wid = (item_id or "").strip() or pick_default_work_item_id(order)
    if not wid:
        raise ValueError(
            "Add a work item before setting current work — the RO is the car, items are the jobs"
        )

    if also_assign:
        assign_work_item(order, wid, tech_id=tid, tech_name=tname)
    start_work_timer(order, wid, tech_id=tid, tech_name=tname)
    order.current_tech_id = tid
    order.current_tech_name = tname
    order.current_since = now_iso()
    order.current_item_id = wid
    if not (order.started_at or "").strip():
        order.started_at = now_iso()
    order.done_at = ""
    order.billed_out_at = ""
    rollup_ro_status_from_items(order)


def add_to_my_queue(
    order: RepairOrder,
    *,
    tech_id: str,
    tech_name: str,
    item_id: str = "",
) -> None:
    """Plan work: assign a work item to this tech (queue is per concern, not per car)."""
    from carro.core.models import CLOSED_STATUSES
    from carro.core.work_items import ensure_work_items_on_order, pick_default_work_item_id

    if (order.status or "").strip().lower() in CLOSED_STATUSES:
        return
    if order.status == "done":
        reopen_ro(order, tech_id=tech_id, tech_name=tech_name)
    wid = (item_id or "").strip() or pick_default_work_item_id(order)
    if not wid:
        raise ValueError("Add a work item before queuing — queue is per concern, not per car")
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == wid), None)
    if not target:
        raise ValueError(f"Work item not found: {wid}")
    owner = (target.assigned_to_id or "").strip()
    if owner and owner != (tech_id or "").strip():
        raise ValueError(
            "This work item is assigned to another technician — ask an advisor to reassign"
        )
    if not assign_work_item(order, wid, tech_id=tech_id, tech_name=tech_name):
        raise ValueError(f"Work item not found: {wid}")
    if order.status in ("", "open"):
        order.status = "assigned"


def remove_from_my_queue(
    order: RepairOrder,
    *,
    tech_id: str,
    tech_name: str,
    item_id: str = "",
) -> bool:
    """
    Drop a work item from this tech's planned queue.
    Clears current work if they were actively on that item.
    """
    from carro.core.work_items import ensure_work_items_on_order, pick_default_work_item_id

    items = ensure_work_items_on_order(order)
    wid = (item_id or "").strip()
    if not wid and matches_tech(
        order.current_tech_id,
        order.current_tech_name,
        me_id=tech_id,
        me_name=tech_name,
    ):
        wid = (order.current_item_id or "").strip()
    if not wid:
        for w in items:
            if matches_tech(
                w.assigned_to_id,
                w.assigned_to_name,
                me_id=tech_id,
                me_name=tech_name,
            ):
                wid = w.id
                break
    if not wid:
        wid = pick_default_work_item_id(order)
    if not wid:
        return False

    target = next((w for w in items if w.id == wid), None)
    if not target:
        return False
    mine = matches_tech(
        target.assigned_to_id,
        target.assigned_to_name,
        me_id=tech_id,
        me_name=tech_name,
    )
    is_current = (order.current_item_id or "") == wid and matches_tech(
        order.current_tech_id,
        order.current_tech_name,
        me_id=tech_id,
        me_name=tech_name,
    )
    if not mine and not is_current:
        return False
    if mine:
        assign_work_item(order, wid, tech_id="", tech_name="")
    if is_current:
        clear_current_task(order)
    return True


def set_waiting(
    order: RepairOrder,
    *,
    kind: str,
    tech_id: str = "",
    tech_name: str = "",
) -> None:
    """Park the job: waiting_parts or waiting_customer. Clears current bay task."""
    if kind not in ("waiting_parts", "waiting_customer"):
        raise ValueError(f"Unknown waiting kind: {kind}")
    order.status = kind
    order.waiting_since = now_iso()
    if tech_id or tech_name:
        if matches_tech(
            order.current_tech_id,
            order.current_tech_name,
            me_id=tech_id,
            me_name=tech_name,
        ):
            clear_current_task(order)
    else:
        clear_current_task(order)


def rollup_ro_status_from_items(order: RepairOrder) -> None:
    """
    Derive RO shop status from work items.
    Closed statuses (billed / canceled / NCNS) are never set here.
    """
    from carro.core.models import CLOSED_STATUSES

    if (order.status or "").strip().lower() in CLOSED_STATUSES:
        return
    from carro.core.work_items import ensure_work_items_on_order

    items = ensure_work_items_on_order(order)
    if not items:
        if order.status in ("", "done"):
            order.status = "open"
        return

    cur_item = (order.current_item_id or "").strip()
    statuses = [(w.status or "open").strip().lower() for w in items]
    active = [s for s in statuses if s not in ("done", "declined")]

    if cur_item or any(s == "in_progress" for s in statuses):
        order.status = "in_progress"
        order.waiting_since = ""
        order.done_at = ""
        return

    if not active:
        order.status = "done"
        if not (order.done_at or "").strip():
            order.done_at = now_iso()
        order.waiting_since = ""
        return

    order.done_at = ""
    if all(s == "waiting_parts" for s in active):
        order.status = "waiting_parts"
        if not (order.waiting_since or "").strip():
            order.waiting_since = now_iso()
        return
    if all(s == "waiting_customer" for s in active):
        order.status = "waiting_customer"
        if not (order.waiting_since or "").strip():
            order.waiting_since = now_iso()
        return

    # Mixed or open work remaining
    order.waiting_since = ""
    if any(s in ("open", "in_progress") for s in active) or any(
        (w.assigned_to_id or w.assigned_to_name) for w in items if (w.status or "") not in ("done", "declined")
    ):
        has_assign = any(
            (w.assigned_to_id or w.assigned_to_name)
            for w in items
            if (w.status or "").strip().lower() not in ("done", "declined")
        )
        order.status = "assigned" if has_assign else "open"
    else:
        # e.g. mix of waiting_parts + waiting_customer — keep floor-visible
        order.status = "assigned"


def complete_work_item(
    order: RepairOrder,
    item_id: str,
    *,
    tech_id: str = "",
    tech_name: str = "",
) -> None:
    """Mark one work item done — banks timer; RO ready-to-bill when all items finished."""
    from carro.core.models import CLOSED_STATUSES
    from carro.core.queue_lanes import (
        normalize_queue_lane,
        repark_siblings_long_term,
    )
    from carro.core.work_items import (
        ensure_work_items_on_order,
        set_item_status,
        stop_downtime,
        stop_work_timer,
        work_items_to_dicts,
    )

    wid = (item_id or "").strip()
    if not wid:
        raise ValueError("item_id required to complete a work item")
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == wid), None)
    if not target:
        raise ValueError(f"Work item not found: {wid}")
    if (target.timer_started_at or "").strip():
        stop_work_timer(order, wid, bank_between_sessions=False)
    if (order.current_item_id or "").strip() == wid:
        clear_current_task(order)
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == wid), None)
    if not target:
        raise ValueError(f"Work item not found: {wid}")
    stop_downtime(target)
    completed_lane = normalize_queue_lane(
        getattr(target, "queue_lane", None), default="daily"
    )
    set_item_status(target, "done")
    target.updated = now_iso()
    order.work_items = work_items_to_dicts(items)
    rollup_ro_status_from_items(order)

    # Diag done → pending repair request for advisor (found-issues desk flow).
    try:
        from carro.core.found_issues import create_diag_repair_request

        create_diag_repair_request(
            order,
            target,
            actor=tech_name,
            actor_id=tech_id,
        )
    except Exception:
        pass

    # Keep multi-item long-term projects parked until everything is finished.
    if str(order.status or "").strip().lower() not in ("done", *CLOSED_STATUSES):
        items = ensure_work_items_on_order(order)
        sibling_long_term = any(
            normalize_queue_lane(getattr(w, "queue_lane", None), default="daily")
            == "long_term"
            and str(w.status or "").strip().lower() not in ("done", "declined")
            for w in items
            if w.id != wid
        )
        if completed_lane == "long_term" or sibling_long_term:
            repark_siblings_long_term(order, except_id=wid)


def set_work_item_waiting(
    order: RepairOrder,
    item_id: str,
    *,
    kind: str,
    tech_id: str = "",
    tech_name: str = "",
) -> None:
    """Park one work item waiting_parts or waiting_customer; stop its timer."""
    from carro.core.work_items import (
        ensure_work_items_on_order,
        set_item_status,
        stop_downtime,
        stop_work_timer,
        work_items_to_dicts,
    )

    if kind not in ("waiting_parts", "waiting_customer"):
        raise ValueError(f"Unknown waiting kind: {kind}")
    wid = (item_id or "").strip()
    if not wid:
        raise ValueError("item_id required")
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == wid), None)
    if not target:
        raise ValueError(f"Work item not found: {wid}")
    if (target.timer_started_at or "").strip():
        stop_work_timer(order, wid, bank_between_sessions=False)
    if (order.current_item_id or "").strip() == wid:
        clear_current_task(order)
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == wid), None)
    if not target:
        raise ValueError(f"Work item not found: {wid}")
    stop_downtime(target)
    set_item_status(target, kind)
    target.wait_kind = kind
    target.wait_requested_by = (tech_name or "").strip() or (target.assigned_to_name or "").strip()
    target.wait_requested_by_id = (tech_id or "").strip() or (target.assigned_to_id or "").strip()
    target.updated = now_iso()
    ts = now_iso()
    if kind == "waiting_parts":
        order.parts_requested_at = ts
        order.parts_requested_by = (tech_name or "").strip()
        order.parts_requested_by_id = (tech_id or "").strip()
    else:
        order.approval_requested_at = ts
        order.approval_requested_by = (tech_name or "").strip()
        order.approval_requested_by_id = (tech_id or "").strip()
    order.work_items = work_items_to_dicts(items)
    rollup_ro_status_from_items(order)


def release_wait_item(
    order: RepairOrder,
    item_id: str,
    *,
    return_to_requester: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    """
    Clear waiting_parts / waiting_customer on one item.

    Default: open + Unassigned (any available tech can pick it up).
    return_to_requester=True: assign back to wait_requested_by (the tech who parked it).
    """
    from carro.core.work_items import (
        ensure_work_items_on_order,
        set_item_status,
        work_items_to_dicts,
    )

    wid = (item_id or "").strip()
    if not wid:
        raise ValueError("item_id required")
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == wid), None)
    if not target:
        raise ValueError(f"Work item not found: {wid}")
    st = (target.status or "").strip().lower()
    if st not in ("waiting_parts", "waiting_customer"):
        raise ValueError("Work item is not waiting on parts or customer")

    if (order.current_item_id or "").strip() == wid:
        clear_current_task(order)
        items = ensure_work_items_on_order(order)
        target = next((w for w in items if w.id == wid), None)
        if not target:
            raise ValueError(f"Work item not found: {wid}")

    # Prefer stamped requester; fall back to current assignee (legacy waits).
    req_id = (
        target.wait_requested_by_id or target.assigned_to_id or ""
    ).strip()
    req_name = (
        target.wait_requested_by or target.assigned_to_name or ""
    ).strip()
    set_item_status(target, "open")
    target.wait_kind = ""
    if return_to_requester and (req_id or req_name):
        target.assigned_to_id = req_id
        target.assigned_to_name = req_name
        target.assigned_at = now_iso()
    else:
        target.assigned_to_id = ""
        target.assigned_to_name = ""
        target.assigned_at = ""
    target.wait_requested_by = ""
    target.wait_requested_by_id = ""
    target.updated = now_iso()
    order.work_items = work_items_to_dicts(items)
    rollup_ro_status_from_items(order)
    return {
        "item_id": wid,
        "return_to_requester": bool(return_to_requester and (req_id or req_name)),
        "assigned_to_id": target.assigned_to_id,
        "assigned_to_name": target.assigned_to_name,
        "requester_id": req_id,
        "requester_name": req_name,
        "reason": (reason or "").strip(),
    }


def request_parts(
    order: RepairOrder,
    *,
    tech_id: str = "",
    tech_name: str = "",
    item_id: str = "",
) -> None:
    """
    Prefer item-scoped wait when item_id is given.
    Legacy: park whole RO when no item_id (advisor / wrong-part path).
    """
    wid = (item_id or "").strip() or (order.current_item_id or "").strip()
    if wid:
        set_work_item_waiting(
            order,
            wid,
            kind="waiting_parts",
            tech_id=tech_id,
            tech_name=tech_name,
        )
        return
    set_waiting(
        order,
        kind="waiting_parts",
        tech_id=tech_id,
        tech_name=tech_name,
    )
    order.parts_requested_at = now_iso()
    order.parts_requested_by = (tech_name or "").strip()
    order.parts_requested_by_id = (tech_id or "").strip()


def request_customer_approval(
    order: RepairOrder,
    *,
    tech_id: str = "",
    tech_name: str = "",
    item_id: str = "",
) -> None:
    wid = (item_id or "").strip() or (order.current_item_id or "").strip()
    if wid:
        set_work_item_waiting(
            order,
            wid,
            kind="waiting_customer",
            tech_id=tech_id,
            tech_name=tech_name,
        )
        return
    set_waiting(
        order,
        kind="waiting_customer",
        tech_id=tech_id,
        tech_name=tech_name,
    )
    order.approval_requested_at = now_iso()
    order.approval_requested_by = (tech_name or "").strip()
    order.approval_requested_by_id = (tech_id or "").strip()


def complete_ro(order: RepairOrder, *, tech_id: str = "", tech_name: str = "") -> None:
    """
    Mark all open work items done (or RO done if none), then ready-to-bill.
    Prefer complete_work_item for bay tech UX.
    """
    from carro.core.work_items import (
        ensure_work_items_on_order,
        set_item_status,
        stop_all_work_timers,
        work_items_to_dicts,
    )

    stop_all_work_timers(order)
    clear_current_task(order)
    items = ensure_work_items_on_order(order)
    for w in items:
        if (w.status or "").strip().lower() not in ("done", "declined"):
            set_item_status(w, "done")
            w.updated = now_iso()
    order.work_items = work_items_to_dicts(items)
    order.status = "done"
    order.done_at = now_iso()
    order.waiting_since = ""


def reopen_ro(order: RepairOrder, *, tech_id: str = "", tech_name: str = "") -> None:
    """
    Undo done (ready-to-bill) or archived close (billed / canceled / NCNS).
    Puts the RO on the acting tech's queue when tech_id/name are given.
    """
    from carro.core.models import CLOSED_STATUSES

    st = (order.status or "").strip().lower()
    if st not in ("done", *CLOSED_STATUSES):
        raise ValueError("Only done or archived ROs can be reopened")
    order.done_at = ""
    order.billed_out_at = ""
    order.canceled_at = ""
    order.no_call_no_show_at = ""
    order.waiting_since = ""
    clear_current_task(order)
    tid = (tech_id or "").strip()
    tname = (tech_name or "").strip()
    if tid or tname:
        assign_ro(order, tech_id=tid, tech_name=tname, set_status_assigned=False)
        order.status = "assigned"
    elif (order.assigned_to_id or "").strip() or (order.assigned_to_name or "").strip():
        order.status = "assigned"
    else:
        order.status = "open"


def bill_out_ro(order: RepairOrder, *, tech_id: str = "", tech_name: str = "") -> None:
    """
    Final close: accounting done, car left / billed.
    Keeps all RO data (VIN, work items, notes, assignee) for vehicle history —
    only clears the current bay task and sets status/timestamps.
    """
    from carro.core.found_issues import close_pending_found_issues_on_bill_out

    close_pending_found_issues_on_bill_out(
        order, actor=tech_name or "system", actor_id=tech_id
    )
    if not (order.done_at or "").strip():
        order.done_at = now_iso()
    order.status = "billed_out"
    order.billed_out_at = now_iso()
    order.canceled_at = ""
    order.no_call_no_show_at = ""
    order.waiting_since = ""
    # Do not clear assigned_to_* — history and reopen need who closed the job.
    clear_current_task(order)


def archive_ro(
    order: RepairOrder,
    status: str,
    *,
    tech_id: str = "",
    tech_name: str = "",
) -> None:
    """
    Archive without billing: canceled appointment or no-call/no-show.
    Separate from billed_out so each can be filtered and reopened later.
    """
    from carro.core.models import ARCHIVE_STATUSES

    st = (status or "").strip().lower()
    if st not in ARCHIVE_STATUSES:
        raise ValueError("Archive status must be canceled or no_call_no_show")
    from carro.core.found_issues import close_pending_found_issues_on_bill_out

    close_pending_found_issues_on_bill_out(
        order, actor=tech_name or "system", actor_id=tech_id
    )
    ts = now_iso()
    order.status = st
    order.waiting_since = ""
    order.billed_out_at = ""
    if st == "canceled":
        order.canceled_at = ts
        order.no_call_no_show_at = ""
    else:
        order.no_call_no_show_at = ts
        order.canceled_at = ""
    clear_current_task(order)


def clear_tech_current_elsewhere(
    orders: list[RepairOrder],
    *,
    tech_id: str,
    tech_name: str,
    except_id: str = "",
) -> list[RepairOrder]:
    """Clear current-task on other ROs for this tech. Returns mutated orders."""
    cleared: list[RepairOrder] = []
    for order in orders:
        if except_id and order.id == except_id:
            continue
        if not (order.current_tech_id or order.current_tech_name):
            continue
        if matches_tech(
            order.current_tech_id,
            order.current_tech_name,
            me_id=tech_id,
            me_name=tech_name,
        ):
            clear_current_task(order)
            cleared.append(order)
    return cleared


def assign_work_item(
    order: RepairOrder,
    item_id: str,
    *,
    tech_id: str = "",
    tech_name: str = "",
    due_eod: bool | None = None,
) -> bool:
    """Assign (or clear) a single work item — the unit of planned / billed work."""
    from carro.core.queue_lanes import ensure_daily_on_assign

    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        return False
    tid = (tech_id or "").strip()
    tname = (tech_name or "").strip()
    if not tid and not tname:
        target.assigned_to_id = ""
        target.assigned_to_name = ""
        target.assigned_at = ""
        target.due_eod = False
    else:
        target.assigned_to_id = tid
        target.assigned_to_name = tname
        target.assigned_at = now_iso()
        ensure_daily_on_assign(target)
        if due_eod is not None:
            target.due_eod = bool(due_eod)
    target.updated = now_iso()
    order.work_items = work_items_to_dicts(items)
    return True


def _tech_key(tech_id: str, tech_name: str) -> str:
    tid = (tech_id or "").strip().lower()
    if tid:
        return f"id:{tid}"
    name = (tech_name or "").strip().lower()
    if name:
        return f"name:{name}"
    return ""


def matches_tech(tech_id: str, tech_name: str, *, me_id: str, me_name: str) -> bool:
    mid = (me_id or "").strip().lower()
    mname = (me_name or "").strip().lower()
    tid = (tech_id or "").strip().lower()
    tname = (tech_name or "").strip().lower()
    if mid and tid and mid == tid:
        return True
    if mname and tname and mname == tname:
        return True
    return False


def order_involves_tech(order: RepairOrder | dict[str, Any], *, tech_id: str, tech_name: str) -> bool:
    if isinstance(order, RepairOrder):
        d = order.to_dict()
    else:
        d = order
    if matches_tech(
        str(d.get("assigned_to_id") or ""),
        str(d.get("assigned_to_name") or ""),
        me_id=tech_id,
        me_name=tech_name,
    ):
        return True
    if matches_tech(
        str(d.get("current_tech_id") or ""),
        str(d.get("current_tech_name") or ""),
        me_id=tech_id,
        me_name=tech_name,
    ):
        return True
    for it in d.get("work_items") or []:
        if not isinstance(it, dict):
            continue
        if matches_tech(
            str(it.get("assigned_to_id") or it.get("notes_by_id") or ""),
            str(it.get("assigned_to_name") or it.get("notes_by") or ""),
            me_id=tech_id,
            me_name=tech_name,
        ):
            return True
    return False


def summarize_order_for_board(order: RepairOrder | dict[str, Any]) -> dict[str, Any]:
    if isinstance(order, RepairOrder):
        d = order.to_dict()
    else:
        d = dict(order)
    items = [it for it in (d.get("work_items") or []) if isinstance(it, dict)]
    statuses = [(it.get("status") or "open").strip().lower() for it in items]
    items_done = sum(1 for s in statuses if s == "done")
    items_declined = sum(1 for s in statuses if s == "declined")
    items_open = sum(1 for s in statuses if s not in ("done", "declined"))
    open_concerns = [
        (it.get("concern") or "").strip()[:80]
        for it, s in zip(items, statuses)
        if s not in ("done", "declined") and (it.get("concern") or "").strip()
    ][:6]
    from carro.core.work_items import tech_time_breakdown

    tech_worked = [
        {
            "tech_id": str(b.get("tech_id") or ""),
            "tech_name": str(b.get("tech_name") or "Unknown"),
            "minutes": max(0, int(b.get("minutes") or 0)),
        }
        for b in tech_time_breakdown(order)
        if max(0, int(b.get("minutes") or 0)) > 0
    ]
    return {
        "id": d.get("id") or "",
        "customer": f"{d.get('last_name') or ''}, {d.get('first_name') or ''}".strip(", ").strip()
        or "(no customer)",
        "vehicle": " ".join(
            str(x) for x in (d.get("year"), d.get("make"), d.get("model")) if x
        ).strip()
        or "(no vehicle)",
        "vin": d.get("vin") or "",
        "status": d.get("status") or "open",
        "assigned_to_id": d.get("assigned_to_id") or "",
        "assigned_to_name": d.get("assigned_to_name") or "",
        "assigned_at": d.get("assigned_at") or "",
        "current_tech_id": d.get("current_tech_id") or "",
        "current_tech_name": d.get("current_tech_name") or "",
        "current_since": d.get("current_since") or "",
        "current_item_id": d.get("current_item_id") or "",
        "started_at": d.get("started_at") or "",
        "done_at": d.get("done_at") or "",
        "billed_out_at": d.get("billed_out_at") or "",
        "canceled_at": d.get("canceled_at") or "",
        "no_call_no_show_at": d.get("no_call_no_show_at") or "",
        "waiting_since": d.get("waiting_since") or "",
        "parts_requested_at": d.get("parts_requested_at") or "",
        "parts_requested_by": d.get("parts_requested_by") or "",
        "approval_requested_at": d.get("approval_requested_at") or "",
        "approval_requested_by": d.get("approval_requested_by") or "",
        "waiter": bool(d.get("waiter")),
        "urgent": bool(d.get("urgent")),
        "worked_minutes": sum(
            max(0, int(it.get("worked_minutes") or 0)) for it in items
        ),
        "tech_worked": tech_worked,
        "items_total": len(items),
        "items_done": items_done,
        "items_declined": items_declined,
        "items_open": items_open,
        "open_concerns": open_concerns,
        "created": d.get("created") or "",
        "updated": d.get("updated") or d.get("created") or "",
        "work_items": [
            {
                "id": it.get("id") or "",
                "concern": (it.get("concern") or "")[:120],
                "status": it.get("status") or "open",
                "assigned_to_id": it.get("assigned_to_id") or it.get("notes_by_id") or "",
                "assigned_to_name": it.get("assigned_to_name")
                or it.get("notes_by")
                or "",
                "created_by": it.get("created_by") or "",
                "created_by_role": it.get("created_by_role") or "",
                "notes_by": it.get("notes_by") or "",
                "worked_minutes": int(it.get("worked_minutes") or 0),
                "worked_first_at": it.get("worked_first_at") or "",
                "worked_last_at": it.get("worked_last_at") or "",
                "timer_started_at": it.get("timer_started_at") or "",
            }
            for it in items
        ],
    }


def summarize_item_job(
    order: RepairOrder | dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any]:
    """One queued / current work unit: work item + car context from the RO."""
    from carro.core.queue_lanes import normalize_next_day_request, normalize_queue_lane
    from carro.core.work_items import (
        live_stage_minutes,
        normalize_stage_totals,
        stage_total_with_live,
        total_downtime_minutes,
    )

    if isinstance(order, RepairOrder):
        d = order.to_dict()
    else:
        d = dict(order)
    cur_item = str(d.get("current_item_id") or "")
    wid = str(item.get("id") or "")
    istatus = str(item.get("status") or "open")
    totals = normalize_stage_totals(item.get("stage_totals"))
    req = normalize_next_day_request(item.get("next_day_request"))
    return {
        "id": f"{d.get('id') or ''}:{wid}",  # unique key for lists
        "ro_id": d.get("id") or "",
        "item_id": wid,
        "concern": (item.get("concern") or "")[:160],
        "item_status": istatus,
        "item_type": item.get("item_type") or "",
        "customer": f"{d.get('last_name') or ''}, {d.get('first_name') or ''}".strip(", ").strip()
        or "(no customer)",
        "vehicle": " ".join(
            str(x) for x in (d.get("year"), d.get("make"), d.get("model")) if x
        ).strip()
        or "(no vehicle)",
        "vin": d.get("vin") or "",
        "ro_status": d.get("status") or "open",
        "waiter": bool(d.get("waiter")),
        "urgent": bool(d.get("urgent")),
        "queue_lane": normalize_queue_lane(item.get("queue_lane"), default="daily"),
        "pending_queue_lane": str(item.get("pending_queue_lane") or "").strip(),
        "queue_day": str(item.get("queue_day") or "").strip(),
        "due_eod": bool(item.get("due_eod")),
        "next_day_request": req,
        "assigned_to_id": item.get("assigned_to_id") or "",
        "assigned_to_name": item.get("assigned_to_name") or "",
        "assigned_at": item.get("assigned_at") or "",
        "wait_requested_by": item.get("wait_requested_by") or "",
        "wait_requested_by_id": item.get("wait_requested_by_id") or "",
        "wait_kind": item.get("wait_kind") or "",
        "worked_minutes": int(item.get("worked_minutes") or 0),
        "worked_first_at": item.get("worked_first_at") or "",
        "worked_last_at": item.get("worked_last_at") or "",
        "timer_started_at": item.get("timer_started_at") or "",
        "timer_tech_name": item.get("timer_tech_name") or "",
        "stage_entered_at": item.get("stage_entered_at") or "",
        "stage_totals": totals,
        "waiting_parts_minutes": stage_total_with_live(item, "waiting_parts_minutes"),
        "waiting_customer_minutes": stage_total_with_live(
            item, "waiting_customer_minutes"
        ),
        "stage_live_minutes": live_stage_minutes(item),
        "downtime_minutes": total_downtime_minutes(item),
        "is_current": bool(cur_item and cur_item == wid),
        "current_tech_id": d.get("current_tech_id") or "",
        "current_tech_name": d.get("current_tech_name") or "",
        "current_since": d.get("current_since") or "",
        "updated": item.get("updated") or d.get("updated") or d.get("created") or "",
        "from_found_issue_id": "",
    }


def build_assigned_board(
    orders: list[RepairOrder | dict[str, Any]],
    *,
    tech_id: str = "",
    tech_name: str = "",
) -> dict[str, Any]:
    """
    Assigned Work is work-item centric:
    - mine / mine_daily / mine_next_day / mine_long_term
    - next_day / long_term / long_term_unassigned / long_term_by_tech / daily_by_tech
    - unassigned / by_tech / now_working / waiting_* = itemized jobs
    - ready_to_bill / billed_out = car-level RO stages (advisor handoff)
    - waiting_other_items = some items done, others still open (advisor billing watch)

    Current work items appear under now_working (in progress) and are omitted
    from daily/next_day/long_term lane lists.
    """
    from carro.core.queue_lanes import normalize_queue_lane

    mine: list[dict[str, Any]] = []
    mine_daily: list[dict[str, Any]] = []
    mine_next_day: list[dict[str, Any]] = []
    mine_long_term: list[dict[str, Any]] = []
    next_day: list[dict[str, Any]] = []
    long_term: list[dict[str, Any]] = []
    long_term_unassigned: list[dict[str, Any]] = []
    long_term_by_tech: dict[str, dict[str, Any]] = {}
    waiting_parts: list[dict[str, Any]] = []
    waiting_customer: list[dict[str, Any]] = []
    found_issues_pending: list[dict[str, Any]] = []
    ready_to_bill: list[dict[str, Any]] = []
    waiting_other_items: list[dict[str, Any]] = []
    billed_out: list[dict[str, Any]] = []
    canceled: list[dict[str, Any]] = []
    no_call_no_show: list[dict[str, Any]] = []
    by_tech: dict[str, dict[str, Any]] = {}
    daily_by_tech: dict[str, dict[str, Any]] = {}
    unassigned: list[dict[str, Any]] = []
    now_working: list[dict[str, Any]] = []
    my_current: dict[str, Any] | None = None
    defer_requests: list[dict[str, Any]] = []

    from carro.core.models import CLOSED_STATUSES

    def _lane_bucket(job: dict[str, Any]) -> None:
        lane = normalize_queue_lane(job.get("queue_lane"), default="daily")
        if lane == "next_day":
            next_day.append(job)
        elif lane == "long_term":
            long_term.append(job)
            aid = str(job.get("assigned_to_id") or "")
            aname = str(job.get("assigned_to_name") or "")
            key = _tech_key(aid, aname)
            if not key:
                long_term_unassigned.append(job)
            else:
                bucket = long_term_by_tech.setdefault(
                    key,
                    {
                        "id": aid,
                        "name": aname or aid or "Unknown",
                        "jobs": [],
                    },
                )
                if not any(j.get("id") == job["id"] for j in bucket["jobs"]):
                    bucket["jobs"].append(job)
        else:
            aid = str(job.get("assigned_to_id") or "")
            aname = str(job.get("assigned_to_name") or "")
            key = _tech_key(aid, aname)
            if key:
                bucket = daily_by_tech.setdefault(
                    key,
                    {
                        "id": aid,
                        "name": aname or aid or "Unknown",
                        "jobs": [],
                    },
                )
                if not any(j.get("id") == job["id"] for j in bucket["jobs"]):
                    bucket["jobs"].append(job)

    for order in orders:
        from carro.core.work_items import sanitize_open_time_segments

        if isinstance(order, RepairOrder):
            sanitize_open_time_segments(order)
        summary = summarize_order_for_board(order)
        d = order.to_dict() if isinstance(order, RepairOrder) else dict(order)
        cur_id = str(d.get("current_tech_id") or "")
        cur_name = str(d.get("current_tech_name") or "")
        cur_item = str(d.get("current_item_id") or "")
        status = str(d.get("status") or "")
        raw_items = [it for it in (d.get("work_items") or []) if isinstance(it, dict)]

        if status == "done":
            ready_to_bill.append(summary)
        elif status == "billed_out":
            billed_out.append(summary)
        elif status == "canceled":
            canceled.append(summary)
        elif status == "no_call_no_show":
            no_call_no_show.append(summary)
        else:
            n_done = int(summary.get("items_done") or 0)
            n_open = int(summary.get("items_open") or 0)
            if n_done > 0 and n_open > 0:
                from carro.core.queue_lanes import order_open_items_all_long_term

                # Long-term-only partial ROs stay in Queues — not Floor "waiting on other".
                if not order_open_items_all_long_term(order):
                    waiting_other_items.append(summary)

        from carro.core.found_issues import summarize_found_issue_for_board

        fi_by_work_item: dict[str, str] = {}
        for fi in d.get("found_issues") or []:
            if not isinstance(fi, dict):
                continue
            fi_status = str(fi.get("status") or "")
            if fi_status == "pending":
                found_issues_pending.append(summarize_found_issue_for_board(d, fi))
            elif fi_status == "converted":
                linked = str(fi.get("work_item_id") or "").strip()
                fid = str(fi.get("id") or "").strip()
                if linked and fid:
                    fi_by_work_item[linked] = fid

        def _stamp_fi(job: dict[str, Any]) -> dict[str, Any]:
            linked_fi = fi_by_work_item.get(str(job.get("item_id") or ""), "")
            if linked_fi:
                job["from_found_issue_id"] = linked_fi
            return job

        # Working now = tech + specific work item
        if cur_id or cur_name:
            current_item = next((it for it in raw_items if it.get("id") == cur_item), None)
            job = (
                _stamp_fi(summarize_item_job(d, current_item))
                if current_item
                else {
                    "id": f"{d.get('id')}:",
                    "ro_id": d.get("id") or "",
                    "item_id": cur_item,
                    "concern": "(no work item selected)",
                    "item_status": "",
                    "customer": summary.get("customer") or "",
                    "vehicle": summary.get("vehicle") or "",
                    "vin": summary.get("vin") or "",
                    "ro_status": status,
                    "waiter": bool(d.get("waiter")),
                    "urgent": bool(d.get("urgent")),
                    "is_current": True,
                    "current_tech_id": cur_id,
                    "current_tech_name": cur_name,
                    "current_since": summary.get("current_since") or "",
                    "worked_minutes": 0,
                    "from_found_issue_id": fi_by_work_item.get(str(cur_item or ""), ""),
                }
            )
            entry = {
                "tech_id": cur_id,
                "tech_name": cur_name,
                "since": summary.get("current_since") or "",
                "item_id": cur_item,
                "order": summary,
                "job": job,
                "is_me": matches_tech(cur_id, cur_name, me_id=tech_id, me_name=tech_name),
            }
            now_working.append(entry)
            if entry["is_me"]:
                my_current = job

        if status in CLOSED_STATUSES:
            continue

        for it in raw_items:
            istatus = str(it.get("status") or "open")
            if istatus == "declined":
                continue
            if istatus == "done":
                continue
            job = _stamp_fi(summarize_item_job(d, it))
            req = job.get("next_day_request") or {}
            if isinstance(req, dict) and req.get("status") == "pending":
                defer_requests.append(job)
            if istatus == "waiting_parts":
                waiting_parts.append(job)
                continue
            if istatus == "waiting_customer":
                waiting_customer.append(job)
                continue
            if status == "done":
                continue

            # In-progress (current) stays out of lane lists
            if job.get("is_current"):
                aid = str(it.get("assigned_to_id") or "")
                aname = str(it.get("assigned_to_name") or "")
                if matches_tech(aid, aname, me_id=tech_id, me_name=tech_name):
                    mine.append(job)
                continue

            lane = normalize_queue_lane(job.get("queue_lane"), default="daily")
            aid = str(it.get("assigned_to_id") or "")
            aname = str(it.get("assigned_to_name") or "")
            if matches_tech(aid, aname, me_id=tech_id, me_name=tech_name):
                mine.append(job)
                if lane == "next_day":
                    mine_next_day.append(job)
                elif lane == "long_term":
                    mine_long_term.append(job)
                else:
                    mine_daily.append(job)
                _lane_bucket(job)
                continue
            if not aid and not aname:
                # Long-term parks only under Queues → Unassigned long-term.
                if lane != "long_term":
                    unassigned.append(job)
                _lane_bucket(job)
                continue
            key = _tech_key(aid, aname)
            if not key:
                if lane != "long_term":
                    unassigned.append(job)
                _lane_bucket(job)
                continue
            # Long-term assigned jobs stay in Queues (long_term_by_tech), not Floor by_tech.
            if lane == "long_term":
                _lane_bucket(job)
                continue
            bucket = by_tech.setdefault(
                key,
                {
                    "id": aid,
                    "name": aname or aid or "Unknown",
                    "orders": [],
                    "jobs": [],
                    "current": None,
                },
            )
            if not any(j.get("id") == job["id"] for j in bucket["jobs"]):
                bucket["jobs"].append(job)
            if not any(o.get("id") == summary["id"] for o in bucket["orders"]):
                bucket["orders"].append(summary)
            if cur_item == job["item_id"] and matches_tech(
                cur_id, cur_name, me_id=aid, me_name=aname
            ):
                bucket["current"] = job
            _lane_bucket(job)

    def sort_floor(lst: list[dict[str, Any]]) -> None:
        # waiter → urgent → due_eod → newer updated first
        lst.sort(key=lambda o: str(o.get("updated") or ""), reverse=True)
        lst.sort(
            key=lambda o: (
                0 if o.get("waiter") else 1,
                0 if o.get("urgent") else 1,
                0 if o.get("due_eod") else 1,
            )
        )

    by_tech_list = sorted(by_tech.values(), key=lambda b: (b.get("name") or "").lower())
    daily_by_tech_list = sorted(
        daily_by_tech.values(), key=lambda b: (b.get("name") or "").lower()
    )
    long_term_by_tech_list = sorted(
        long_term_by_tech.values(), key=lambda b: (b.get("name") or "").lower()
    )
    for lst in (
        mine,
        mine_daily,
        mine_next_day,
        mine_long_term,
        next_day,
        long_term,
        long_term_unassigned,
        unassigned,
        waiting_parts,
        waiting_customer,
        defer_requests,
    ):
        sort_floor(lst)
    found_issues_pending.sort(key=lambda o: o.get("found_at") or "", reverse=True)
    for lst in (ready_to_bill, waiting_other_items, billed_out, canceled, no_call_no_show):
        lst.sort(key=lambda o: o.get("updated") or "", reverse=True)
    billed_out.sort(
        key=lambda o: o.get("billed_out_at") or o.get("updated") or "",
        reverse=True,
    )
    canceled.sort(
        key=lambda o: o.get("canceled_at") or o.get("updated") or "",
        reverse=True,
    )
    no_call_no_show.sort(
        key=lambda o: o.get("no_call_no_show_at") or o.get("updated") or "",
        reverse=True,
    )
    now_working.sort(key=lambda e: (e.get("tech_name") or "").lower())
    for b in by_tech_list:
        sort_floor(b["jobs"])
        b["orders"].sort(key=lambda o: o.get("updated") or "", reverse=True)
    for b in daily_by_tech_list:
        sort_floor(b["jobs"])
    for b in long_term_by_tech_list:
        sort_floor(b["jobs"])

    return {
        "mine": mine,
        "mine_daily": mine_daily,
        "mine_next_day": mine_next_day,
        "mine_long_term": mine_long_term,
        "next_day": next_day,
        "long_term": long_term,
        "long_term_unassigned": long_term_unassigned,
        "long_term_by_tech": long_term_by_tech_list,
        "daily_by_tech": daily_by_tech_list,
        "defer_requests": defer_requests,
        "waiting_parts": waiting_parts,
        "waiting_customer": waiting_customer,
        "found_issues_pending": found_issues_pending,
        "waiting_other_items": waiting_other_items,
        "ready_to_bill": ready_to_bill,
        "billed_out": billed_out,
        "canceled": canceled,
        "no_call_no_show": no_call_no_show,
        "by_tech": by_tech_list,
        "unassigned": unassigned,
        "now_working": now_working,
        "my_current": my_current,
        "tech_id": tech_id,
        "tech_name": tech_name,
    }
