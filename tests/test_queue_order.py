"""Numbered tech queues: one number per car (RO), items listed under it."""

from __future__ import annotations

from pathlib import Path

import pytest

from carro.core.appointments import convert_appointment_to_ro, upsert_appointment
from carro.core.assignment import assign_work_item, build_assigned_board
from carro.core.db import LocalStore
from carro.core.queue_lanes import move_ro_group_lane, set_tech_queue
from carro.core.work_items import ensure_work_items_on_order, upsert_work_item


@pytest.fixture()
def store(tmp_path: Path) -> LocalStore:
    return LocalStore(db_path=tmp_path / "carro.db")


def _ro(store: LocalStore, *, last: str, concern: str, extra: str | None = None):
    order = store.create(
        first_name="Pat",
        last_name=last,
        year="2018",
        make="Toyota",
        model="Camry",
    )
    upsert_work_item(
        order,
        concern=concern,
        item_type="repair",
        actor="Desk",
        actor_role="advisor",
    )
    if extra:
        upsert_work_item(
            order,
            concern=extra,
            item_type="service",
            actor="Desk",
            actor_role="advisor",
        )
    store.save(order)
    return store.get(order.id) or order


def test_two_items_same_ro_share_number(store: LocalStore):
    order = _ro(store, last="Cole", concern="Brakes", extra="Oil")
    items = ensure_work_items_on_order(order)
    assign_work_item(
        order, items[0].id, tech_id="t1", tech_name="Jane", store=store
    )
    store.save(order)
    order = store.get(order.id)
    assign_work_item(
        order, items[1].id, tech_id="t1", tech_name="Jane", store=store
    )
    store.save(order)
    items = {w.id: w for w in ensure_work_items_on_order(store.get(order.id))}
    assert items[list(items)[0]].queue_order == 1
    assert items[list(items)[1]].queue_order == 1
    board = build_assigned_board(store.list_orders(), tech_id="t1", tech_name="Jane")
    mine = board["mine_daily"]
    assert len(mine) == 2
    assert {j["queue_order"] for j in mine} == {1}
    assert {j["ro_id"] for j in mine} == {order.id}


def test_second_ro_is_number_two(store: LocalStore):
    a = _ro(store, last="Cole", concern="Brakes")
    b = _ro(store, last="Lee", concern="Diag")
    wa = ensure_work_items_on_order(a)[0]
    wb = ensure_work_items_on_order(b)[0]
    assign_work_item(a, wa.id, tech_id="t1", tech_name="Jane", store=store)
    store.save(a)
    assign_work_item(b, wb.id, tech_id="t1", tech_name="Jane", store=store)
    store.save(b)
    a = store.get(a.id)
    b = store.get(b.id)
    assert ensure_work_items_on_order(a)[0].queue_order == 1
    assert ensure_work_items_on_order(b)[0].queue_order == 2
    board = build_assigned_board(store.list_orders(), tech_id="t1", tech_name="Jane")
    orders = [j["ro_id"] for j in board["mine_daily"]]
    assert orders == [a.id, b.id]
    assert [j["queue_order"] for j in board["mine_daily"]] == [1, 2]


def test_reorder_groups(store: LocalStore):
    a = _ro(store, last="Cole", concern="Brakes")
    b = _ro(store, last="Lee", concern="Diag")
    assign_work_item(
        a,
        ensure_work_items_on_order(a)[0].id,
        tech_id="t1",
        tech_name="Jane",
        store=store,
    )
    store.save(a)
    assign_work_item(
        b,
        ensure_work_items_on_order(b)[0].id,
        tech_id="t1",
        tech_name="Jane",
        store=store,
    )
    store.save(b)
    for o in set_tech_queue(
        store,
        tech_id="t1",
        tech_name="Jane",
        lane="daily",
        ro_ids=[b.id, a.id],
    ):
        store.save(o)
    a = store.get(a.id)
    b = store.get(b.id)
    assert ensure_work_items_on_order(b)[0].queue_order == 1
    assert ensure_work_items_on_order(a)[0].queue_order == 2


def test_move_group_to_next_day(store: LocalStore):
    order = _ro(store, last="Cole", concern="Brakes", extra="Oil")
    items = ensure_work_items_on_order(order)
    assign_work_item(order, items[0].id, tech_id="t1", tech_name="Jane", store=store)
    store.save(order)
    order = store.get(order.id)
    assign_work_item(order, items[1].id, tech_id="t1", tech_name="Jane", store=store)
    store.save(order)
    order = store.get(order.id)
    other = _ro(store, last="Lee", concern="Battery")
    assign_work_item(
        other,
        ensure_work_items_on_order(other)[0].id,
        tech_id="t1",
        tech_name="Jane",
        store=store,
    )
    store.save(other)
    order = store.get(order.id)
    for o in move_ro_group_lane(store, order, items[0].id, "next_day"):
        store.save(o)
    order = store.get(order.id)
    other = store.get(other.id)
    moved = ensure_work_items_on_order(order)
    assert {w.queue_lane for w in moved} == {"next_day"}
    assert {w.queue_order for w in moved} == {1}
    left = ensure_work_items_on_order(other)[0]
    assert left.queue_lane == "daily"
    assert left.queue_order == 1
    board = build_assigned_board(store.list_orders(), tech_id="t1", tech_name="Jane")
    assert {j["ro_id"] for j in board["mine_next_day"]} == {order.id}
    assert {j["ro_id"] for j in board["mine_daily"]} == {other.id}


def test_appointment_off_queue_until_converted(store: LocalStore):
    appt = upsert_appointment(
        store,
        {
            "scheduled_at": "2026-08-14T08:00",
            "first_name": "Kim",
            "last_name": "Park",
            "tag": "diag",
            "notes": "Noise",
            "requested_tech_id": "t1",
            "requested_tech_name": "Jane",
        },
    )
    board = build_assigned_board(store.list_orders(), tech_id="t1", tech_name="Jane")
    assert board["mine_daily"] == []
    assert board["unassigned"] == []
    converted, order = convert_appointment_to_ro(store, appt["id"])
    assert converted["converted_ro_id"] == order.id
    board2 = build_assigned_board(store.list_orders(), tech_id="t1", tech_name="Jane")
    assert len(board2["mine_daily"]) == 1
    job = board2["mine_daily"][0]
    assert job["ro_id"] == order.id
    assert job["queue_order"] == 1
    assert job["concern"] == "Noise"
    assert not job["ro_id"].startswith("APPT-")


def test_unassigned_next_day_visible_on_board(store: LocalStore):
    order = _ro(store, last="Ng", concern="Noise")
    wid = ensure_work_items_on_order(order)[0].id
    for o in move_ro_group_lane(store, order, wid, "next_day"):
        store.save(o)
    board = build_assigned_board(store.list_orders())
    assert board["next_day_by_tech"] == []
    assert len(board["next_day_unassigned"]) == 1
    assert board["next_day_unassigned"][0]["item_id"] == wid
    assert board["unassigned"] == []


def test_next_day_keeps_assignee(store: LocalStore):
    order = _ro(store, last="Ng", concern="Noise")
    wid = ensure_work_items_on_order(order)[0].id
    assign_work_item(order, wid, tech_id="t1", tech_name="Jane", store=store)
    store.save(order)
    order = store.get(order.id)
    for o in move_ro_group_lane(store, order, wid, "next_day"):
        store.save(o)
    order = store.get(order.id)
    item = ensure_work_items_on_order(order)[0]
    assert item.queue_lane == "next_day"
    assert item.assigned_to_id == "t1"
    assert item.assigned_to_name == "Jane"
    board = build_assigned_board(store.list_orders(), tech_id="t1", tech_name="Jane")
    assert len(board["mine_next_day"]) == 1
    assert board["next_day_unassigned"] == []
    assert board["next_day_by_tech"][0]["jobs"][0]["item_id"] == wid
