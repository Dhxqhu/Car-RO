"""Advisor day plan: quiet dirty tracking, today send, next-day 8am flush."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from carro.core.assignment import build_assigned_board
from carro.core.day_plans import (
    NEXT_DAY_NOTIFY_HOUR,
    apply_staged,
    cars_from_jobs,
    diff_dirty,
    flush_due_next_day_sends,
    format_path_message,
    list_staged,
    load_day_plan,
    save_day_plan,
    send_day_plans,
    stage_item,
    unstage_item,
)
from carro.core.db import LocalStore
from carro.core.work_items import ensure_work_items_on_order, upsert_work_item


def _board() -> dict:
    return {
        "daily_by_tech": [
            {
                "id": "t1",
                "name": "Alex",
                "jobs": [
                    {
                        "ro_id": "RO-1",
                        "queue_order": 1,
                        "year": "2018",
                        "make": "Ford",
                        "model": "F-150",
                    },
                    {
                        "ro_id": "RO-2",
                        "queue_order": 2,
                        "year": "2020",
                        "make": "Toyota",
                        "model": "Camry",
                    },
                ],
            }
        ],
        "next_day_by_tech": [
            {
                "id": "t1",
                "name": "Alex",
                "jobs": [
                    {
                        "ro_id": "RO-3",
                        "queue_order": 1,
                        "year": "2015",
                        "make": "Honda",
                        "model": "Civic",
                    }
                ],
            }
        ],
    }


def test_cars_from_jobs_groups_by_ro(tmp_path: Path):
    cars = cars_from_jobs(
        [
            {"ro_id": "RO-1", "queue_order": 1, "make": "Ford", "model": "F-150"},
            {"ro_id": "RO-1", "queue_order": 1, "make": "Ford", "model": "F-150"},
            {"ro_id": "RO-2", "queue_order": 2, "make": "Toyota", "model": "Camry"},
        ]
    )
    assert [c["ro_id"] for c in cars] == ["RO-1", "RO-2"]


def test_dirty_then_send_today_queues_next_day(tmp_path: Path):
    path = tmp_path / "day_plan.json"
    board = _board()
    state = load_day_plan(path=path)
    dirty = diff_dirty(board, state)
    assert len(dirty) == 1
    assert dirty[0]["tech_id"] == "t1"
    assert dirty[0]["daily_changed"] is True
    assert dirty[0]["next_day_changed"] is True

    sent: list[dict] = []

    def notify(**kwargs):
        sent.append(kwargs)

    result = send_day_plans(
        board,
        notify=notify,
        advisor_id="a1",
        advisor_name="Jordan",
        path=path,
    )
    assert len(sent) == 1
    assert "Today's plan" in sent[0]["body"]
    assert "RO-1" in sent[0]["body"]
    assert len(result["scheduled_next_day"]) == 1
    assert result["scheduled_next_day"][0]["for_date"]

    state2 = load_day_plan(path=path)
    dirty2 = diff_dirty(board, state2)
    assert dirty2 == []

    pending = state2["pending_next_day_send"]["t1"]
    assert "Tomorrow's plan" in pending["body"]
    assert pending["cars"][0]["ro_id"] == "RO-3"


def test_flush_before_8am_noop_after_sends(tmp_path: Path):
    path = tmp_path / "day_plan.json"
    board = _board()
    sent: list[dict] = []

    def notify(**kwargs):
        sent.append(kwargs)

    send_day_plans(board, notify=notify, path=path)
    sent.clear()

    early = datetime.now().astimezone().replace(
        hour=max(0, NEXT_DAY_NOTIFY_HOUR - 1), minute=0, second=0, microsecond=0
    )
    # Force pending for_date to "today" so hour gate is what we test
    state = load_day_plan(path=path)
    entry = state["pending_next_day_send"]["t1"]
    entry["for_date"] = early.date().isoformat()
    save_day_plan(state, path=path)

    flush_due_next_day_sends(notify=notify, now=early, path=path)
    assert sent == []

    late = early.replace(hour=NEXT_DAY_NOTIFY_HOUR, minute=5)
    delivered = flush_due_next_day_sends(notify=notify, now=late, path=path)
    assert len(delivered) == 1
    assert len(sent) == 1
    assert "Tomorrow's plan" in sent[0]["body"]
    assert load_day_plan(path=path)["pending_next_day_send"] == {}


def test_format_path_message():
    text = format_path_message(
        "Today's plan",
        [{"ro_id": "RO-1", "queue_order": 1, "label": "2018 Ford F-150"}],
    )
    assert "1 car" in text
    assert "#1 RO-1" in text


def test_quiet_tech_skips_tech_push():
    from carro_server.notify_targets import recipients_for_event

    people = [
        {"id": "tech-1", "name": "Alex", "role": "technician"},
        {"id": "adv-1", "name": "Jordan", "role": "advisor"},
    ]
    ev = {
        "type": "item_assigned",
        "summary": "Alex",
        "payload": {
            "assigned_to_id": "tech-1",
            "assigned_to_name": "Alex",
            "quiet_tech": "true",
        },
    }
    got = recipients_for_event(ev, actor_id="adv-1", actor_name="Jordan", people=people)
    assert "tech-1" not in got
    assert "adv-1" not in got  # actor


@pytest.fixture()
def store(tmp_path: Path) -> LocalStore:
    return LocalStore(db_path=tmp_path / "carro.db")


def _unassigned_ro(store: LocalStore, *, concern: str = "Brakes"):
    order = store.create(
        first_name="Pat",
        last_name="Cole",
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
    store.save(order)
    return store.get(order.id) or order


def test_stage_does_not_assign_or_move_lane(store: LocalStore, tmp_path: Path):
    path = tmp_path / "day_plan.json"
    order = _unassigned_ro(store)
    item = ensure_work_items_on_order(order)[0]
    assert not (item.assigned_to_id or item.assigned_to_name)

    entry = stage_item(
        ro_id=order.id,
        item_id=item.id,
        tech_id="t1",
        tech_name="Alex",
        lane="daily",
        path=path,
        concern=item.concern,
    )
    assert entry["tech_id"] == "t1"
    assert entry["lane"] == "daily"

    order2 = store.get(order.id)
    item2 = ensure_work_items_on_order(order2)[0]
    assert not (item2.assigned_to_id or item2.assigned_to_name)
    lane = (getattr(item2, "queue_lane", None) or "daily").lower()
    assert lane in ("", "daily")

    rows = list_staged(load_day_plan(path=path))
    assert len(rows) == 1
    assert rows[0]["item_id"] == item.id


def test_unstage_removes_one_entry(tmp_path: Path):
    path = tmp_path / "day_plan.json"
    stage_item(
        ro_id="RO-1",
        item_id="WI-1",
        tech_id="t1",
        tech_name="Alex",
        lane="daily",
        path=path,
    )
    stage_item(
        ro_id="RO-2",
        item_id="WI-2",
        tech_id="t1",
        tech_name="Alex",
        lane="next_day",
        path=path,
    )
    assert len(list_staged(load_day_plan(path=path))) == 2
    assert unstage_item(ro_id="RO-1", item_id="WI-1", path=path) is True
    rows = list_staged(load_day_plan(path=path))
    assert len(rows) == 1
    assert rows[0]["ro_id"] == "RO-2"
    assert unstage_item(ro_id="RO-1", item_id="WI-1", path=path) is False


def test_send_applies_staged_then_notifies(store: LocalStore, tmp_path: Path):
    path = tmp_path / "day_plan.json"
    order = _unassigned_ro(store, concern="Oil leak")
    item = ensure_work_items_on_order(order)[0]
    stage_item(
        ro_id=order.id,
        item_id=item.id,
        tech_id="t1",
        tech_name="Alex",
        lane="daily",
        path=path,
        concern=item.concern,
        vehicle="2018 Toyota Camry",
    )

    sent: list[dict] = []

    def notify(**kwargs):
        sent.append(kwargs)

    def board_builder():
        return build_assigned_board(store.list_orders())

    board = board_builder()
    # Still unassigned on the board before send
    assert any(j["item_id"] == item.id for j in board.get("unassigned") or [])

    result = send_day_plans(
        board,
        notify=notify,
        advisor_id="a1",
        advisor_name="Jordan",
        path=path,
        store=store,
        board_builder=board_builder,
    )
    assert len(result["applied_staged"]) == 1
    assert result["applied_staged"][0]["item_id"] == item.id
    assert list_staged(load_day_plan(path=path)) == []

    order2 = store.get(order.id)
    item2 = ensure_work_items_on_order(order2)[0]
    assert item2.assigned_to_id == "t1"
    assert (getattr(item2, "queue_lane", None) or "daily").lower() == "daily"

    assert len(sent) == 1
    assert "Today's plan" in sent[0]["body"]
    assert order.id in sent[0]["body"]
    assert sent[0]["to_id"] == "t1"


def test_apply_staged_next_day_lane(store: LocalStore, tmp_path: Path):
    path = tmp_path / "day_plan.json"
    order = _unassigned_ro(store)
    item = ensure_work_items_on_order(order)[0]
    stage_item(
        ro_id=order.id,
        item_id=item.id,
        tech_id="t2",
        tech_name="Sam",
        lane="next_day",
        path=path,
    )
    applied = apply_staged(store, path=path)
    assert len(applied) == 1
    item2 = ensure_work_items_on_order(store.get(order.id))[0]
    assert item2.assigned_to_id == "t2"
    assert (getattr(item2, "queue_lane", None) or "").lower() == "next_day"
    assert list_staged(load_day_plan(path=path)) == []
