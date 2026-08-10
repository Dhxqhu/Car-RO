"""Work items (itemized concerns + diag notes) on a repair order."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from carro.core.models import now_iso

WORK_ITEM_STATUSES = ("open", "in_progress", "waiting_parts", "done", "declined")


@dataclass
class WorkItem:
    id: str
    concern: str = ""
    notes: str = ""
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
    # Mirrors notes_by for Assigned board (auto). Advisors may set later via dedicated API.
    assigned_to_id: str = ""
    assigned_to_name: str = ""
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
        wid = str(clean.get("id") or "").strip() or "WI-001"
        clean["id"] = wid
        st = str(clean.get("status") or "open").strip().lower()
        clean["status"] = st if st in WORK_ITEM_STATUSES else "open"
        try:
            clean["priority"] = int(clean.get("priority") or 0)
        except (TypeError, ValueError):
            clean["priority"] = 0
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
        bits.append(f"{i}. [{w.status}] {text}")
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
    status: str | None = None,
    priority: int | None = None,
    actor: str = "",
    actor_id: str = "",
    actor_role: str = "tech",
    # Only for future advisor app — techs never pass this; engine ignores for tech role.
    assign_to_id: str | None = None,
    assign_to_name: str | None = None,
    allow_manual_assign: bool = False,
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
    if target is None:
        wid = item_id or new_work_item_id(items)
        target = WorkItem(
            id=wid,
            priority=priority if priority is not None else (len(items) + 1),
            created=ts,
            created_by=actor,
            created_by_id=actor_id,
            created_by_role=actor_role,
        )
        items.append(target)

    old_notes = target.notes or ""

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

    if status is not None:
        st = status.strip().lower()
        target.status = st if st in WORK_ITEM_STATUSES else target.status
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
        bits = [f"  {i}. {w.id} [{w.status}] {c}"]
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
