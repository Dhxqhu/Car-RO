from carro.core.history import latest_orders_per_car
from carro.core.models import RepairOrder


def _ro(**kwargs) -> RepairOrder:
    return RepairOrder(**kwargs)


def test_latest_orders_per_car_keeps_newest_vin():
    older = _ro(
        id="RO-1",
        vin="1FTFW1ET0EFA00001",
        last_name="Lee",
        phone="555-1111",
        updated="2024-01-01T10:00:00",
    )
    newer = _ro(
        id="RO-100",
        vin="1FTFW1ET0EFA00001",
        last_name="Lee",
        phone="555-9999",
        updated="2026-08-01T10:00:00",
    )
    other = _ro(
        id="RO-2",
        vin="2G1WF52E359000002",
        last_name="Lee",
        updated="2026-07-01T10:00:00",
    )
    out = latest_orders_per_car([older, newer, other])
    ids = [o.id for o in out]
    assert ids == ["RO-100", "RO-2"]
    assert out[0].phone == "555-9999"


def test_latest_orders_per_car_uses_plate_when_no_vin():
    a = _ro(id="RO-a", plate="ABC-123", updated="2026-01-01T00:00:00")
    b = _ro(id="RO-b", plate="abc123", updated="2026-06-01T00:00:00")
    c = _ro(id="RO-c", plate="XYZ-9", updated="2026-03-01T00:00:00")
    out = latest_orders_per_car([a, b, c])
    assert [o.id for o in out] == ["RO-b", "RO-c"]


def test_latest_orders_per_car_does_not_collapse_blank_cars():
    a = _ro(id="RO-a", last_name="Lee", updated="2026-01-01T00:00:00")
    b = _ro(id="RO-b", last_name="Lee", updated="2026-06-01T00:00:00")
    out = latest_orders_per_car([a, b])
    assert {o.id for o in out} == {"RO-a", "RO-b"}
