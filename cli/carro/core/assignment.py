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
    order.current_tech_id = ""
    order.current_tech_name = ""
    order.current_since = ""


def set_current_task(
    order: RepairOrder,
    *,
    tech_id: str,
    tech_name: str,
    also_assign: bool = True,
) -> None:
    """
    Mark this RO as the tech's current bay task.
    Also assigns the RO to them when unassigned, and moves open/assigned → in_progress.
    """
    tid = (tech_id or "").strip()
    tname = (tech_name or "").strip()
    if not tid and not tname:
        clear_current_task(order)
        return
    order.current_tech_id = tid
    order.current_tech_name = tname
    order.current_since = now_iso()
    if also_assign and not (order.assigned_to_id or "").strip() and not (
        order.assigned_to_name or ""
    ).strip():
        assign_ro(order, tech_id=tid, tech_name=tname, set_status_assigned=False)
    if order.status in ("", "open", "assigned"):
        order.status = "in_progress"


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
) -> bool:
    """Assign a single work item to a tech. Returns False if item missing."""
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        return False
    tid = (tech_id or "").strip()
    tname = (tech_name or "").strip()
    target.assigned_to_id = tid
    target.assigned_to_name = tname
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
            }
            for it in items
        ],
    }


def build_assigned_board(
    orders: list[RepairOrder | dict[str, Any]],
    *,
    tech_id: str = "",
    tech_name: str = "",
) -> dict[str, Any]:
    """
    Build Assigned Work view:
    - mine: ROs assigned to me (RO-level or any work item)
    - by_tech: other techs' assigned work (grouped)
    - unassigned: open/assigned ROs with no RO assignee and no item assignees
    """
    mine: list[dict[str, Any]] = []
    by_tech: dict[str, dict[str, Any]] = {}
    unassigned: list[dict[str, Any]] = []
    now_working: list[dict[str, Any]] = []
    my_current: dict[str, Any] | None = None

    for order in orders:
        summary = summarize_order_for_board(order)
        d = order.to_dict() if isinstance(order, RepairOrder) else dict(order)
        ro_aid = str(d.get("assigned_to_id") or "")
        ro_aname = str(d.get("assigned_to_name") or "")
        cur_id = str(d.get("current_tech_id") or "")
        cur_name = str(d.get("current_tech_name") or "")
        item_assignees: list[tuple[str, str]] = []
        for it in d.get("work_items") or []:
            if not isinstance(it, dict):
                continue
            iid = str(it.get("assigned_to_id") or it.get("notes_by_id") or "")
            iname = str(it.get("assigned_to_name") or it.get("notes_by") or "")
            if iid or iname:
                item_assignees.append((iid, iname))

        involves_me = order_involves_tech(d, tech_id=tech_id, tech_name=tech_name)
        if involves_me:
            mine.append(summary)

        if cur_id or cur_name:
            entry = {
                "tech_id": cur_id,
                "tech_name": cur_name,
                "since": summary.get("current_since") or "",
                "order": summary,
                "is_me": matches_tech(cur_id, cur_name, me_id=tech_id, me_name=tech_name),
            }
            now_working.append(entry)
            if entry["is_me"]:
                my_current = summary

        # Collect unique tech keys for this RO (excluding me for by_tech grouping of "others")
        tech_slots: list[tuple[str, str, str]] = []
        if ro_aid or ro_aname:
            tech_slots.append((_tech_key(ro_aid, ro_aname), ro_aid, ro_aname))
        for iid, iname in item_assignees:
            tech_slots.append((_tech_key(iid, iname), iid, iname))
        if cur_id or cur_name:
            tech_slots.append((_tech_key(cur_id, cur_name), cur_id, cur_name))

        seen_keys: set[str] = set()
        any_assignee = False
        for key, tid, tname in tech_slots:
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            any_assignee = True
            if matches_tech(tid, tname, me_id=tech_id, me_name=tech_name):
                continue
            bucket = by_tech.setdefault(
                key,
                {
                    "id": tid,
                    "name": tname or tid or "Unknown",
                    "orders": [],
                    "current": None,
                },
            )
            # Avoid duplicate RO under same tech
            if not any(o.get("id") == summary["id"] for o in bucket["orders"]):
                bucket["orders"].append(summary)
            if matches_tech(cur_id, cur_name, me_id=tid, me_name=tname):
                bucket["current"] = summary

        if not any_assignee and str(d.get("status") or "") not in ("done",):
            unassigned.append(summary)

    by_tech_list = sorted(by_tech.values(), key=lambda b: (b.get("name") or "").lower())
    mine.sort(key=lambda o: o.get("updated") or "", reverse=True)
    unassigned.sort(key=lambda o: o.get("updated") or "", reverse=True)
    now_working.sort(key=lambda e: (e.get("tech_name") or "").lower())
    for b in by_tech_list:
        b["orders"].sort(key=lambda o: o.get("updated") or "", reverse=True)

    return {
        "mine": mine,
        "by_tech": by_tech_list,
        "unassigned": unassigned,
        "now_working": now_working,
        "my_current": my_current,
        "tech_id": tech_id,
        "tech_name": tech_name,
    }
