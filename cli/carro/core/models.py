"""Repair order model + IDs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


STATUSES = ("open", "in_progress", "done")


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
    complaint: str = ""
    tech_notes: str = ""
    status: str = "open"
    obd_snapshot: str = ""
    photos: list[dict[str, Any]] = field(default_factory=list)
    created: str = ""
    updated: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepairOrder":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in known}
        clean.setdefault("photos", [])
        return cls(**clean)

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
