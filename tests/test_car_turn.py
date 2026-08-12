"""Split-RO car turn + complete-with grouped time."""

from __future__ import annotations

from carro.core.assignment import (
    assign_work_item,
    build_assigned_board,
    complete_items_with,
    complete_work_item,
    set_current_task,
    set_work_item_waiting,
)
from carro.core.car_turn import (
    CarTurnBlocked,
    active_car_turn,
    car_hold_for_item,
    is_split_ro,
    set_car_turn,
)
from carro.core.models import RepairOrder
from carro.core.work_items import add_worked_minutes, ensure_work_items_on_order
from carro.core.weekly_reports import build_weekly_tech_report


def _ro() -> RepairOrder:
    order = RepairOrder(
        id="RO-1",
        first_name="Pat",
        last_name="Lee",
        year="2014",
        make="Honda",
        model="Civic",
        work_items=[
            {
                "id": "WI-001",
                "concern": "Brakes",
                "status": "open",
                "item_type": "repair",
            },
            {
                "id": "WI-002",
                "concern": "Oil leak",
                "status": "open",
                "item_type": "repair",
            },
            {
                "id": "WI-003",
                "concern": "Battery",
                "status": "open",
                "item_type": "service",
            },
        ],
    )
    ensure_work_items_on_order(order)
    return order


def test_assign_second_tech_auto_ranks_and_split():
    order = _ro()
    assign_work_item(order, "WI-001", tech_id="t1", tech_name="Jane")
    assert not is_split_ro(order)
    assign_work_item(order, "WI-002", tech_id="t2", tech_name="Sam")
    assert is_split_ro(order)
    items = {w.id: w for w in ensure_work_items_on_order(order)}
    assert items["WI-001"].car_turn == 1
    assert items["WI-002"].car_turn == 2
    hold = car_hold_for_item(order, "WI-002")
    assert hold["waiting_on_car"] is True
    assert hold["car_held_by_name"] == "Jane"
    assert hold["car_held_item_id"] == "WI-001"


def test_rank_swap_stays_unique():
    order = _ro()
    assign_work_item(order, "WI-001", tech_id="t1", tech_name="Jane")
    assign_work_item(order, "WI-002", tech_id="t2", tech_name="Sam")
    assign_work_item(order, "WI-003", tech_id="t3", tech_name="Kim")
    set_car_turn(order, "WI-003", 1)
    items = {w.id: w for w in ensure_work_items_on_order(order)}
    turns = sorted(w.car_turn for w in items.values() if w.car_turn)
    assert turns == [1, 2, 3]
    assert items["WI-003"].car_turn == 1
    assert items["WI-001"].car_turn == 3
    assert items["WI-002"].car_turn == 2


def test_start_blocked_without_override_then_unlocks():
    order = _ro()
    assign_work_item(order, "WI-001", tech_id="t1", tech_name="Jane")
    assign_work_item(order, "WI-002", tech_id="t2", tech_name="Sam")
    try:
        set_current_task(order, tech_id="t2", tech_name="Sam", item_id="WI-002")
        raise AssertionError("expected CarTurnBlocked")
    except CarTurnBlocked as e:
        assert "Jane" in str(e)
        assert "WI-001" in str(e)
    set_current_task(order, tech_id="t1", tech_name="Jane", item_id="WI-001")
    complete_work_item(order, "WI-001", tech_id="t1", tech_name="Jane")
    assert not is_split_ro(order)
    assert active_car_turn(order) == 0
    set_current_task(order, tech_id="t2", tech_name="Sam", item_id="WI-002")
    assert (order.current_item_id or "") == "WI-002"


def test_park_rank1_unlocks_next():
    order = _ro()
    assign_work_item(order, "WI-001", tech_id="t1", tech_name="Jane")
    assign_work_item(order, "WI-002", tech_id="t2", tech_name="Sam")
    set_work_item_waiting(order, "WI-001", kind="waiting_parts", tech_id="t1", tech_name="Jane")
    hold = car_hold_for_item(order, "WI-002")
    assert hold["waiting_on_car"] is False
    set_current_task(order, tech_id="t2", tech_name="Sam", item_id="WI-002")


def test_override_keeps_both_timers():
    order = _ro()
    assign_work_item(order, "WI-001", tech_id="t1", tech_name="Jane")
    assign_work_item(order, "WI-002", tech_id="t2", tech_name="Sam")
    set_current_task(order, tech_id="t1", tech_name="Jane", item_id="WI-001")
    set_current_task(
        order, tech_id="t2", tech_name="Sam", item_id="WI-002", override=True
    )
    items = {w.id: w for w in ensure_work_items_on_order(order)}
    assert (items["WI-001"].timer_started_at or "").strip()
    assert (items["WI-002"].timer_started_at or "").strip()
    board = build_assigned_board([order], tech_id="t1", tech_name="Jane")
    working_ids = {e["item_id"] for e in board["now_working"]}
    assert working_ids == {"WI-001", "WI-002"}
    assert len(board["now_working"]) == 2


def test_complete_with_zero_time_and_group_report():
    order = _ro()
    assign_work_item(order, "WI-001", tech_id="t1", tech_name="Jane")
    assign_work_item(order, "WI-002", tech_id="t2", tech_name="Sam")
    add_worked_minutes(order, "WI-001", 40, tech_id="t1", tech_name="Jane", note="brakes")
    complete_items_with(
        order,
        timed_id="WI-001",
        companion_ids=["WI-002"],
        tech_id="t2",
        tech_name="Sam",
    )
    items = {w.id: w for w in ensure_work_items_on_order(order)}
    assert items["WI-002"].status == "done"
    assert int(items["WI-002"].worked_minutes or 0) == 0
    assert items["WI-002"].completed_with_id == "WI-001"
    assert items["WI-001"].status != "done"
    assert int(items["WI-001"].worked_minutes or 0) == 40
    assert "WI-002" in (items["WI-001"].covers_item_ids or [])
    assert items["WI-001"].time_group_id
    assert items["WI-001"].time_group_id == items["WI-002"].time_group_id

    report = build_weekly_tech_report([order], [], week_start=None, include_live=False)
    techs = report.get("techs") or []
    assert techs
    jane = next(t for t in techs if t.get("tech_id") == "t1")
    assert int(jane.get("job_minutes") or 0) == 40
    job_ids = [j.get("item_id") for j in (jane.get("jobs") or [])]
    assert "WI-001" in job_ids
    assert "WI-002" not in job_ids
    grouped = next(j for j in jane["jobs"] if j.get("item_id") == "WI-001")
    assert "WI-002" in (grouped.get("grouped_item_ids") or [])
    assert int(items["WI-001"].worked_minutes or 0) == 40
    assert int(items["WI-002"].worked_minutes or 0) == 0
