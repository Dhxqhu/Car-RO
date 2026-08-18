"""Intake notes field on repair orders."""

from carro.core.models import RepairOrder
from carro_server.ro_merge import merge_repair_order


def test_intake_notes_roundtrip() -> None:
    order = RepairOrder(id="RO-1", intake_notes="Brake noise, check tires")
    data = order.to_dict()
    assert data["intake_notes"] == "Brake noise, check tires"
    restored = RepairOrder.from_dict(data)
    assert restored.intake_notes == "Brake noise, check tires"


def test_intake_notes_merge_keeps_both() -> None:
    server = {
        "id": "RO-1",
        "updated": "2026-01-01T10:00:00",
        "intake_notes": "Customer waiting on-site",
    }
    incoming = {
        "id": "RO-1",
        "updated": "2026-01-01T09:00:00",
        "intake_notes": "Also mentions oil leak",
    }
    merged = merge_repair_order(
        server=server,
        incoming=incoming,
        base_updated="2026-01-01T09:00:00",
        actor="Advisor",
    )
    assert "Customer waiting on-site" in merged["intake_notes"]
    assert "oil leak" in merged["intake_notes"]
