"""Found-issue requests — tech discoveries awaiting advisor / customer approval."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from carro.core.models import now_iso

FOUND_ISSUE_STATUSES = ("pending", "converted", "declined")
DECLINE_REASONS = ("customer_declined", "pickup_unresolved")


@dataclass
class FoundIssue:
    id: str
    description: str = ""
    notes: str = ""  # shop-only advisor context
    status: str = "pending"
    decline_reason: str = ""
    found_by: str = ""
    found_by_id: str = ""
    found_at: str = ""
    resolved_by: str = ""
    resolved_by_id: str = ""
    resolved_at: str = ""
    work_item_id: str = ""
    source_work_item_id: str = ""
    compose_downtime_minutes: int = 0
    updated: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> FoundIssue:
        if not isinstance(data, dict):
            return cls(id="FI-001")
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in known}
        fid = str(clean.get("id") or "").strip() or "FI-001"
        clean["id"] = fid
        st = str(clean.get("status") or "pending").strip().lower()
        clean["status"] = st if st in FOUND_ISSUE_STATUSES else "pending"
        reason = str(clean.get("decline_reason") or "").strip().lower()
        clean["decline_reason"] = reason if reason in DECLINE_REASONS else ""
        clean["description"] = str(clean.get("description") or "")
        clean["notes"] = str(clean.get("notes") or "")
        try:
            clean["compose_downtime_minutes"] = max(
                0, int(clean.get("compose_downtime_minutes") or 0)
            )
        except (TypeError, ValueError):
            clean["compose_downtime_minutes"] = 0
        return cls(**clean)


def new_found_issue_id(existing: list[FoundIssue] | list[dict[str, Any]]) -> str:
    n = 1
    for item in existing:
        fid = item.id if isinstance(item, FoundIssue) else str(item.get("id") or "")
        if fid.upper().startswith("FI-"):
            try:
                n = max(n, int(fid.split("-", 1)[1]) + 1)
            except ValueError:
                pass
    return f"FI-{n:03d}"


def normalize_found_issues(raw: list[Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not raw:
        return out
    for entry in raw:
        if isinstance(entry, FoundIssue):
            out.append(entry.to_dict())
        elif isinstance(entry, dict):
            out.append(FoundIssue.from_dict(entry).to_dict())
    return out


def ensure_found_issues_on_order(order: Any) -> list[FoundIssue]:
    raw = getattr(order, "found_issues", None)
    items = [FoundIssue.from_dict(x) if not isinstance(x, FoundIssue) else x for x in (raw or [])]
    # Normalize stored form
    order.found_issues = [w.to_dict() for w in items]
    return items


def _save_found_issues(order: Any, items: list[FoundIssue]) -> None:
    order.found_issues = [w.to_dict() for w in items]
    order.updated = now_iso()


def _find_fi(order: Any, fi_id: str) -> tuple[list[FoundIssue], FoundIssue]:
    items = ensure_found_issues_on_order(order)
    wid = (fi_id or "").strip()
    for fi in items:
        if fi.id == wid:
            return items, fi
    raise ValueError(f"Found issue not found: {fi_id}")


def begin_found_issue_compose(
    order: Any,
    *,
    tech_id: str = "",
    tech_name: str = "",
    item_id: str = "",
) -> dict[str, Any]:
    """
    Pause work timer and start found_issue_compose downtime on the source work item.
    Returns { source_work_item_id, paused }.
    """
    from carro.core.work_items import (
        ensure_work_items_on_order,
        start_downtime,
        stop_work_timer,
        work_items_to_dicts,
    )

    wid = (item_id or "").strip() or (getattr(order, "current_item_id", "") or "").strip()
    paused = False
    if wid:
        items = ensure_work_items_on_order(order)
        target = next((w for w in items if w.id == wid), None)
        if target and (target.timer_started_at or "").strip():
            stop_work_timer(order, wid, bank_between_sessions=False)
            paused = True
            items = ensure_work_items_on_order(order)
            target = next((w for w in items if w.id == wid), None)
        if target:
            start_downtime(target, reason="found_issue_compose")
            order.work_items = work_items_to_dicts(items)
    return {
        "source_work_item_id": wid,
        "paused": paused,
        "tech_id": (tech_id or "").strip(),
        "tech_name": (tech_name or "").strip(),
    }


def _finish_compose_and_resume(
    order: Any,
    *,
    source_work_item_id: str,
    tech_id: str = "",
    tech_name: str = "",
    resume: bool = True,
) -> int:
    """Bank compose downtime; optionally restart work timer on source item."""
    from carro.core.work_items import (
        ensure_work_items_on_order,
        start_work_timer,
        stop_downtime,
        work_items_to_dicts,
    )

    wid = (source_work_item_id or "").strip()
    banked = 0
    if not wid:
        return 0
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == wid), None)
    if not target:
        return 0
    banked = stop_downtime(target)
    order.work_items = work_items_to_dicts(items)
    if resume:
        # Keep as current if it still is, or resume timer when tech is still current on this item
        cur = (getattr(order, "current_item_id", "") or "").strip()
        tid = (tech_id or getattr(order, "current_tech_id", "") or "").strip()
        tname = (tech_name or getattr(order, "current_tech_name", "") or "").strip()
        if cur == wid or (tid or tname):
            if not cur:
                order.current_item_id = wid
                order.current_tech_id = tid
                order.current_tech_name = tname
                order.current_since = now_iso()
            start_work_timer(order, wid, tech_id=tid, tech_name=tname)
    return banked


def cancel_found_issue_compose(
    order: Any,
    *,
    tech_id: str = "",
    tech_name: str = "",
    item_id: str = "",
) -> dict[str, Any]:
    wid = (item_id or "").strip() or (getattr(order, "current_item_id", "") or "").strip()
    banked = _finish_compose_and_resume(
        order,
        source_work_item_id=wid,
        tech_id=tech_id,
        tech_name=tech_name,
        resume=True,
    )
    return {"source_work_item_id": wid, "compose_downtime_minutes": banked}


def create_found_issue(
    order: Any,
    *,
    description: str,
    notes: str = "",
    tech_id: str = "",
    tech_name: str = "",
    source_work_item_id: str = "",
    finish_compose: bool = True,
) -> FoundIssue:
    desc = (description or "").strip()
    if not desc:
        raise ValueError("Describe the found issue")
    items = ensure_found_issues_on_order(order)
    src = (
        (source_work_item_id or "").strip()
        or (getattr(order, "current_item_id", "") or "").strip()
    )
    banked = 0
    if finish_compose:
        banked = _finish_compose_and_resume(
            order,
            source_work_item_id=src,
            tech_id=tech_id,
            tech_name=tech_name,
            resume=True,
        )
    fi = FoundIssue(
        id=new_found_issue_id(items),
        description=desc,
        notes=(notes or "").strip(),
        status="pending",
        found_by=(tech_name or "").strip(),
        found_by_id=(tech_id or "").strip(),
        found_at=now_iso(),
        source_work_item_id=src,
        compose_downtime_minutes=banked,
        updated=now_iso(),
    )
    items.append(fi)
    _save_found_issues(order, items)
    return fi


def decline_found_issue(
    order: Any,
    fi_id: str,
    *,
    reason: str = "customer_declined",
    actor: str = "",
    actor_id: str = "",
) -> FoundIssue:
    items, fi = _find_fi(order, fi_id)
    if fi.status == "converted":
        raise ValueError("Found issue already converted to a work item")
    r = (reason or "customer_declined").strip().lower()
    if r not in DECLINE_REASONS:
        r = "customer_declined"
    fi.status = "declined"
    fi.decline_reason = r
    fi.resolved_by = (actor or "").strip()
    fi.resolved_by_id = (actor_id or "").strip()
    fi.resolved_at = now_iso()
    fi.updated = now_iso()
    _save_found_issues(order, items)
    return fi


def approve_found_issue(
    order: Any,
    fi_id: str,
    *,
    item_type: str = "repair",
    actor: str = "",
    actor_id: str = "",
    actor_role: str = "advisor",
) -> tuple[FoundIssue, Any]:
    """Convert pending found issue into a new work item; notify via RO events on sync."""
    from carro.core.work_items import upsert_work_item

    items, fi = _find_fi(order, fi_id)
    if fi.status == "converted" and fi.work_item_id:
        # Idempotent
        return fi, None
    if fi.status == "declined":
        raise ValueError("Cannot approve a declined found issue")
    notes = "Found during inspection."
    if (fi.notes or "").strip():
        notes = f"{notes}\n{(fi.notes or '').strip()}"
    wi = upsert_work_item(
        order,
        concern=fi.description,
        notes=notes,
        item_type=item_type or "repair",
        actor=actor,
        actor_id=actor_id,
        actor_role=actor_role or "advisor",
    )
    fi.status = "converted"
    fi.work_item_id = wi.id
    fi.resolved_by = (actor or "").strip()
    fi.resolved_by_id = (actor_id or "").strip()
    fi.resolved_at = now_iso()
    fi.updated = now_iso()
    fi.decline_reason = ""
    _save_found_issues(order, items)
    return fi, wi


def close_pending_found_issues_on_bill_out(
    order: Any,
    *,
    actor: str = "",
    actor_id: str = "",
) -> list[FoundIssue]:
    """Auto-decline still-pending found issues when the car is billed out / picked up."""
    items = ensure_found_issues_on_order(order)
    closed: list[FoundIssue] = []
    ts = now_iso()
    for fi in items:
        if fi.status != "pending":
            continue
        fi.status = "declined"
        fi.decline_reason = "pickup_unresolved"
        fi.resolved_by = (actor or "").strip() or "system"
        fi.resolved_by_id = (actor_id or "").strip()
        fi.resolved_at = ts
        fi.updated = ts
        closed.append(fi)
    if closed:
        _save_found_issues(order, items)
    return closed


def summarize_found_issue_for_board(order: Any, fi: FoundIssue | dict[str, Any]) -> dict[str, Any]:
    if isinstance(order, dict):
        d = order
    else:
        d = order.to_dict() if hasattr(order, "to_dict") else {}
    if isinstance(fi, FoundIssue):
        f = fi.to_dict()
    else:
        f = dict(fi)
    return {
        "id": f.get("id") or "",
        "ro_id": d.get("id") or "",
        "description": (f.get("description") or "")[:160],
        "status": f.get("status") or "pending",
        "found_by": f.get("found_by") or "",
        "found_by_id": f.get("found_by_id") or "",
        "found_at": f.get("found_at") or "",
        "source_work_item_id": f.get("source_work_item_id") or "",
        "customer": f"{d.get('last_name') or ''}, {d.get('first_name') or ''}".strip(", ").strip()
        or "(no customer)",
        "vehicle": " ".join(
            str(x) for x in (d.get("year"), d.get("make"), d.get("model")) if x
        ).strip()
        or "(no vehicle)",
        "vin": d.get("vin") or "",
    }


def decline_reason_label(reason: str) -> str:
    r = (reason or "").strip().lower()
    if r == "pickup_unresolved":
        return "Not authorized at pickup"
    if r == "customer_declined":
        return "Declined"
    return "Not authorized"
