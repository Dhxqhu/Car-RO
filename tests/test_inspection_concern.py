"""Default customer concern text for PA inspection work item types."""

from carro.core.models import RepairOrder
from carro.core.work_items import (
    default_concern_for_item_type,
    upsert_work_item,
)


def _ro() -> RepairOrder:
    return RepairOrder(
        id="RO-1",
        first_name="Pat",
        last_name="Lee",
        make="Honda",
        work_items=[],
    )


def test_default_concern_for_si_im():
    assert default_concern_for_item_type("si_im") == "State Inspection and Emissions Testing"


def test_default_concern_for_si_only():
    assert default_concern_for_item_type("si_only") == "State Inspection Only"


def test_default_concern_for_other_types():
    assert default_concern_for_item_type("repair") == ""


def test_new_si_im_item_autofills_concern():
    order = _ro()
    item = upsert_work_item(order, item_type="si_im", require_item_type=True, actor="Desk")
    assert item.concern == "State Inspection and Emissions Testing"


def test_new_si_only_item_autofills_concern():
    order = _ro()
    item = upsert_work_item(order, item_type="si_only", require_item_type=True, actor="Desk")
    assert item.concern == "State Inspection Only"


def test_custom_concern_not_overwritten_on_type_change():
    order = _ro()
    item = upsert_work_item(
        order,
        item_type="repair",
        concern="Brake noise",
        require_item_type=True,
        actor="Desk",
    )
    upsert_work_item(order, item_id=item.id, item_type="si_im", actor="Desk")
    assert item.concern == "Brake noise"


def test_switching_si_types_updates_default_concern():
    order = _ro()
    item = upsert_work_item(order, item_type="si_im", require_item_type=True, actor="Desk")
    updated = upsert_work_item(order, item_id=item.id, item_type="si_only", actor="Desk")
    assert updated.concern == "State Inspection Only"
