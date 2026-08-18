"""PWA / server-side clock onto a work item (job timer)."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _matches_tech(tech_id: str, tech_name: str, *, me_id: str, me_name: str) -> bool:
    mid = (me_id or "").strip().lower()
    mname = (me_name or "").strip().lower()
    tid = (tech_id or "").strip().lower()
    tname = (tech_name or "").strip().lower()
    if mid and tid and mid == tid:
        return True
    if mname and tname and mname == tname:
        return True
    return False


def _elapsed_minutes(started_at: str) -> int:
    raw = (started_at or "").strip()
    if not raw:
        return 0
    try:
        start = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if start.tzinfo is not None:
            start = start.replace(tzinfo=None)
        end = datetime.now()
    except ValueError:
        return 0
    if start > end:
        start = end
    return max(0, int((end - start).total_seconds() // 60))


def _items(order: dict[str, Any]) -> list[dict[str, Any]]:
    raw = order.get("work_items")
    if not isinstance(raw, list):
        return []
    return [it for it in raw if isinstance(it, dict)]


def _stop_item_timer(item: dict[str, Any]) -> int:
    started = str(item.get("timer_started_at") or "").strip()
    if not started:
        return 0
    mins = _elapsed_minutes(started)
    tech_id = str(item.get("timer_tech_id") or "")
    tech_name = str(item.get("timer_tech_name") or "")
    item["timer_started_at"] = ""
    item["timer_tech_id"] = ""
    item["timer_tech_name"] = ""
    if mins > 0:
        worked = 0
        try:
            worked = max(0, int(item.get("worked_minutes") or 0))
        except (TypeError, ValueError):
            worked = 0
        item["worked_minutes"] = worked + mins
        log = item.get("time_log")
        if not isinstance(log, list):
            log = []
        log.append(
            {
                "minutes": mins,
                "tech_id": tech_id,
                "tech_name": tech_name,
                "at": now_iso(),
                "note": "timer",
                "source": "timer",
            }
        )
        item["time_log"] = log[-80:]
        item["worked_last_at"] = now_iso()
    return mins


def _sync_ro_current(order: dict[str, Any]) -> None:
    live = [it for it in _items(order) if str(it.get("timer_started_at") or "").strip()]
    if not live:
        order["current_tech_id"] = ""
        order["current_tech_name"] = ""
        order["current_since"] = ""
        order["current_item_id"] = ""
        return
    live.sort(key=lambda it: str(it.get("timer_started_at") or ""), reverse=True)
    top = live[0]
    order["current_tech_id"] = str(top.get("timer_tech_id") or "")
    order["current_tech_name"] = str(top.get("timer_tech_name") or "")
    order["current_since"] = str(top.get("timer_started_at") or "")
    order["current_item_id"] = str(top.get("id") or "")


def release_tech_current(
    order: dict[str, Any],
    *,
    tech_id: str,
    tech_name: str,
    item_id: str = "",
) -> bool:
    wid = (item_id or "").strip()
    stopped = False
    for it in _items(order):
        if not str(it.get("timer_started_at") or "").strip():
            continue
        if wid and str(it.get("id") or "") != wid:
            continue
        if not _matches_tech(
            str(it.get("timer_tech_id") or ""),
            str(it.get("timer_tech_name") or ""),
            me_id=tech_id,
            me_name=tech_name,
        ):
            continue
        _stop_item_timer(it)
        stopped = True
    _sync_ro_current(order)
    if stopped:
        order["updated"] = now_iso()
    return stopped


def start_item_timer(
    order: dict[str, Any],
    *,
    tech_id: str,
    tech_name: str,
    item_id: str,
) -> None:
    items = _items(order)
    if not items:
        raise ValueError("Add a work item before clocking onto a job")
    wid = (item_id or "").strip()
    if not wid:
        openish = [
            it
            for it in items
            if str(it.get("status") or "").lower() not in ("done", "declined")
        ]
        target = openish[0] if openish else items[0]
        wid = str(target.get("id") or "")
    target = next((it for it in items if str(it.get("id") or "") == wid), None)
    if not target:
        raise ValueError("Work item not found")
    for it in items:
        if str(it.get("id") or "") == wid:
            continue
        if not str(it.get("timer_started_at") or "").strip():
            continue
        if _matches_tech(
            str(it.get("timer_tech_id") or ""),
            str(it.get("timer_tech_name") or ""),
            me_id=tech_id,
            me_name=tech_name,
        ):
            _stop_item_timer(it)
    if not str(target.get("timer_started_at") or "").strip():
        target["timer_started_at"] = now_iso()
        target["timer_tech_id"] = tech_id
        target["timer_tech_name"] = tech_name
        if not str(target.get("worked_first_at") or "").strip():
            target["worked_first_at"] = now_iso()
        st = str(target.get("status") or "").lower()
        if st not in ("waiting_parts", "waiting_customer", "done", "declined"):
            target["status"] = "in_progress"
    order["work_items"] = items
    order["current_tech_id"] = tech_id
    order["current_tech_name"] = tech_name
    order["current_since"] = now_iso()
    order["current_item_id"] = wid
    if not str(order.get("started_at") or "").strip():
        order["started_at"] = now_iso()
    st = str(order.get("status") or "").lower()
    if st in ("", "open", "assigned"):
        order["status"] = "in_progress"
    order["updated"] = now_iso()


def tech_has_live_timer(order: dict[str, Any], *, tech_id: str, tech_name: str) -> bool:
    if _matches_tech(
        str(order.get("current_tech_id") or ""),
        str(order.get("current_tech_name") or ""),
        me_id=tech_id,
        me_name=tech_name,
    ) and str(order.get("current_item_id") or "").strip():
        return True
    for it in _items(order):
        if not str(it.get("timer_started_at") or "").strip():
            continue
        if _matches_tech(
            str(it.get("timer_tech_id") or ""),
            str(it.get("timer_tech_name") or ""),
            me_id=tech_id,
            me_name=tech_name,
        ):
            return True
    return False
