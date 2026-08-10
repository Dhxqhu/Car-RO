"""Repair order model + IDs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


STATUSES = (
    "open",
    "assigned",
    "in_progress",
    "waiting_parts",
    "waiting_customer",
    "done",
    "billed_out",
)

# Shop-floor queues (not yet left / billed)
ACTIVE_STATUSES = frozenset(
    {"open", "assigned", "in_progress", "waiting_parts", "waiting_customer", "done"}
)
WAITING_STATUSES = frozenset({"waiting_parts", "waiting_customer"})
CLOSED_STATUSES = frozenset({"billed_out"})


@dataclass
class PhotoMeta:
    id: str
    filename: str
    tag: str = "other"  # intake | diag | other
    notes: str = ""
    volume: str = "local"
    relpath: str = ""
    created: str = ""


@dataclass
class RepairOrder:
    id: str
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    year: str = ""
    make: str = ""
    model: str = ""
    vin: str = ""
    mileage: str = ""
    plate: str = ""
    # Legacy rollups — kept in sync from work_items for search / old clients
    complaint: str = ""
    tech_notes: str = ""
    technician_name: str = ""
    technician_id: str = ""
    # Who the job is assigned to (advisor desk / Assigned Work board).
    # Distinct from technician_* which stamps who last edited / created the RO.
    assigned_to_id: str = ""
    assigned_to_name: str = ""
    assigned_at: str = ""
    # Who is actively working this car right now (bay / current task).
    current_tech_id: str = ""
    current_tech_name: str = ""
    current_since: str = ""
    # Internal efficiency stamps — never print on customer PDF.
    started_at: str = ""  # first in_progress
    done_at: str = ""  # work finished (still in shop)
    billed_out_at: str = ""  # left / billed
    waiting_since: str = ""  # entered waiting_parts or waiting_customer
    status: str = "open"
    obd_snapshot: str = ""
    photos: list[dict[str, Any]] = field(default_factory=list)
    work_items: list[dict[str, Any]] = field(default_factory=list)
    created: str = ""
    updated: str = ""

    def to_dict(self) -> dict[str, Any]:
        from carro.core.work_items import apply_rollups

        apply_rollups(self)
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepairOrder":
        from carro.core.work_items import apply_rollups, ensure_work_items_from_legacy

        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in known}
        clean.setdefault("photos", [])
        clean.setdefault("work_items", [])
        if not isinstance(clean.get("work_items"), list):
            clean["work_items"] = []
        order = cls(**clean)
        items = ensure_work_items_from_legacy(
            work_items=order.work_items,
            complaint=order.complaint,
            tech_notes=order.tech_notes,
        )
        order.work_items = [w.to_dict() for w in items]
        if items:
            apply_rollups(order)
        return order

    def customer_label(self) -> str:
        name = f"{self.last_name}, {self.first_name}".strip(", ").strip()
        return name or "(no customer)"

    def vehicle_label(self) -> str:
        bits = [self.year, self.make, self.model]
        return " ".join(b for b in bits if b).strip() or "(no vehicle)"


def new_ro_id(existing: list[str], when: datetime | None = None) -> str:
    when = when or datetime.now()
    day = when.strftime("%Y%m%d")
    prefix = f"RO-{day}-"
    seq = 1
    for eid in existing:
        if eid.startswith(prefix):
            try:
                seq = max(seq, int(eid.rsplit("-", 1)[-1]) + 1)
            except ValueError:
                pass
    return f"{prefix}{seq:03d}"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
