"""Queue lane midnight rollover — next day promote + EOD unassign."""

from __future__ import annotations

from pathlib import Path

import pytest

from carro.core.db import LocalStore
from carro.core.queue_lanes import rollover_queue_lanes, set_queue_lane
from carro.core.work_items import ensure_work_items_on_order, upsert_work_item


@pytest.fixture()
def store(tmp_path: Path) -> LocalStore:
    return LocalStore(db_path=tmp_path / "carro.db")


def test_eod_unassigns_stale_daily_back_to_needs_attention(store: LocalStore):
    order = store.create(first_name="Pat", last_name="Lee")
    item = upsert_work_item(
        order,
        concern="Brakes",
        item_type="repair",
        actor="Desk",
        actor_role="advisor",
        assign_to_id="t1",
        assign_to_name="Alex",
        allow_manual_assign=True,
    )
    items = ensure_work_items_on_order(order)
    target = next(w for w in items if w.id == item.id)
    set_queue_lane(target, "daily", clear_pending=True, set_day=True)
    target.queue_day = "2026-08-10"
    target.status = "open"
    order.work_items = [w.to_dict() for w in items]
    store.save(order)

    n = rollover_queue_lanes(order, today="2026-08-12")
    assert n >= 1
    items2 = ensure_work_items_on_order(order)
    again = next(w for w in items2 if w.id == item.id)
    assert (again.assigned_to_id or "") == ""
    assert (again.assigned_to_name or "") == ""
    assert again.queue_lane == "daily"


def test_eod_keeps_in_progress_assignee(store: LocalStore):
    order = store.create(first_name="Sam", last_name="Ng")
    item = upsert_work_item(
        order,
        concern="Noise",
        item_type="diag",
        actor="Desk",
        actor_role="advisor",
        assign_to_id="t1",
        assign_to_name="Alex",
        allow_manual_assign=True,
    )
    items = ensure_work_items_on_order(order)
    target = next(w for w in items if w.id == item.id)
    set_queue_lane(target, "daily", clear_pending=True, set_day=True)
    target.queue_day = "2026-08-10"
    target.status = "in_progress"
    target.timer_started_at = "2026-08-10T09:00:00"
    order.work_items = [w.to_dict() for w in items]
    store.save(order)

    rollover_queue_lanes(order, today="2026-08-12")
    items2 = ensure_work_items_on_order(order)
    again = next(w for w in items2 if w.id == item.id)
    assert again.assigned_to_id == "t1"
