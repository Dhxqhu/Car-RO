"""Work items (itemized concerns + diag notes) on a repair order."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from carro.core.models import now_iso

WORK_ITEM_STATUSES = (
    "open",
    "in_progress",
    "waiting_parts",
    "waiting_customer",
    "done",
    "declined",
)
WORK_ITEM_TYPES = ("diag", "service", "repair", "other")
WORK_ITEM_TYPE_LABELS = {
    "diag": "Diag",
    "service": "Service",
    "repair": "Repair",
    "other": "Other",
}
PART_STATUSES = ("new_request", "ordered", "received", "received_wrong")
PART_STATUS_LABELS = {
    "new_request": "New request",
    "ordered": "Ordered",
    "received": "Received",
    "received_wrong": "Received wrong",
}


def normalize_item_type(raw: object, *, default: str = "other") -> str:
    st = str(raw or "").strip().lower()
    return st if st in WORK_ITEM_TYPES else default


def item_type_label(raw: object) -> str:
    key = normalize_item_type(raw)
    return WORK_ITEM_TYPE_LABELS.get(key, key.title())


def normalize_part_status(raw: object, *, default: str = "new_request") -> str:
    st = str(raw or "").strip().lower()
    return st if st in PART_STATUSES else default


def part_status_label(raw: object) -> str:
    key = normalize_part_status(raw)
    return PART_STATUS_LABELS.get(key, key.replace("_", " ").title())


def new_part_id(existing: list[dict[str, Any]] | None) -> str:
    n = 1
    for entry in existing or []:
        if not isinstance(entry, dict):
            continue
        pid = str(entry.get("id") or "")
        if pid.upper().startswith("PN-"):
            try:
                n = max(n, int(pid.split("-", 1)[1]) + 1)
            except ValueError:
                pass
    return f"PN-{n:03d}"


def normalize_part(data: dict[str, Any] | None, *, default_manufacturer: str = "") -> dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    pid = str(data.get("id") or "").strip() or "PN-001"
    return {
        "id": pid,
        "description": str(data.get("description") or "").strip(),
        "part_number": str(data.get("part_number") or "").strip(),
        "manufacturer": str(data.get("manufacturer") or default_manufacturer or "").strip(),
        "status": normalize_part_status(data.get("status")),
        "requested_at": str(data.get("requested_at") or "").strip(),
        "ordered_at": str(data.get("ordered_at") or "").strip(),
        "received_at": str(data.get("received_at") or "").strip(),
        "wrong_note": str(data.get("wrong_note") or "").strip(),
        "updated_at": str(data.get("updated_at") or "").strip(),
    }


def normalize_parts(
    raw: list[Any] | None, *, default_manufacturer: str = ""
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not raw:
        return out
    for entry in raw:
        if isinstance(entry, dict):
            out.append(normalize_part(entry, default_manufacturer=default_manufacturer))
    return out


STAGE_TOTAL_KEYS = (
    "waiting_parts_minutes",
    "waiting_customer_minutes",
    "in_progress_calendar_minutes",
    "open_minutes",
)
_STAGE_LOG_CAP = 50
_DOWNTIME_LOG_CAP = 50
DOWNTIME_REASONS = (
    "found_issue_compose",
    "between_sessions",
)


def empty_stage_totals() -> dict[str, int]:
    return {k: 0 for k in STAGE_TOTAL_KEYS}


def normalize_stage_totals(raw: object) -> dict[str, int]:
    out = empty_stage_totals()
    if isinstance(raw, dict):
        for k in STAGE_TOTAL_KEYS:
            try:
                out[k] = max(0, int(raw.get(k) or 0))
            except (TypeError, ValueError):
                out[k] = 0
    return out


def normalize_stage_log(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in raw[-_STAGE_LOG_CAP:]:
        if not isinstance(entry, dict):
            continue
        stage = str(entry.get("stage") or "").strip().lower()
        if not stage:
            continue
        try:
            mins = max(0, int(entry.get("minutes") or 0))
        except (TypeError, ValueError):
            mins = 0
        out.append(
            {
                "stage": stage,
                "started_at": str(entry.get("started_at") or "").strip(),
                "ended_at": str(entry.get("ended_at") or "").strip(),
                "minutes": mins,
            }
        )
    return out


def normalize_downtime_log(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in raw[-_DOWNTIME_LOG_CAP:]:
        if not isinstance(entry, dict):
            continue
        reason = str(entry.get("reason") or "").strip().lower()
        if not reason:
            continue
        try:
            mins = max(0, int(entry.get("minutes") or 0))
        except (TypeError, ValueError):
            mins = 0
        out.append(
            {
                "reason": reason,
                "started_at": str(entry.get("started_at") or "").strip(),
                "ended_at": str(entry.get("ended_at") or "").strip(),
                "minutes": mins,
            }
        )
    return out


@dataclass
class WorkItem:
    id: str
    concern: str = ""
    notes: str = ""
    # Shop-only notes — never on customer PDF / advisor customer view.
    private_notes: str = ""
    # Required category for new items: diag | service | repair | other
    item_type: str = "other"
    status: str = "open"
    priority: int = 0
    # Who entered the customer concern (advisor or tech) — set on create / first concern text
    created_by: str = ""
    created_by_id: str = ""
    created_by_role: str = ""  # advisor | tech | ""
    # Who wrote the repair / diagnosis notes — auto-stamped; not manually choosable
    notes_by: str = ""
    notes_by_id: str = ""
    notes_by_role: str = ""
    # Planned queue: who owns this itemized job (not the whole RO/car).
    assigned_to_id: str = ""
    assigned_to_name: str = ""
    assigned_at: str = ""
    # Shop-only efficiency: time actually spent (not billed hours). Never on customer PDF.
    worked_minutes: int = 0
    time_log: list[dict[str, Any]] = field(default_factory=list)
    worked_first_at: str = ""  # first time logged on this item
    worked_last_at: str = ""  # most recent time log
    timer_started_at: str = ""
    timer_tech_id: str = ""
    timer_tech_name: str = ""
    # Wall-clock stage dwell (advisor metrics) — can span days/weeks. Not worked time.
    stage_entered_at: str = ""
    stage_totals: dict[str, int] = field(default_factory=dict)
    stage_log: list[dict[str, Any]] = field(default_factory=list)
    # Non-working gaps (compose, between sessions). Waits also count via stage_totals.
    downtime_minutes: int = 0
    downtime_log: list[dict[str, Any]] = field(default_factory=list)
    downtime_started_at: str = ""
    downtime_reason: str = ""
    # Needed parts (shop order sheet). Never on customer PDF.
    parts: list[dict[str, Any]] = field(default_factory=list)
    updated_by: str = ""
    updated_by_role: str = ""
    created: str = ""
    updated: str = ""
    linked_photo_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> WorkItem:
        if not isinstance(data, dict):
            return cls(id="WI-001")
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in known}
        clean.setdefault("linked_photo_ids", [])
        if not isinstance(clean.get("linked_photo_ids"), list):
            clean["linked_photo_ids"] = []
        clean.setdefault("time_log", [])
        if not isinstance(clean.get("time_log"), list):
            clean["time_log"] = []
        clean.setdefault("parts", [])
        if not isinstance(clean.get("parts"), list):
            clean["parts"] = []
        clean["parts"] = normalize_parts(clean.get("parts"))
        clean["item_type"] = normalize_item_type(clean.get("item_type"), default="other")
        clean["private_notes"] = str(clean.get("private_notes") or "")
        clean["stage_totals"] = normalize_stage_totals(clean.get("stage_totals"))
        clean["stage_log"] = normalize_stage_log(clean.get("stage_log"))
        clean["stage_entered_at"] = str(clean.get("stage_entered_at") or "")
        clean.setdefault("downtime_log", [])
        if not isinstance(clean.get("downtime_log"), list):
            clean["downtime_log"] = []
        clean["downtime_log"] = normalize_downtime_log(clean.get("downtime_log"))
        clean["downtime_started_at"] = str(clean.get("downtime_started_at") or "")
        clean["downtime_reason"] = str(clean.get("downtime_reason") or "")
        try:
            clean["downtime_minutes"] = max(0, int(clean.get("downtime_minutes") or 0))
        except (TypeError, ValueError):
            clean["downtime_minutes"] = 0
        try:
            clean["worked_minutes"] = max(0, int(clean.get("worked_minutes") or 0))
        except (TypeError, ValueError):
            clean["worked_minutes"] = 0
        wid = str(clean.get("id") or "").strip() or "WI-001"
        clean["id"] = wid
        st = str(clean.get("status") or "open").strip().lower()
        clean["status"] = st if st in WORK_ITEM_STATUSES else "open"
        try:
            clean["priority"] = int(clean.get("priority") or 0)
        except (TypeError, ValueError):
            clean["priority"] = 0
        if not clean["stage_entered_at"] and clean.get("created"):
            clean["stage_entered_at"] = str(clean.get("created") or "")
        return cls(**clean)


def new_work_item_id(existing: list[WorkItem] | list[dict[str, Any]]) -> str:
    n = 1
    for item in existing:
        wid = item.id if isinstance(item, WorkItem) else str(item.get("id") or "")
        if wid.upper().startswith("WI-"):
            try:
                n = max(n, int(wid.split("-", 1)[1]) + 1)
            except ValueError:
                pass
    return f"WI-{n:03d}"


def normalize_work_items(raw: list[Any] | None) -> list[WorkItem]:
    out: list[WorkItem] = []
    if not raw:
        return out
    for entry in raw:
        if isinstance(entry, WorkItem):
            out.append(entry)
        elif isinstance(entry, dict):
            out.append(WorkItem.from_dict(entry))
    out.sort(key=lambda w: (w.priority, w.id))
    return out


def work_items_to_dicts(items: list[WorkItem]) -> list[dict[str, Any]]:
    return [w.to_dict() for w in items]


def rollup_complaint(items: list[WorkItem]) -> str:
    bits = []
    for i, w in enumerate(items, 1):
        text = (w.concern or "").strip()
        if not text:
            continue
        bits.append(f"{i}. [{item_type_label(w.item_type)}/{w.status}] {text}")
    return "\n".join(bits)


def rollup_tech_notes(items: list[WorkItem]) -> str:
    bits = []
    for i, w in enumerate(items, 1):
        text = (w.notes or "").strip()
        if not text:
            continue
        head = (w.concern or "").strip()
        label = f"{i}." + (f" ({head[:40]})" if head else "")
        bits.append(f"{label}\n{text}")
    return "\n\n".join(bits)


def ensure_work_items_from_legacy(
    *,
    work_items: list[Any] | None,
    complaint: str = "",
    tech_notes: str = "",
) -> list[WorkItem]:
    """
    If work_items present, normalize them.
    If empty but legacy blobs exist, synthesize a single item.
    """
    items = normalize_work_items(work_items)
    if items:
        return items
    c = (complaint or "").strip()
    n = (tech_notes or "").strip()
    if not c and not n:
        return []
    ts = now_iso()
    return [
        WorkItem(
            id="WI-001",
            concern=c,
            notes=n,
            status="open",
            priority=1,
            created=ts,
            updated=ts,
            created_by_role="tech",
        )
    ]


def apply_rollups(order: Any) -> None:
    """Sync complaint/tech_notes from work_items (mutates order)."""
    items = ensure_work_items_on_order(order)
    order.work_items = work_items_to_dicts(items)
    if items:
        order.complaint = rollup_complaint(items)
        order.tech_notes = rollup_tech_notes(items)


def ensure_work_items_on_order(order: Any) -> list[WorkItem]:
    raw = getattr(order, "work_items", None)
    items = ensure_work_items_from_legacy(
        work_items=raw,
        complaint=getattr(order, "complaint", "") or "",
        tech_notes=getattr(order, "tech_notes", "") or "",
    )
    order.work_items = work_items_to_dicts(items)
    return items


def upsert_work_item(
    order: Any,
    *,
    item_id: str | None = None,
    concern: str | None = None,
    notes: str | None = None,
    private_notes: str | None = None,
    item_type: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    actor: str = "",
    actor_id: str = "",
    actor_role: str = "tech",
    # Only for future advisor app — techs never pass this; engine ignores for tech role.
    assign_to_id: str | None = None,
    assign_to_name: str | None = None,
    allow_manual_assign: bool = False,
    require_item_type: bool = False,
) -> WorkItem:
    """
    Create/update a work item.

    Attribution is automatic from the logged-in actor:
    - New item / first concern text → created_by (who talked to the customer / entered the request)
    - Notes text changed → notes_by + assigned_to (who did the repair notes); techs cannot
      pick another technician.
    """
    items = ensure_work_items_on_order(order)
    ts = now_iso()
    target: WorkItem | None = None
    if item_id:
        for w in items:
            if w.id == item_id:
                target = w
                break
    is_new = target is None
    if is_new and require_item_type and not (item_type or "").strip():
        raise ValueError("Choose a work item type: diag, service, repair, or other")
    if target is None:
        wid = item_id or new_work_item_id(items)
        target = WorkItem(
            id=wid,
            item_type=normalize_item_type(item_type, default="other"),
            priority=priority if priority is not None else (len(items) + 1),
            created=ts,
            stage_entered_at=ts,
            created_by=actor,
            created_by_id=actor_id,
            created_by_role=actor_role,
        )
        items.append(target)

    old_notes = target.notes or ""

    if item_type is not None:
        target.item_type = normalize_item_type(item_type, default=target.item_type or "other")

    if concern is not None:
        target.concern = concern
        # First time concern is filled in — stamp who entered it (keeps original if already set)
        if (concern or "").strip() and not (target.created_by or "").strip():
            target.created_by = actor
            target.created_by_id = actor_id
            target.created_by_role = actor_role
        elif is_new and (concern or "").strip():
            target.created_by = actor or target.created_by
            target.created_by_id = actor_id or target.created_by_id
            target.created_by_role = actor_role or target.created_by_role

    if notes is not None:
        target.notes = notes
        notes_changed = (notes or "") != old_notes
        if notes_changed and (notes or "").strip() and actor:
            # Repair notes always belong to the person who just wrote them
            target.notes_by = actor
            target.notes_by_id = actor_id
            target.notes_by_role = actor_role
            if actor_role == "tech" or not allow_manual_assign:
                target.assigned_to_id = actor_id
                target.assigned_to_name = actor

    if private_notes is not None:
        target.private_notes = private_notes

    if status is not None:
        st = status.strip().lower()
        if st in WORK_ITEM_STATUSES and st != (target.status or "").strip().lower():
            set_item_status(target, st, at=ts)
        elif st in WORK_ITEM_STATUSES:
            target.status = st
    if priority is not None:
        target.priority = int(priority)

    if allow_manual_assign and actor_role == "advisor":
        if assign_to_id is not None:
            target.assigned_to_id = assign_to_id.strip()
        if assign_to_name is not None:
            target.assigned_to_name = assign_to_name.strip()

    target.updated = ts
    target.updated_by = actor
    target.updated_by_role = actor_role
    order.work_items = work_items_to_dicts(items)
    apply_rollups(order)
    return target


def remove_work_item(order: Any, item_id: str) -> bool:
    items = ensure_work_items_on_order(order)
    kept = [w for w in items if w.id != item_id]
    if len(kept) == len(items):
        return False
    order.work_items = work_items_to_dicts(kept)
    apply_rollups(order)
    return True


def _find_item(order: Any, item_id: str) -> tuple[list[WorkItem], WorkItem]:
    items = ensure_work_items_on_order(order)
    for w in items:
        if w.id == item_id:
            return items, w
    raise ValueError(f"Work item not found: {item_id}")


def add_part(
    order: Any,
    item_id: str,
    *,
    description: str,
    part_number: str = "",
    manufacturer: str | None = None,
) -> dict[str, Any]:
    """Add a needed-part line to a work item."""
    items, target = _find_item(order, item_id)
    desc = (description or "").strip()
    if not desc:
        raise ValueError("Part description required")
    ts = now_iso()
    mfr = (manufacturer if manufacturer is not None else (getattr(order, "make", "") or "")).strip()
    parts = list(target.parts or [])
    part = normalize_part(
        {
            "id": new_part_id(parts),
            "description": desc,
            "part_number": (part_number or "").strip(),
            "manufacturer": mfr,
            "status": "new_request",
            "requested_at": ts,
            "updated_at": ts,
        },
        default_manufacturer=mfr,
    )
    parts.append(part)
    target.parts = parts
    target.updated = ts
    order.work_items = work_items_to_dicts(items)
    apply_rollups(order)
    return part


def update_part(
    order: Any,
    item_id: str,
    part_id: str,
    *,
    description: str | None = None,
    part_number: str | None = None,
    manufacturer: str | None = None,
) -> dict[str, Any]:
    items, target = _find_item(order, item_id)
    parts = list(target.parts or [])
    for i, p in enumerate(parts):
        if str(p.get("id")) != part_id:
            continue
        if description is not None:
            p["description"] = description.strip()
        if part_number is not None:
            p["part_number"] = part_number.strip()
        if manufacturer is not None:
            p["manufacturer"] = manufacturer.strip()
        p["updated_at"] = now_iso()
        parts[i] = normalize_part(p)
        target.parts = parts
        target.updated = now_iso()
        order.work_items = work_items_to_dicts(items)
        apply_rollups(order)
        return parts[i]
    raise ValueError(f"Part not found: {part_id}")


def remove_part(order: Any, item_id: str, part_id: str) -> bool:
    items, target = _find_item(order, item_id)
    parts = list(target.parts or [])
    kept = [p for p in parts if str(p.get("id")) != part_id]
    if len(kept) == len(parts):
        return False
    target.parts = kept
    target.updated = now_iso()
    order.work_items = work_items_to_dicts(items)
    apply_rollups(order)
    return True


def set_part_status(
    order: Any,
    item_id: str,
    part_id: str,
    status: str,
    *,
    wrong_note: str = "",
    actor: str = "",
    actor_id: str = "",
) -> dict[str, Any]:
    """
    Transition a part line.
    received_wrong → resets to new_request, stamps wrong_note, re-requests parts on the RO.
    """
    from carro.core.assignment import request_parts

    st = normalize_part_status(status, default="")
    if st not in PART_STATUSES:
        raise ValueError(f"Unknown part status: {status}")
    items, target = _find_item(order, item_id)
    parts = list(target.parts or [])
    ts = now_iso()
    found: dict[str, Any] | None = None
    for i, p in enumerate(parts):
        if str(p.get("id")) != part_id:
            continue
        if st == "received_wrong":
            p["status"] = "new_request"
            note = (wrong_note or "").strip() or "Received wrong part"
            prev = (p.get("wrong_note") or "").strip()
            p["wrong_note"] = f"{prev}\n{ts}: {note}".strip() if prev else f"{ts}: {note}"
            p["received_at"] = ""
            p["ordered_at"] = ""
            if not (p.get("requested_at") or "").strip():
                p["requested_at"] = ts
            request_parts(
                order,
                tech_id=actor_id,
                tech_name=actor or "tech",
                item_id=item_id,
            )
        else:
            p["status"] = st
            if st == "new_request" and not (p.get("requested_at") or "").strip():
                p["requested_at"] = ts
            if st == "ordered":
                p["ordered_at"] = ts
            if st == "received":
                p["received_at"] = ts
        p["updated_at"] = ts
        parts[i] = normalize_part(p)
        found = parts[i]
        break
    if found is None:
        raise ValueError(f"Part not found: {part_id}")
    target.parts = parts
    target.updated = ts
    order.work_items = work_items_to_dicts(items)
    apply_rollups(order)
    return found


def collect_parts_sheet(
    orders: list[Any],
    *,
    status: str = "",
    manufacturer: str = "",
    part_number: str = "",
    ro_id: str = "",
    include_received: bool = False,
) -> list[dict[str, Any]]:
    """Flatten part lines across ROs for the shop parts order sheet."""
    want_status = (status or "").strip().lower()
    want_mfr = (manufacturer or "").strip().lower()
    want_pn = (part_number or "").strip().lower()
    want_ro = (ro_id or "").strip()
    rows: list[dict[str, Any]] = []
    for order in orders:
        oid = getattr(order, "id", "") or ""
        if want_ro and oid != want_ro:
            continue
        make = (getattr(order, "make", "") or "").strip()
        vehicle = ""
        if hasattr(order, "vehicle_label"):
            vehicle = order.vehicle_label()
        customer = ""
        if hasattr(order, "customer_label"):
            customer = order.customer_label()
        for w in ensure_work_items_on_order(order):
            for p in w.parts or []:
                pst = normalize_part_status(p.get("status"))
                if not include_received and pst == "received":
                    continue
                if want_status and pst != want_status:
                    continue
                mfr = (p.get("manufacturer") or make or "").strip()
                if want_mfr and want_mfr not in mfr.lower():
                    continue
                pn = (p.get("part_number") or "").strip()
                if want_pn and want_pn not in pn.lower():
                    continue
                rows.append(
                    {
                        "ro_id": oid,
                        "work_item_id": w.id,
                        "item_type": w.item_type,
                        "concern": (w.concern or "")[:80],
                        "customer": customer,
                        "vehicle": vehicle,
                        "make": make,
                        "part_id": p.get("id"),
                        "description": p.get("description") or "",
                        "part_number": pn,
                        "manufacturer": mfr,
                        "status": pst,
                        "requested_at": p.get("requested_at") or "",
                        "ordered_at": p.get("ordered_at") or "",
                        "received_at": p.get("received_at") or "",
                        "wrong_note": p.get("wrong_note") or "",
                        "updated_at": p.get("updated_at") or "",
                    }
                )
    rows.sort(key=lambda r: (r.get("status") or "", r.get("updated_at") or "", r.get("ro_id") or ""))
    return rows


def prune_received_parts(order: Any, *, keep_hours: float = 24.0) -> int:
    """
    Drop part lines marked received older than keep_hours.
    Call after server upsert so the archive retains them.
    Returns number of parts removed.
    """
    from datetime import datetime, timedelta, timezone

    if keep_hours < 0:
        keep_hours = 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=float(keep_hours))
    removed = 0
    items = ensure_work_items_on_order(order)
    changed = False
    for w in items:
        kept: list[dict[str, Any]] = []
        for p in w.parts or []:
            if normalize_part_status(p.get("status")) != "received":
                kept.append(p)
                continue
            raw = (p.get("received_at") or "").strip()
            when: datetime | None = None
            if raw:
                try:
                    when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                except ValueError:
                    when = None
            if when is None or when <= cutoff:
                removed += 1
                changed = True
                continue
            kept.append(p)
        if len(kept) != len(w.parts or []):
            w.parts = kept
            changed = True
    if changed:
        order.work_items = work_items_to_dicts(items)
        apply_rollups(order)
    return removed


def reorder_work_items(order: Any, ordered_ids: list[str]) -> None:
    items = ensure_work_items_on_order(order)
    by_id = {w.id: w for w in items}
    new_list: list[WorkItem] = []
    for i, wid in enumerate(ordered_ids, 1):
        if wid in by_id:
            w = by_id.pop(wid)
            w.priority = i
            new_list.append(w)
    for w in items:
        if w.id in by_id:
            w.priority = len(new_list) + 1
            new_list.append(w)
            by_id.pop(w.id, None)
    order.work_items = work_items_to_dicts(new_list)
    apply_rollups(order)


def diff_work_item_events(
    before: list[dict[str, Any]] | None,
    after: list[dict[str, Any]] | None,
    *,
    ro_id: str,
    actor: str = "",
) -> list[dict[str, Any]]:
    """Build event dicts describing work-item changes (for server event log)."""
    b_items = {w.id: w for w in normalize_work_items(before)}
    a_items = {w.id: w for w in normalize_work_items(after)}
    events: list[dict[str, Any]] = []
    ts = now_iso()
    for wid, w in a_items.items():
        if wid not in b_items:
            events.append(
                {
                    "type": "item_added",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": ts,
                    "summary": (w.concern or "")[:120] or wid,
                }
            )
            continue
        old = b_items[wid]
        if (old.concern or "") != (w.concern or ""):
            events.append(
                {
                    "type": "item_concern_updated",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": ts,
                    "summary": (w.concern or "")[:120],
                }
            )
        if (old.notes or "") != (w.notes or ""):
            events.append(
                {
                    "type": "item_notes_updated",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": ts,
                    "summary": (w.notes or "")[:120],
                }
            )
        if old.status != w.status:
            events.append(
                {
                    "type": "item_status_changed",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": ts,
                    "summary": f"{old.status} → {w.status}",
                }
            )
        if (old.assigned_to_id, old.assigned_to_name) != (
            w.assigned_to_id,
            w.assigned_to_name,
        ):
            who = (w.assigned_to_name or w.assigned_to_id or "unassigned").strip()
            events.append(
                {
                    "type": "item_assigned",
                    "ro_id": ro_id,
                    "item_id": wid,
                    "actor": actor,
                    "at": ts,
                    "summary": who,
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
                    "at": ts,
                    "summary": wid,
                }
            )
    return events


def format_worked_minutes(minutes: int) -> str:
    """Human label for shop efficiency display (not billed hours)."""
    m = max(0, int(minutes or 0))
    if m < 60:
        return f"{m}m"
    h, rem = divmod(m, 60)
    return f"{h}h {rem}m" if rem else f"{h}h"


def format_duration_minutes(minutes: int | float | None) -> str:
    """
    Wall-clock / stage duration label.
    ≥ 48h → days + hours; else hours/minutes. Not billed/worked hours.
    """
    m = max(0, int(round(float(minutes or 0))))
    if m >= 48 * 60:
        days, rem = divmod(m, 24 * 60)
        hours, mins = divmod(rem, 60)
        if hours and mins:
            return f"{days}d {hours}h {mins}m"
        if hours:
            return f"{days}d {hours}h"
        if mins:
            return f"{days}d {mins}m"
        return f"{days}d"
    return format_worked_minutes(m)


def _stage_total_key(status: str) -> str | None:
    st = (status or "").strip().lower()
    if st == "waiting_parts":
        return "waiting_parts_minutes"
    if st == "waiting_customer":
        return "waiting_customer_minutes"
    if st == "in_progress":
        return "in_progress_calendar_minutes"
    if st == "open":
        return "open_minutes"
    return None


def close_stage_segment(item: WorkItem, *, ended_at: str | None = None) -> int:
    """Bank wall-clock minutes for the stage the item is leaving."""
    ts = (ended_at or now_iso()).strip()
    started = (item.stage_entered_at or "").strip()
    if not started:
        started = (item.created or "").strip()
    if not started:
        item.stage_entered_at = ""
        return 0
    mins = _elapsed_minutes(started, ended_at=ts)
    stage = (item.status or "open").strip().lower() or "open"
    key = _stage_total_key(stage)
    totals = normalize_stage_totals(item.stage_totals)
    if key and mins > 0:
        totals[key] = int(totals.get(key) or 0) + mins
    item.stage_totals = totals
    log = normalize_stage_log(item.stage_log)
    log.append(
        {
            "stage": stage,
            "started_at": started,
            "ended_at": ts,
            "minutes": mins,
        }
    )
    item.stage_log = log[-_STAGE_LOG_CAP:]
    item.stage_entered_at = ""
    return mins


def open_stage_segment(
    item: WorkItem, *, status: str | None = None, at: str | None = None
) -> None:
    st = (status if status is not None else item.status) or "open"
    if st in WORK_ITEM_STATUSES:
        item.status = st
    item.stage_entered_at = (at or now_iso()).strip()


def set_item_status(
    item: WorkItem,
    new_status: str,
    *,
    at: str | None = None,
) -> None:
    """Transition item status, banking prior wall-clock stage dwell."""
    st = (new_status or "").strip().lower()
    if st not in WORK_ITEM_STATUSES:
        raise ValueError(f"Unknown work item status: {new_status}")
    ts = (at or now_iso()).strip()
    old = (item.status or "open").strip().lower() or "open"
    if old == st and (item.stage_entered_at or "").strip():
        return
    if not (item.stage_entered_at or "").strip() and (item.created or "").strip():
        item.stage_entered_at = item.created
    close_stage_segment(item, ended_at=ts)
    open_stage_segment(item, status=st, at=ts)


def live_stage_minutes(item: WorkItem | dict[str, Any], *, now: str | None = None) -> int:
    if isinstance(item, WorkItem):
        started = (item.stage_entered_at or item.created or "").strip()
    else:
        started = str(item.get("stage_entered_at") or item.get("created") or "").strip()
    if not started:
        return 0
    return _elapsed_minutes(started, ended_at=now)


def stage_total_with_live(
    item: WorkItem | dict[str, Any],
    key: str,
    *,
    now: str | None = None,
) -> int:
    if isinstance(item, WorkItem):
        totals = normalize_stage_totals(item.stage_totals)
        status = (item.status or "").strip().lower()
    else:
        totals = normalize_stage_totals(item.get("stage_totals"))
        status = str(item.get("status") or "").strip().lower()
    base = int(totals.get(key) or 0)
    if _stage_total_key(status) == key:
        base += live_stage_minutes(item, now=now)
    return base


def start_downtime(
    item: WorkItem,
    *,
    reason: str,
    at: str | None = None,
) -> None:
    """Begin a non-working interrupt segment (compose / between sessions)."""
    reason_n = (reason or "").strip().lower() or "between_sessions"
    if (item.downtime_started_at or "").strip():
        # Already in downtime — retarget reason if compose takes over a between-session gap.
        if reason_n == "found_issue_compose":
            item.downtime_reason = reason_n
        return
    item.downtime_started_at = (at or now_iso()).strip()
    item.downtime_reason = reason_n


def stop_downtime(item: WorkItem, *, ended_at: str | None = None) -> int:
    """Bank live interrupt downtime into downtime_minutes / downtime_log."""
    started = (item.downtime_started_at or "").strip()
    if not started:
        item.downtime_reason = ""
        return 0
    ts = (ended_at or now_iso()).strip()
    mins = _elapsed_minutes(started, ended_at=ts)
    reason = (item.downtime_reason or "between_sessions").strip().lower()
    item.downtime_started_at = ""
    item.downtime_reason = ""
    if mins > 0:
        item.downtime_minutes = max(0, int(item.downtime_minutes or 0)) + mins
        log = normalize_downtime_log(item.downtime_log)
        log.append(
            {
                "reason": reason,
                "started_at": started,
                "ended_at": ts,
                "minutes": mins,
            }
        )
        item.downtime_log = log[-_DOWNTIME_LOG_CAP:]
    return mins


def live_downtime_minutes(item: WorkItem | dict[str, Any], *, now: str | None = None) -> int:
    if isinstance(item, WorkItem):
        started = (item.downtime_started_at or "").strip()
    else:
        started = str(item.get("downtime_started_at") or "").strip()
    if not started:
        return 0
    return _elapsed_minutes(started, ended_at=now)


def interrupt_downtime_minutes(
    item: WorkItem | dict[str, Any], *, include_live: bool = True
) -> int:
    if isinstance(item, WorkItem):
        base = max(0, int(item.downtime_minutes or 0))
    else:
        try:
            base = max(0, int(item.get("downtime_minutes") or 0))
        except (TypeError, ValueError):
            base = 0
    if include_live:
        base += live_downtime_minutes(item)
    return base


def total_downtime_minutes(
    item: WorkItem | dict[str, Any], *, include_live: bool = True
) -> int:
    """
    Shop downtime from first start until done:
    waiting_parts + waiting_customer stage dwell + interrupt bank (compose / between sessions).
    """
    waits = stage_total_with_live(item, "waiting_parts_minutes") + stage_total_with_live(
        item, "waiting_customer_minutes"
    )
    return waits + interrupt_downtime_minutes(item, include_live=include_live)


def order_total_downtime_minutes(order: Any, *, include_live: bool = True) -> int:
    items = ensure_work_items_on_order(order)
    return sum(total_downtime_minutes(w, include_live=include_live) for w in items)


MAX_OPEN_SEGMENT_MINUTES = 12 * 60  # 12h — crash / forgotten-timer safety valve
TIMER_CHECKPOINT_MINUTES = 15  # GUI heartbeat interval (documented for clients)


def _elapsed_minutes(
    started_at: str,
    *,
    ended_at: str | None = None,
    max_minutes: int | None = None,
) -> int:
    from datetime import datetime

    raw = (started_at or "").strip()
    if not raw:
        return 0
    try:
        start = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if start.tzinfo is not None:
            start = start.replace(tzinfo=None)
        if ended_at:
            end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
            if end.tzinfo is not None:
                end = end.replace(tzinfo=None)
        else:
            end = datetime.now()
    except ValueError:
        return 0
    # Clock skew: treat future starts as "now"
    if start > end:
        start = end
    secs = max(0, (end - start).total_seconds())
    # Round to nearest minute; minimum 1 if any time passed
    mins = int(round(secs / 60.0))
    if secs > 0 and mins == 0:
        mins = 1
    cap = MAX_OPEN_SEGMENT_MINUTES if max_minutes is None else max(0, int(max_minutes))
    if cap > 0 and mins > cap:
        mins = cap
    return mins


def sanitize_open_time_segments(order: Any) -> list[str]:
    """
    Cap and clear stale open work timers / downtime segments (crash recovery).
    Returns human-readable notes for callers that want to surface a message.
    """
    items = ensure_work_items_on_order(order)
    notes: list[str] = []
    changed = False
    for w in items:
        started = (w.timer_started_at or "").strip()
        if started:
            age = _elapsed_minutes(started, max_minutes=10**9)
            if age > MAX_OPEN_SEGMENT_MINUTES:
                tech_id = w.timer_tech_id
                tech_name = w.timer_tech_name
                w.timer_started_at = ""
                w.timer_tech_id = ""
                w.timer_tech_name = ""
                _append_time_entry(
                    w,
                    minutes=MAX_OPEN_SEGMENT_MINUTES,
                    tech_id=tech_id,
                    tech_name=tech_name,
                    note="stale timer capped (crash/recovery)",
                    source="stale_recovery",
                )
                notes.append(
                    f"{w.id}: work timer capped at {MAX_OPEN_SEGMENT_MINUTES}m (was open {age}m)"
                )
                changed = True
                if (getattr(order, "current_item_id", "") or "").strip() == w.id:
                    order.current_tech_id = ""
                    order.current_tech_name = ""
                    order.current_since = ""
                    order.current_item_id = ""
        d_started = (w.downtime_started_at or "").strip()
        if d_started:
            age = _elapsed_minutes(d_started, max_minutes=10**9)
            if age > MAX_OPEN_SEGMENT_MINUTES:
                reason = (w.downtime_reason or "between_sessions").strip().lower()
                w.downtime_started_at = ""
                w.downtime_reason = ""
                w.downtime_minutes = max(0, int(w.downtime_minutes or 0)) + MAX_OPEN_SEGMENT_MINUTES
                log = normalize_downtime_log(w.downtime_log)
                log.append(
                    {
                        "reason": reason,
                        "started_at": d_started,
                        "ended_at": now_iso(),
                        "minutes": MAX_OPEN_SEGMENT_MINUTES,
                    }
                )
                w.downtime_log = log[-_DOWNTIME_LOG_CAP:]
                notes.append(
                    f"{w.id}: downtime capped at {MAX_OPEN_SEGMENT_MINUTES}m (was open {age}m)"
                )
                changed = True
    if changed:
        order.work_items = work_items_to_dicts(items)
        apply_rollups(order)
    return notes


def checkpoint_work_timer(
    order: Any,
    item_id: str,
    *,
    tech_id: str = "",
    tech_name: str = "",
) -> WorkItem:
    """
    Bank the current open timer segment (capped) and immediately restart.
    Used by GUI heartbeat so a crash only risks ~checkpoint interval.
    """
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        raise ValueError(f"Work item not found: {item_id}")
    if not (target.timer_started_at or "").strip():
        return target
    tid = (tech_id or target.timer_tech_id or "").strip()
    tname = (tech_name or target.timer_tech_name or "").strip()
    _stop_timer_on_item(target)
    order.work_items = work_items_to_dicts(items)
    return start_work_timer(order, item_id, tech_id=tid, tech_name=tname)


def total_worked_minutes(order: Any, *, include_live: bool = True) -> int:
    items = ensure_work_items_on_order(order)
    total = sum(max(0, int(w.worked_minutes or 0)) for w in items)
    if include_live:
        for w in items:
            if (w.timer_started_at or "").strip():
                total += _elapsed_minutes(w.timer_started_at)
    return total


def pick_default_work_item_id(order: Any) -> str:
    """Prefer an open/in-progress item; else first item; else empty."""
    items = ensure_work_items_on_order(order)
    if not items:
        return ""
    for w in items:
        if w.status not in ("done", "declined"):
            return w.id
    return items[0].id


def tech_time_breakdown(order: Any) -> list[dict[str, Any]]:
    """Aggregate worked minutes by tech across all work items (shop efficiency)."""
    items = ensure_work_items_on_order(order)
    buckets: dict[str, dict[str, Any]] = {}
    for w in items:
        for entry in w.time_log or []:
            if not isinstance(entry, dict):
                continue
            try:
                mins = max(0, int(entry.get("minutes") or 0))
            except (TypeError, ValueError):
                mins = 0
            if mins <= 0:
                continue
            tid = str(entry.get("tech_id") or "").strip()
            tname = str(entry.get("tech_name") or "").strip() or tid or "Unknown"
            key = tid or tname.lower()
            bucket = buckets.setdefault(
                key,
                {"tech_id": tid, "tech_name": tname, "minutes": 0},
            )
            if tname and not bucket.get("tech_name"):
                bucket["tech_name"] = tname
            bucket["minutes"] += mins
        if (w.timer_started_at or "").strip():
            live = _elapsed_minutes(w.timer_started_at)
            if live > 0:
                tid = (w.timer_tech_id or "").strip()
                tname = (w.timer_tech_name or "").strip() or tid or "Unknown"
                key = tid or tname.lower()
                bucket = buckets.setdefault(
                    key,
                    {"tech_id": tid, "tech_name": tname, "minutes": 0},
                )
                bucket["minutes"] += live
    return sorted(
        buckets.values(),
        key=lambda b: (-int(b.get("minutes") or 0), str(b.get("tech_name") or "").lower()),
    )


def item_tech_breakdown(item: WorkItem | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(item, dict):
        item = WorkItem.from_dict(item)
    buckets: dict[str, dict[str, Any]] = {}
    for entry in item.time_log or []:
        if not isinstance(entry, dict):
            continue
        try:
            mins = max(0, int(entry.get("minutes") or 0))
        except (TypeError, ValueError):
            mins = 0
        if mins <= 0:
            continue
        tid = str(entry.get("tech_id") or "").strip()
        tname = str(entry.get("tech_name") or "").strip() or tid or "Unknown"
        key = tid or tname.lower()
        bucket = buckets.setdefault(
            key,
            {"tech_id": tid, "tech_name": tname, "minutes": 0},
        )
        bucket["minutes"] += mins
    if (item.timer_started_at or "").strip():
        live = _elapsed_minutes(item.timer_started_at)
        if live > 0:
            tid = (item.timer_tech_id or "").strip()
            tname = (item.timer_tech_name or "").strip() or tid or "Unknown"
            key = tid or tname.lower()
            bucket = buckets.setdefault(
                key,
                {"tech_id": tid, "tech_name": tname, "minutes": 0},
            )
            bucket["minutes"] += live
    return sorted(
        buckets.values(),
        key=lambda b: (-int(b.get("minutes") or 0), str(b.get("tech_name") or "").lower()),
    )


def _append_time_entry(
    item: WorkItem,
    *,
    minutes: int,
    tech_id: str = "",
    tech_name: str = "",
    note: str = "",
    source: str = "manual",
) -> None:
    mins = max(0, int(minutes))
    if mins <= 0:
        return
    ts = now_iso()
    item.worked_minutes = max(0, int(item.worked_minutes or 0)) + mins
    if not (item.worked_first_at or "").strip():
        item.worked_first_at = ts
    item.worked_last_at = ts
    entry = {
        "minutes": mins,
        "tech_id": (tech_id or "").strip(),
        "tech_name": (tech_name or "").strip(),
        "at": ts,
        "note": (note or "").strip(),
        "source": source,
    }
    log = list(item.time_log or [])
    log.append(entry)
    item.time_log = log
    item.updated = ts


def add_worked_minutes(
    order: Any,
    item_id: str,
    minutes: int,
    *,
    tech_id: str = "",
    tech_name: str = "",
    note: str = "",
    source: str = "manual",
) -> WorkItem:
    """Manually log shop time on a work item (efficiency reference, not billing)."""
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        raise ValueError(f"Work item not found: {item_id}")
    _append_time_entry(
        target,
        minutes=minutes,
        tech_id=tech_id,
        tech_name=tech_name,
        note=note,
        source=source,
    )
    order.work_items = work_items_to_dicts(items)
    apply_rollups(order)
    return target


def start_work_timer(
    order: Any,
    item_id: str,
    *,
    tech_id: str = "",
    tech_name: str = "",
) -> WorkItem:
    """Start a running timer on this item (stops other timers on the same RO first)."""
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        raise ValueError(f"Work item not found: {item_id}")
    # Flush any other running timers on this RO
    for w in items:
        if w.id != item_id and (w.timer_started_at or "").strip():
            _stop_timer_on_item(w)
            # Other item left mid-work → between-session downtime on that item
            if not (w.downtime_started_at or "").strip():
                st = (w.status or "").strip().lower()
                if st not in ("waiting_parts", "waiting_customer", "done", "declined"):
                    start_downtime(w, reason="between_sessions")
    # Resume from downtime on this item
    stop_downtime(target)
    if (target.timer_started_at or "").strip():
        # Already running — leave as-is (idempotent)
        order.work_items = work_items_to_dicts(items)
        return target
    target.timer_started_at = now_iso()
    target.timer_tech_id = (tech_id or "").strip()
    target.timer_tech_name = (tech_name or "").strip()
    if target.status != "in_progress":
        set_item_status(target, "in_progress")
    target.updated = now_iso()
    order.work_items = work_items_to_dicts(items)
    apply_rollups(order)
    return target


def _stop_timer_on_item(item: WorkItem) -> int:
    started = (item.timer_started_at or "").strip()
    if not started:
        return 0
    mins = _elapsed_minutes(started)
    tech_id = item.timer_tech_id
    tech_name = item.timer_tech_name
    item.timer_started_at = ""
    item.timer_tech_id = ""
    item.timer_tech_name = ""
    if mins > 0:
        _append_time_entry(
            item,
            minutes=mins,
            tech_id=tech_id,
            tech_name=tech_name,
            note="timer",
            source="timer",
        )
    return mins


def stop_work_timer(
    order: Any,
    item_id: str,
    *,
    bank_between_sessions: bool = True,
) -> WorkItem:
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        raise ValueError(f"Work item not found: {item_id}")
    had_timer = bool((target.timer_started_at or "").strip())
    _stop_timer_on_item(target)
    if (
        bank_between_sessions
        and had_timer
        and not (target.downtime_started_at or "").strip()
    ):
        st = (target.status or "").strip().lower()
        if st not in ("waiting_parts", "waiting_customer", "done", "declined"):
            start_downtime(target, reason="between_sessions")
    order.work_items = work_items_to_dicts(items)
    apply_rollups(order)
    return target


def stop_all_work_timers(
    order: Any,
    *,
    bank_between_sessions: bool = True,
) -> int:
    """Flush every running item timer (e.g. when leaving the current bay task)."""
    items = ensure_work_items_on_order(order)
    total = 0
    for w in items:
        had = bool((w.timer_started_at or "").strip())
        total += _stop_timer_on_item(w)
        if (
            bank_between_sessions
            and had
            and not (w.downtime_started_at or "").strip()
        ):
            st = (w.status or "").strip().lower()
            if st not in ("waiting_parts", "waiting_customer", "done", "declined"):
                start_downtime(w, reason="between_sessions")
    order.work_items = work_items_to_dicts(items)
    if total:
        apply_rollups(order)
    return total


def admin_set_worked_minutes(
    order: Any,
    item_id: str,
    minutes: int,
    *,
    note: str = "",
    actor: str = "admin",
) -> WorkItem:
    """
    Admin correction: set absolute worked minutes on an item.
    Stops a running timer first; records an adjustment entry in the time log.
    """
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        raise ValueError(f"Work item not found: {item_id}")
    if (target.timer_started_at or "").strip():
        _stop_timer_on_item(target)
    new_total = max(0, int(minutes))
    old_total = max(0, int(target.worked_minutes or 0))
    delta = new_total - old_total
    target.worked_minutes = new_total
    ts = now_iso()
    if not (target.worked_first_at or "").strip() and new_total > 0:
        target.worked_first_at = ts
    if new_total > 0:
        target.worked_last_at = ts
    elif new_total == 0:
        target.worked_first_at = ""
        target.worked_last_at = ""
    log = list(target.time_log or [])
    log.append(
        {
            "minutes": delta,
            "tech_id": "",
            "tech_name": (actor or "admin").strip() or "admin",
            "at": ts,
            "note": (note or f"admin set total to {new_total}m (was {old_total}m)").strip(),
            "source": "admin",
        }
    )
    target.time_log = log
    target.updated = ts
    order.work_items = work_items_to_dicts(items)
    apply_rollups(order)
    return target


def admin_clear_time_log(
    order: Any,
    item_id: str,
    *,
    note: str = "",
    actor: str = "admin",
) -> WorkItem:
    """Admin: wipe time log and worked minutes on an item (keeps concern/notes)."""
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        raise ValueError(f"Work item not found: {item_id}")
    if (target.timer_started_at or "").strip():
        target.timer_started_at = ""
        target.timer_tech_id = ""
        target.timer_tech_name = ""
    target.worked_minutes = 0
    target.worked_first_at = ""
    target.worked_last_at = ""
    ts = now_iso()
    target.time_log = [
        {
            "minutes": 0,
            "tech_id": "",
            "tech_name": (actor or "admin").strip() or "admin",
            "at": ts,
            "note": (note or "admin cleared time log").strip(),
            "source": "admin",
        }
    ]
    target.updated = ts
    order.work_items = work_items_to_dicts(items)
    apply_rollups(order)
    return target


def format_items_for_display(items: list[WorkItem]) -> str:
    if not items:
        return "(no work items)"
    lines = []
    for i, w in enumerate(items, 1):
        c = (w.concern or "—").replace("\n", " ")
        if len(c) > 50:
            c = c[:47] + "…"
        concern_who = (w.created_by or "").strip()
        notes_who = (w.notes_by or w.assigned_to_name or "").strip()
        time_bit = ""
        if w.worked_minutes:
            time_bit = f" · worked {format_worked_minutes(w.worked_minutes)}"
        if (w.timer_started_at or "").strip():
            time_bit += " · timer on"
        parts_n = len(w.parts or [])
        parts_bit = f" · {parts_n} part(s)" if parts_n else ""
        priv = " · private notes" if (w.private_notes or "").strip() else ""
        bits = [
            f"  {i}. {w.id} [{item_type_label(w.item_type)}/{w.status}]{time_bit}{parts_bit}{priv} {c}"
        ]
        attr = []
        if concern_who:
            role = f"/{w.created_by_role}" if w.created_by_role else ""
            attr.append(f"concern:{concern_who}{role}")
        if notes_who:
            attr.append(f"notes:{notes_who}")
        if attr:
            bits.append("     (" + ", ".join(attr) + ")")
        lines.append("\n".join(bits))
    return "\n".join(lines)


def clone_items(items: list[WorkItem]) -> list[dict[str, Any]]:
    return deepcopy(work_items_to_dicts(items))
