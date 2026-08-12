"""SI/IM tags + per-vehicle service plans (due list, call, roll next_due)."""

from __future__ import annotations

from pathlib import Path

import pytest

from carro.core.appointments import convert_appointment_to_ro, upsert_appointment
from carro.core.assignment import complete_work_item
from carro.core.db import LocalStore
from carro.core.service_plans import (
    add_months,
    due_call_list,
    set_line_call,
    upsert_line,
    upsert_plan,
)
from carro.core.work_items import ensure_work_items_on_order, normalize_item_type, upsert_work_item


@pytest.fixture()
def store(tmp_path: Path) -> LocalStore:
    return LocalStore(db_path=tmp_path / "carro.db")


def test_si_tags_normalize():
    assert normalize_item_type("si_im") == "si_im"
    assert normalize_item_type("si_only") == "si_only"


def test_completing_si_im_creates_yearly_line(store: LocalStore):
    order = store.create(
        first_name="Ann",
        last_name="Cole",
        phone="555-0100",
        year="2018",
        make="Toyota",
        model="Camry",
        vin="1HGBH41JXMN109186",
    )
    item = upsert_work_item(
        order,
        concern="Yearly inspection",
        item_type="si_im",
        actor="Desk",
        actor_role="advisor",
    )
    complete_work_item(order, item.id, tech_name="Jane")
    store.save(order)
    plans = store.list_service_plans()
    assert len(plans) == 1
    lines = plans[0]["lines"]
    assert len(lines) == 1
    assert lines[0]["tag"] == "si_im"
    assert lines[0]["interval_months"] == 12
    assert lines[0]["last_ro_id"] == order.id
    assert lines[0]["next_due"] == add_months(lines[0]["last_done_at"], 12)
    store.save(order)
    again = store.list_service_plans()[0]["lines"][0]
    assert again["last_ro_id"] == order.id
    assert again["next_due"] == lines[0]["next_due"]


def test_custom_interval_due_call_and_skip(store: LocalStore):
    plan = upsert_plan(
        store,
        {
            "first_name": "Bob",
            "last_name": "Lee",
            "phone": "555-0101",
            "year": "2012",
            "make": "Honda",
            "model": "Civic",
            "vin": "JH4DA3340NS000001",
            "lines": [
                {
                    "label": "Oil change",
                    "tag": "service",
                    "interval_months": 6,
                    "last_done_at": "2026-02-01",
                    "next_due": "2026-08-01",
                }
            ],
        },
    )
    due = due_call_list(store, today="2026-08-11")
    assert len(due) == 1
    assert due[0]["label"] == "Oil change"
    assert due[0]["overdue"] is True
    line_id = plan["lines"][0]["id"]
    noans = set_line_call(store, plan["id"], line_id, "no_answer", actor="Desk")
    assert noans["lines"][0]["call_status"] == "no_answer"
    assert noans["lines"][0]["call_attempts"] == 1
    skipped = set_line_call(store, plan["id"], line_id, "skip", actor="Desk")
    assert skipped["lines"][0]["next_due"] == "2027-02-01"
    later = due_call_list(store, today="2026-08-11")
    assert later == []


def test_book_stamps_line_and_complete_advances(store: LocalStore):
    plan = upsert_plan(
        store,
        {
            "first_name": "Kim",
            "last_name": "Park",
            "phone": "555-0199",
            "year": "2016",
            "make": "Ford",
            "model": "F-150",
            "vin": "1FTFW1ET0EFA00001",
        },
    )
    plan = upsert_line(
        store,
        plan["id"],
        {
            "label": "Trans service",
            "tag": "service",
            "interval_months": 24,
            "last_done_at": "2024-08-11",
            "next_due": "2026-08-11",
        },
    )
    line = plan["lines"][0]
    due = due_call_list(store, today="2026-08-11")
    assert due[0]["line_id"] == line["id"]
    appt = upsert_appointment(
        store,
        {
            "scheduled_at": "2026-08-20T09:00",
            "first_name": "Kim",
            "last_name": "Park",
            "phone": "555-0199",
            "year": "2016",
            "make": "Ford",
            "model": "F-150",
            "vin": "1FTFW1ET0EFA00001",
            "tag": "service",
            "notes": "Trans service",
            "service_plan_id": plan["id"],
            "service_plan_line_id": line["id"],
        },
        actor="Alex",
    )
    assert appt["service_plan_id"] == plan["id"]
    hidden = due_call_list(store, today="2026-08-11")
    assert hidden == []
    converted, order = convert_appointment_to_ro(store, appt["id"], actor="Alex")
    assert converted["status"] == "converted"
    items = ensure_work_items_on_order(order)
    assert items[0].service_plan_id == plan["id"]
    assert items[0].service_plan_line_id == line["id"]
    complete_work_item(order, items[0].id)
    store.save(order)
    rolled = store.get_service_plan(plan["id"])
    assert rolled is not None
    ln = rolled["lines"][0]
    assert ln["last_ro_id"] == order.id
    assert ln["next_due"] == add_months(ln["last_done_at"], 24)
    still = due_call_list(store, today="2026-08-11")
    assert still == []


def test_enroll_no_skips_auto_plan(store: LocalStore):
    order = store.create(
        first_name="Rae",
        last_name="Kim",
        phone="555-0110",
        year="2019",
        make="Subaru",
        model="Outback",
        vin="4S4BSANC0K3400001",
    )
    item = upsert_work_item(
        order,
        concern="SI only",
        item_type="si_only",
        actor="Desk",
        actor_role="advisor",
        service_plan_enroll="no",
    )
    complete_work_item(order, item.id)
    store.save(order)
    assert store.list_service_plans() == []


def test_enroll_yes_on_appointment(store: LocalStore):
    appt = upsert_appointment(
        store,
        {
            "scheduled_at": "2026-08-15T09:00",
            "first_name": "Lee",
            "last_name": "Ortiz",
            "phone": "555-0120",
            "year": "2015",
            "make": "Chevy",
            "model": "Silverado",
            "vin": "1GCUKREC0FZ100001",
            "tag": "si_im",
            "service_plan_enroll": "yes",
        },
        actor="Desk",
    )
    assert appt["service_plan_id"]
    assert appt["service_plan_line_id"]
    plan = store.get_service_plan(appt["service_plan_id"])
    assert plan is not None
    assert plan["lines"][0]["tag"] == "si_im"


def test_veto_next_hides_then_returns(store: LocalStore):
    plan = upsert_plan(
        store,
        {
            "first_name": "Pat",
            "last_name": "Ng",
            "phone": "555-0130",
            "year": "2011",
            "make": "Toyota",
            "model": "Tacoma",
            "vin": "5TFUU4EN0BX000001",
            "lines": [
                {
                    "label": "SI/IM",
                    "tag": "si_im",
                    "interval_months": 12,
                    "last_done_at": "2025-08-01",
                    "next_due": "2026-08-01",
                }
            ],
        },
    )
    line_id = plan["lines"][0]["id"]
    set_line_call(store, plan["id"], line_id, "veto_next", actor="Desk", today="2026-08-11")
    hidden = due_call_list(store, today="2026-08-11")
    assert hidden == []
    shown = due_call_list(store, today="2026-08-12")
    assert len(shown) == 1
    assert shown[0]["call_status"] == "veto_next"


def test_veto_completely_forgets_till_next(store: LocalStore):
    plan = upsert_plan(
        store,
        {
            "first_name": "Sam",
            "last_name": "Wu",
            "phone": "555-0140",
            "year": "2013",
            "make": "Honda",
            "model": "CR-V",
            "vin": "2HKRM4H70DH000001",
            "lines": [
                {
                    "label": "Oil change",
                    "tag": "service",
                    "interval_months": 6,
                    "last_done_at": "2026-02-11",
                    "next_due": "2026-08-11",
                }
            ],
        },
    )
    line_id = plan["lines"][0]["id"]
    out = set_line_call(store, plan["id"], line_id, "veto", actor="Desk", today="2026-08-11")
    assert out["lines"][0]["next_due"] == "2027-02-11"
    assert out["lines"][0]["call_status"] == "veto"
    assert due_call_list(store, today="2026-08-11") == []
