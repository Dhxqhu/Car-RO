"""Advisor appointments + calendar parts overlay."""

from __future__ import annotations

from pathlib import Path

import pytest

from carro.core.appointments import (
    archive_appointment,
    calendar_payload,
    confirm_call_list,
    convert_appointment_to_ro,
    restore_appointment,
    set_confirm_call,
    upsert_appointment,
)
from carro.core.db import LocalStore
from carro.core.work_items import ensure_work_items_on_order, work_items_to_dicts


@pytest.fixture()
def store(tmp_path: Path) -> LocalStore:
    return LocalStore(db_path=tmp_path / "carro.db")


def test_create_and_list_by_week(store: LocalStore):
    in_week = upsert_appointment(
        store,
        {
            "scheduled_at": "2026-08-12T09:00",
            "first_name": "Ann",
            "last_name": "Cole",
            "phone": "555-0100",
            "year": "2018",
            "make": "Toyota",
            "model": "Camry",
            "tag": "diag",
            "notes": "Check engine light",
        },
        actor="Desk",
        actor_id="adv-1",
    )
    upsert_appointment(
        store,
        {
            "scheduled_at": "2026-08-20T10:00",
            "first_name": "Bob",
            "last_name": "Lee",
            "tag": "service",
        },
        actor="Desk",
    )
    rows = store.list_appointments_in_range("2026-08-10", "2026-08-15", statuses=["scheduled"])
    assert [r["id"] for r in rows] == [in_week["id"]]
    assert in_week["id"].startswith("APPT-")
    assert in_week["status"] == "scheduled"
    assert in_week["tag"] == "diag"


def test_archive_drops_from_grid_and_restore(store: LocalStore):
    appt = upsert_appointment(
        store,
        {
            "scheduled_at": "2026-08-13T14:30",
            "first_name": "Pat",
            "last_name": "Ng",
            "tag": "repair",
        },
    )
    archived = archive_appointment(store, appt["id"], status="canceled")
    assert archived["status"] == "canceled"
    assert archived["canceled_at"]
    grid = store.list_appointments_in_range(
        "2026-08-10", "2026-08-16", statuses=["scheduled"]
    )
    assert grid == []
    payload = calendar_payload(store, start="2026-08-10", end="2026-08-16")
    assert payload["appointments"] == []
    assert payload["canceled"][0]["id"] == appt["id"]

    restored = restore_appointment(store, appt["id"])
    assert restored["status"] == "scheduled"
    assert not restored["canceled_at"]
    grid2 = store.list_appointments_in_range(
        "2026-08-10", "2026-08-16", statuses=["scheduled"]
    )
    assert len(grid2) == 1

    noshow = archive_appointment(store, appt["id"], status="no_show")
    assert noshow["status"] == "no_show"
    payload2 = calendar_payload(store, start="2026-08-10", end="2026-08-16")
    assert payload2["appointments"] == []
    assert payload2["no_show"][0]["id"] == appt["id"]


def test_convert_creates_ro_with_tag_notes_and_tech(store: LocalStore):
    appt = upsert_appointment(
        store,
        {
            "scheduled_at": "2026-08-14T08:00",
            "first_name": "Kim",
            "last_name": "Park",
            "phone": "555-0199",
            "year": "2012",
            "make": "Honda",
            "model": "Civic",
            "tag": "service",
            "notes": "Oil leak + noise",
            "requested_tech_id": "t-jane",
            "requested_tech_name": "Jane",
        },
        actor="Alex",
        actor_id="adv-2",
    )
    converted, order = convert_appointment_to_ro(
        store, appt["id"], actor="Alex", actor_id="adv-2"
    )
    assert converted["status"] == "converted"
    assert converted["converted_ro_id"] == order.id
    assert order.first_name == "Kim"
    assert order.last_name == "Park"
    assert order.year == "2012"
    items = ensure_work_items_on_order(order)
    assert len(items) == 1
    assert items[0].item_type == "service"
    assert items[0].concern == "Oil leak + noise"
    assert items[0].assigned_to_id == "t-jane"
    assert items[0].assigned_to_name == "Jane"
    saved = store.get(order.id)
    assert saved is not None
    again, same = convert_appointment_to_ro(store, appt["id"])
    assert same.id == order.id
    assert again["converted_ro_id"] == order.id


def test_calendar_includes_parts_ordered_and_received(store: LocalStore):
    order = store.create(
        first_name="Sam",
        last_name="Ortiz",
        year="2016",
        make="Ford",
        model="F-150",
    )
    from carro.core.work_items import upsert_work_item

    item = upsert_work_item(
        order,
        concern="Brakes",
        item_type="repair",
        actor="Desk",
        actor_role="advisor",
    )
    items = ensure_work_items_on_order(order)
    target = next(w for w in items if w.id == item.id)
    target.parts = [
        {
            "id": "PN-001",
            "description": "Front pads",
            "part_number": "P-1",
            "status": "received",
            "ordered_at": "2026-08-11T11:00:00",
            "received_at": "2026-08-12T15:30:00",
        }
    ]
    order.work_items = work_items_to_dicts(items)
    store.save(order)
    payload = calendar_payload(store, start="2026-08-11", end="2026-08-12")
    kinds = {(p["kind"], p["description"], p["ro_id"]) for p in payload["parts"]}
    assert ("ordered", "Front pads", order.id) in kinds
    assert ("received", "Front pads", order.id) in kinds
    outside = calendar_payload(store, start="2026-08-01", end="2026-08-05")
    assert outside["parts"] == []


def test_confirm_call_confirmed_canceled_no_answer(store: LocalStore):
    tomorrow = upsert_appointment(
        store,
        {
            "scheduled_at": "2026-08-12T09:00",
            "first_name": "Ann",
            "last_name": "Cole",
            "phone": "555-0100",
            "tag": "diag",
        },
    )
    later = upsert_appointment(
        store,
        {
            "scheduled_at": "2026-08-13T10:00",
            "first_name": "Bob",
            "last_name": "Lee",
            "phone": "555-0101",
            "tag": "service",
        },
    )
    calls = confirm_call_list(store, today="2026-08-11")
    assert calls["tomorrow"] == "2026-08-12"
    assert [a["id"] for a in calls["tomorrow_calls"]] == [tomorrow["id"]]
    assert calls["today_open"] == []

    noans = set_confirm_call(store, tomorrow["id"], "no_answer", actor="Desk")
    assert noans["status"] == "scheduled"
    assert noans["confirm_status"] == "no_answer"
    assert noans["confirm_attempts"] == 1
    assert noans["confirm_by"] == "Desk"
    again = set_confirm_call(store, tomorrow["id"], "no_answer", actor="Desk")
    assert again["confirm_attempts"] == 2
    yes = set_confirm_call(store, tomorrow["id"], "confirmed", actor="Desk")
    assert yes["confirm_status"] == "confirmed"
    assert yes["status"] == "scheduled"

    canceled = set_confirm_call(store, later["id"], "canceled", actor="Desk")
    assert canceled["status"] == "canceled"
    assert canceled["confirm_status"] == "canceled"
    grid = store.list_appointments_in_range(
        "2026-08-13", "2026-08-13", statuses=["scheduled"]
    )
    assert grid == []
    restored = restore_appointment(store, later["id"])
    assert restored["status"] == "scheduled"
    assert restored["confirm_status"] == ""


def test_confirm_veto_next_and_veto(store: LocalStore):
    appt = upsert_appointment(
        store,
        {
            "scheduled_at": "2026-08-12T09:00",
            "first_name": "Ann",
            "last_name": "Cole",
            "phone": "555-0100",
            "tag": "diag",
        },
    )
    vetoed = set_confirm_call(store, appt["id"], "veto_next", actor="Desk", today="2026-08-11")
    assert vetoed["confirm_status"] == "veto_next"
    assert vetoed["confirm_veto_until"] == "2026-08-12"
    hidden = confirm_call_list(store, today="2026-08-11")
    assert hidden["tomorrow_calls"] == []
    later = confirm_call_list(store, today="2026-08-12")
    assert [a["id"] for a in later["today_open"]] == [appt["id"]]
    done = set_confirm_call(store, appt["id"], "veto", actor="Desk", today="2026-08-12")
    assert done["confirm_status"] == "veto"
    gone = confirm_call_list(store, today="2026-08-12")
    assert gone["today_open"] == []


def test_waiter_urgent_roundtrip_and_convert(store: LocalStore):
    appt = upsert_appointment(
        store,
        {
            "scheduled_at": "2026-08-14T10:30",
            "all_day": False,
            "first_name": "Lee",
            "last_name": "Wait",
            "tag": "diag",
            "waiter": True,
            "urgent": True,
        },
    )
    assert appt["waiter"] is True
    assert appt["urgent"] is True
    cleared = upsert_appointment(
        store,
        {
            "id": appt["id"],
            "scheduled_at": "2026-08-14T10:30",
            "waiter": False,
            "urgent": False,
        },
    )
    assert cleared["waiter"] is False
    assert cleared["urgent"] is False
    flagged = upsert_appointment(
        store,
        {
            "id": appt["id"],
            "scheduled_at": "2026-08-14T10:30",
            "waiter": True,
            "urgent": False,
        },
    )
    assert flagged["waiter"] is True
    assert flagged["urgent"] is False
    _converted, order = convert_appointment_to_ro(store, appt["id"], actor="Desk")
    assert order.waiter is True
    assert order.urgent is False


def test_all_day_date_only_scheduled_at(store: LocalStore):
    appt = upsert_appointment(
        store,
        {
            "scheduled_at": "2026-08-15",
            "all_day": True,
            "first_name": "Day",
            "last_name": "Only",
            "tag": "other",
        },
    )
    assert appt["all_day"] is True
    assert appt["scheduled_at"] == "2026-08-15"


def test_delete_appointment_via_archive(store: LocalStore):
    appt = upsert_appointment(
        store,
        {
            "scheduled_at": "2026-08-16T11:00",
            "first_name": "Del",
            "last_name": "Me",
            "tag": "service",
        },
    )
    deleted = archive_appointment(store, appt["id"], status="canceled")
    assert deleted["status"] == "canceled"
    grid = store.list_appointments_in_range(
        "2026-08-16", "2026-08-16", statuses=["scheduled"]
    )
    assert grid == []
