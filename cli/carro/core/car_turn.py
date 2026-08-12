"""Split-RO car turn: who has the bay first when items go to different techs."""

from __future__ import annotations

from typing import Any

from carro.core.models import RepairOrder

# Items in these statuses still occupy the car (next rank waits).
_OCCUPYING = frozenset({"open", "in_progress"})
_FINISHED = frozenset({"done", "declined"})


def _item_status(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("status") or "open").strip().lower()
    return str(getattr(item, "status", None) or "open").strip().lower()


def _item_id(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("id") or "").strip()
    return str(getattr(item, "id", "") or "").strip()


def _assignee_key(item: Any) -> str:
    if isinstance(item, dict):
        tid = str(item.get("assigned_to_id") or "").strip().lower()
        tname = str(item.get("assigned_to_name") or "").strip().lower()
    else:
        tid = str(getattr(item, "assigned_to_id", "") or "").strip().lower()
        tname = str(getattr(item, "assigned_to_name", "") or "").strip().lower()
    if tid:
        return f"id:{tid}"
    if tname:
        return f"name:{tname}"
    return ""


def _assignee_name(item: Any) -> str:
    if isinstance(item, dict):
        return (
            str(item.get("assigned_to_name") or "").strip()
            or str(item.get("assigned_to_id") or "").strip()
        )
    return (
        str(getattr(item, "assigned_to_name", "") or "").strip()
        or str(getattr(item, "assigned_to_id", "") or "").strip()
    )


def _car_turn(item: Any) -> int:
    try:
        if isinstance(item, dict):
            return max(0, int(item.get("car_turn") or 0))
        return max(0, int(getattr(item, "car_turn", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _set_car_turn(item: Any, turn: int) -> None:
    n = max(0, int(turn))
    if isinstance(item, dict):
        item["car_turn"] = n
    else:
        item.car_turn = n


def open_rankable_items(items: list[Any]) -> list[Any]:
    """Open items that can sit in the 1..N turn list (not done/declined)."""
    return [w for w in items if _item_status(w) not in _FINISHED]


def occupying_items(items: list[Any]) -> list[Any]:
    return [w for w in items if _item_status(w) in _OCCUPYING]


def is_split_ro(order: RepairOrder | dict[str, Any] | Any) -> bool:
    """True when 2+ open items are assigned to 2+ different techs."""
    from carro.core.work_items import ensure_work_items_on_order

    if isinstance(order, dict):
        raw = [it for it in (order.get("work_items") or []) if isinstance(it, dict)]
        items = raw
    else:
        items = ensure_work_items_on_order(order)
    keys = {_assignee_key(w) for w in open_rankable_items(items) if _assignee_key(w)}
    return len(keys) >= 2


def rebalance_car_turns(order: RepairOrder) -> None:
    """Unique 1..N on open items when split; clear turns when not split."""
    from carro.core.work_items import ensure_work_items_on_order, work_items_to_dicts

    items = ensure_work_items_on_order(order)
    open_items = open_rankable_items(items)
    if not is_split_ro(order):
        changed = False
        for w in items:
            if _car_turn(w):
                _set_car_turn(w, 0)
                changed = True
        if changed:
            order.work_items = work_items_to_dicts(items)
        return
    def _assigned_at(w: Any) -> str:
        if isinstance(w, dict):
            return str(w.get("assigned_at") or "")
        return str(getattr(w, "assigned_at", "") or "")

    ranked = sorted(
        open_items,
        key=lambda w: (
            0 if _car_turn(w) > 0 else 1,
            _car_turn(w) if _car_turn(w) > 0 else 10_000,
            0 if _assignee_key(w) else 1,
            _assigned_at(w) or "9999",
            _item_id(w),
        ),
    )
    for i, w in enumerate(ranked, 1):
        _set_car_turn(w, i)
    order.work_items = work_items_to_dicts(items)


def ensure_car_turns_on_assign(order: RepairOrder, item_id: str = "") -> None:
    """After assign/unassign, keep unique 1..N (first assigned stays 1st)."""
    rebalance_car_turns(order)


def set_car_turn(order: RepairOrder, item_id: str, turn: int) -> None:
    """Set this item's turn; swap with whoever already holds that rank."""
    from carro.core.work_items import ensure_work_items_on_order, work_items_to_dicts

    wid = (item_id or "").strip()
    if not wid:
        raise ValueError("item_id required")
    items = ensure_work_items_on_order(order)
    open_items = open_rankable_items(items)
    n = len(open_items)
    if n < 1:
        raise ValueError("No open work items to rank")
    try:
        want = int(turn)
    except (TypeError, ValueError) as e:
        raise ValueError("turn must be an integer") from e
    if want < 1 or want > n:
        raise ValueError(f"turn must be between 1 and {n}")
    target = next((w for w in open_items if _item_id(w) == wid), None)
    if not target:
        raise ValueError(f"Work item not found or already finished: {wid}")
    if not is_split_ro(order):
        # Ranking only matters on a split; still persist so it is ready when split.
        _set_car_turn(target, want)
        order.work_items = work_items_to_dicts(items)
        rebalance_car_turns(order)
        return
    old = _car_turn(target) or want
    other = next(
        (w for w in open_items if _item_id(w) != wid and _car_turn(w) == want),
        None,
    )
    _set_car_turn(target, want)
    if other is not None:
        _set_car_turn(other, old if old > 0 else want)
    order.work_items = work_items_to_dicts(items)
    rebalance_car_turns(order)


def active_car_turn(order: RepairOrder | dict[str, Any] | Any) -> int:
    """Lowest car_turn among items still occupying the bay; 0 if none/not split."""
    from carro.core.work_items import ensure_work_items_on_order

    if not is_split_ro(order):
        return 0
    if isinstance(order, dict):
        items = [it for it in (order.get("work_items") or []) if isinstance(it, dict)]
    else:
        items = ensure_work_items_on_order(order)
    turns = [_car_turn(w) for w in occupying_items(items) if _car_turn(w) > 0]
    return min(turns) if turns else 0


def car_hold_for_item(
    order: RepairOrder | dict[str, Any] | Any,
    item_id: str,
) -> dict[str, Any]:
    """Board/UI stamp: who has the car first and whether this item must wait."""
    from carro.core.work_items import ensure_work_items_on_order

    wid = (item_id or "").strip()
    split = is_split_ro(order)
    if isinstance(order, dict):
        items = [it for it in (order.get("work_items") or []) if isinstance(it, dict)]
    else:
        items = ensure_work_items_on_order(order)
    item = next((w for w in items if _item_id(w) == wid), None)
    my_turn = _car_turn(item) if item is not None else 0
    if not split:
        return {
            "car_turn": my_turn,
            "car_turn_count": len(open_rankable_items(items)),
            "split_ro": False,
            "waiting_on_car": False,
            "car_held_by_name": "",
            "car_held_item_id": "",
            "car_held_concern": "",
        }
    active = active_car_turn(order)
    holder = next(
        (
            w
            for w in occupying_items(items)
            if _car_turn(w) == active and active > 0
        ),
        None,
    )
    waiting = bool(
        item is not None
        and _item_status(item) in _OCCUPYING
        and my_turn > 0
        and active > 0
        and my_turn > active
    )
    concern = ""
    if holder is not None:
        if isinstance(holder, dict):
            concern = str(holder.get("concern") or "")[:80]
        else:
            concern = str(getattr(holder, "concern", "") or "")[:80]
    return {
        "car_turn": my_turn,
        "car_turn_count": len(open_rankable_items(items)),
        "split_ro": True,
        "waiting_on_car": waiting,
        "car_held_by_name": _assignee_name(holder) if holder is not None else "",
        "car_held_item_id": _item_id(holder) if holder is not None else "",
        "car_held_concern": concern,
    }


def waiting_copy_for_item(order: RepairOrder, item_id: str) -> str:
    info = car_hold_for_item(order, item_id)
    if not info.get("waiting_on_car"):
        return ""
    who = info.get("car_held_by_name") or "another tech"
    held = info.get("car_held_item_id") or "another item"
    return f"wait, {who} has the car first on {held}"


class CarTurnBlocked(ValueError):
    """Start work blocked until the higher-priority item releases the car."""
