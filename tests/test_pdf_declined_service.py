"""Customer PDF: declined found issues render as declined service, not work items."""

from carro.core.pdf import (
    DECLINED_SERVICE_DISCLAIMER,
    _billable_work_items,
    _declined_service_lines,
)
from carro.core.work_items import WorkItem, upsert_work_item
from carro.core.models import RepairOrder


def test_billable_work_items_skip_declined():
    open_item = WorkItem(id="WI-001", concern="Brakes", status="open")
    declined_item = WorkItem(id="WI-002", concern="Rotors", status="declined")
    kept = _billable_work_items([open_item, declined_item])
    assert [w.id for w in kept] == ["WI-001"]


def test_declined_service_lines_from_found_issues():
    lines = _declined_service_lines(
        items=[],
        declined_found_issues=[
            {"description": "Rear brake pads worn", "status": "declined"},
            {"description": "Coolant leak at water pump", "status": "declined"},
        ],
    )
    assert len(lines) == 2
    assert "Rear brake pads worn" in lines[0]
    assert "Coolant leak at water pump" in lines[1]
    assert "Status:" not in "\n".join(lines)


def test_declined_work_items_also_listed_as_declined_service():
    order = RepairOrder(
        id="RO-1",
        first_name="Pat",
        last_name="Lee",
        work_items=[
            {"id": "WI-001", "concern": "Oil change", "status": "done", "item_type": "service"},
        ],
    )
    upsert_work_item(
        order,
        item_id="WI-002",
        concern="Timing belt recommended",
        notes="Due by mileage",
        item_type="repair",
        status="declined",
        actor="Desk",
    )
    from carro.core.work_items import ensure_work_items_on_order

    items = ensure_work_items_on_order(order)
    lines = _declined_service_lines(items=items, declined_found_issues=[])
    assert any("Timing belt recommended" in line for line in lines)
    assert any("Notes: Due by mileage" in line for line in lines)


def test_disclaimer_present():
    assert "not liable" in DECLINED_SERVICE_DISCLAIMER.lower()
    assert "declined" in DECLINED_SERVICE_DISCLAIMER.lower()
