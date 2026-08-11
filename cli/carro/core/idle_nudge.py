"""Idle work / parts nudges — forgotten jobs sitting too long on the bay."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from carro.core.models import CLOSED_STATUSES
from carro.core.queue_lanes import normalize_queue_lane
from carro.core.work_items import (
    ensure_work_items_on_order,
    item_type_label,
    normalize_part_status,
    part_status_label,
)

# Work items that still need attention (not finished / declined).
IDLE_WORK_ITEM_STATUSES = frozenset(
    {"open", "in_progress", "waiting_parts", "waiting_customer"}
)
# Parts waiting on order / receipt.
IDLE_PART_STATUSES = frozenset({"new_request", "ordered"})

# Long-term parked jobs: weekly check-in only (not the daily idle nudge).
LONG_TERM_IDLE_HOURS = 168.0


def _parse_iso(raw: object) -> datetime | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        when = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when


def _latest(*raws: object) -> datetime | None:
    best: datetime | None = None
    for raw in raws:
        when = _parse_iso(raw)
        if when is None:
            continue
        if best is None or when > best:
            best = when
    return best


def _hours_idle(since: datetime | None, *, now: datetime) -> float | None:
    if since is None:
        return None
    delta = now - since
    if delta.total_seconds() < 0:
        return 0.0
    return delta.total_seconds() / 3600.0


def _threshold_for_lane(lane: str, idle_hours: float) -> float:
    if normalize_queue_lane(lane, default="daily") == "long_term":
        return float(LONG_TERM_IDLE_HOURS)
    return float(idle_hours)


def filter_idle_nudges(
    rows: list[dict[str, Any]],
    *,
    assignee_id: str = "",
    desk: bool = False,
) -> list[dict[str, Any]]:
    """Optionally narrow idle rows for tech assignee or advisor desk scope."""
    aid = str(assignee_id or "").strip().lower()
    out = rows
    if aid:
        out = [
            r
            for r in out
            if str(r.get("assigned_to_id") or "").strip().lower() == aid
        ]
    if desk:
        filtered: list[dict[str, Any]] = []
        for r in out:
            kind = str(r.get("kind") or "")
            status = str(r.get("status") or "").strip().lower()
            assignee = str(r.get("assigned_to_id") or "").strip()
            if kind == "part" or status in IDLE_PART_STATUSES or status == "waiting_parts":
                filtered.append(r)
                continue
            if kind in {"work_item", "ro"} and not assignee:
                filtered.append(r)
                continue
        out = filtered
    return out


def collect_idle_nudges(
    orders: list[Any],
    *,
    idle_hours: float = 24.0,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    Return idle work items and parts older than idle_hours.

    Long-term queue items use a weekly threshold (168h) instead.
    Skips billed-out ROs. A running timer on a work item means that item is not idle.
    """
    if idle_hours <= 0:
        return []
    now = now or datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []

    for order in orders:
        status = str(getattr(order, "status", "") or "").strip().lower()
        if status in CLOSED_STATUSES:
            continue
        oid = str(getattr(order, "id", "") or "")
        if not oid:
            continue
        vehicle = order.vehicle_label() if hasattr(order, "vehicle_label") else ""
        customer = order.customer_label() if hasattr(order, "customer_label") else ""
        items = ensure_work_items_on_order(order)

        if not items:
            # Legacy RO with no work items — nudge on whole order update age.
            last = _latest(
                getattr(order, "updated", None),
                getattr(order, "created", None),
                getattr(order, "assigned_at", None),
                getattr(order, "waiting_since", None),
            )
            threshold = float(idle_hours)
            cutoff = now - timedelta(hours=threshold)
            if last is not None and last <= cutoff:
                hours = _hours_idle(last, now=now) or 0.0
                rows.append(
                    {
                        "kind": "ro",
                        "ro_id": oid,
                        "work_item_id": "",
                        "part_id": "",
                        "status": status or "open",
                        "summary": (getattr(order, "complaint", "") or "RO with no work items")[
                            :120
                        ],
                        "customer": customer,
                        "vehicle": vehicle,
                        "assigned_to_id": str(getattr(order, "assigned_to_id", "") or ""),
                        "assigned_to_name": str(getattr(order, "assigned_to_name", "") or ""),
                        "idle_since": last.isoformat(),
                        "idle_hours": round(hours, 1),
                        "idle_threshold_hours": threshold,
                        "fingerprint": f"ro:{oid}:{last.isoformat()}",
                    }
                )
            continue

        for w in items:
            w_status = str(w.status or "").strip().lower()
            lane = normalize_queue_lane(getattr(w, "queue_lane", None), default="daily")
            threshold = _threshold_for_lane(lane, idle_hours)
            cutoff = now - timedelta(hours=threshold)
            assignee_id = str(getattr(w, "assigned_to_id", "") or "")
            assignee_name = str(getattr(w, "assigned_to_name", "") or "")

            if w_status not in IDLE_WORK_ITEM_STATUSES:
                # Still check parts on done items? Usually parts are ordered while
                # waiting_parts / open — skip finished items' parts if declined/done
                # unless part still outstanding.
                pass
            else:
                if (w.timer_started_at or "").strip():
                    # Actively being worked — not idle.
                    pass
                else:
                    last = _latest(
                        w.updated,
                        w.worked_last_at,
                        w.assigned_at,
                        w.created,
                        w.worked_first_at,
                    )
                    if last is not None and last <= cutoff:
                        hours = _hours_idle(last, now=now) or 0.0
                        concern = (w.concern or "").strip() or w.id
                        rows.append(
                            {
                                "kind": "work_item",
                                "ro_id": oid,
                                "work_item_id": w.id,
                                "part_id": "",
                                "status": w_status,
                                "item_type": w.item_type,
                                "queue_lane": lane,
                                "summary": (
                                    f"{item_type_label(w.item_type)} · {concern}"
                                )[:140],
                                "customer": customer,
                                "vehicle": vehicle,
                                "assigned_to_id": assignee_id,
                                "assigned_to_name": assignee_name,
                                "idle_since": last.isoformat(),
                                "idle_hours": round(hours, 1),
                                "idle_threshold_hours": threshold,
                                "fingerprint": f"wi:{oid}:{w.id}:{last.isoformat()}",
                            }
                        )

            # Parts can still need a push even if the item is waiting_parts / open.
            if w_status in {"done", "declined"}:
                continue
            for p in w.parts or []:
                pst = normalize_part_status(p.get("status"))
                if pst not in IDLE_PART_STATUSES:
                    continue
                last = _latest(
                    p.get("updated_at"),
                    p.get("ordered_at") if pst == "ordered" else None,
                    p.get("requested_at"),
                )
                if last is None or last > cutoff:
                    continue
                hours = _hours_idle(last, now=now) or 0.0
                desc = (p.get("description") or "").strip() or str(p.get("id") or "part")
                rows.append(
                    {
                        "kind": "part",
                        "ro_id": oid,
                        "work_item_id": w.id,
                        "part_id": str(p.get("id") or ""),
                        "status": pst,
                        "queue_lane": lane,
                        "summary": (
                            f"{part_status_label(pst)} · {desc}"
                            + (
                                f" · PN {p.get('part_number')}"
                                if (p.get("part_number") or "").strip()
                                else ""
                            )
                        )[:140],
                        "customer": customer,
                        "vehicle": vehicle,
                        "manufacturer": (p.get("manufacturer") or "").strip(),
                        "assigned_to_id": assignee_id,
                        "assigned_to_name": assignee_name,
                        "idle_since": last.isoformat(),
                        "idle_hours": round(hours, 1),
                        "idle_threshold_hours": threshold,
                        "fingerprint": (
                            f"part:{oid}:{w.id}:{p.get('id')}:{last.isoformat()}"
                        ),
                    }
                )

    rows.sort(
        key=lambda r: (
            -(float(r.get("idle_hours") or 0)),
            str(r.get("ro_id") or ""),
            str(r.get("kind") or ""),
        )
    )
    return rows
