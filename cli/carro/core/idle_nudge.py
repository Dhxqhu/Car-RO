"""Idle work / parts nudges — forgotten jobs sitting too long on the bay."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from carro.core.models import CLOSED_STATUSES
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


def collect_idle_nudges(
    orders: list[Any],
    *,
    idle_hours: float = 24.0,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    Return idle work items and parts older than idle_hours.

    Skips billed-out ROs. A running timer on a work item means that item is not idle.
    """
    if idle_hours <= 0:
        return []
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=float(idle_hours))
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
                        "idle_since": last.isoformat(),
                        "idle_hours": round(hours, 1),
                        "fingerprint": f"ro:{oid}:{last.isoformat()}",
                    }
                )
            continue

        for w in items:
            w_status = str(w.status or "").strip().lower()
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
                                "summary": (
                                    f"{item_type_label(w.item_type)} · {concern}"
                                )[:140],
                                "customer": customer,
                                "vehicle": vehicle,
                                "assigned_to_name": w.assigned_to_name or "",
                                "idle_since": last.isoformat(),
                                "idle_hours": round(hours, 1),
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
                        "idle_since": last.isoformat(),
                        "idle_hours": round(hours, 1),
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
