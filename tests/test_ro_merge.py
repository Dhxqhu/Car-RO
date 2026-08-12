"""RO amend-on-write: concurrent / offline PUTs must not drop notes or rows."""

from __future__ import annotations

from copy import deepcopy

from carro_server.ro_merge import merge_repair_order, merge_text


def _ro(**overrides):
    base = {
        "id": "RO-20260811-001",
        "first_name": "Pat",
        "last_name": "Lee",
        "year": "2017",
        "make": "Ford",
        "model": "F-150",
        "vin": "",
        "mileage": "120000",
        "status": "in_progress",
        "tech_notes": "",
        "complaint": "",
        "waiter": False,
        "urgent": False,
        "updated": "2026-08-11T12:00:00",
        "created": "2026-08-11T09:00:00",
        "work_items": [
            {
                "id": "WI-001",
                "concern": "Brakes",
                "notes": "Pads 4mm",
                "private_notes": "",
                "status": "in_progress",
                "parts": [],
                "time_log": [],
            }
        ],
        "found_issues": [],
        "photos": [{"id": "P1", "filename": "a.jpg", "notes": ""}],
        "advisor_actions": [],
    }
    base.update(overrides)
    return base


def test_matching_base_is_authoritative_including_deletes():
    server = _ro()
    incoming = _ro(
        year="2018",
        work_items=[],
        photos=[],
        updated="2026-08-11T12:05:00",
    )
    out = merge_repair_order(
        server=server,
        incoming=incoming,
        base_updated="2026-08-11T12:00:00",
        actor="Alex",
    )
    assert out["year"] == "2018"
    assert out["work_items"] == []
    assert out["photos"] == []


def test_different_fields_both_survive():
    server = _ro()
    incoming = _ro(
        year="2018",
        work_items=[
            {
                "id": "WI-001",
                "concern": "Brakes",
                "notes": "Pads 4mm",
                "status": "in_progress",
                "parts": [],
                "time_log": [],
            }
        ],
        updated="2026-08-11T12:10:00",
    )
    # Shop already has tech notes from a later write; incoming is stale year edit.
    server["work_items"][0]["notes"] = "Pads 4mm\nResurfaced rotors"
    server["updated"] = "2026-08-11T12:08:00"
    out = merge_repair_order(
        server=server,
        incoming=incoming,
        base_updated="2026-08-11T12:00:00",
        actor="Sam",
    )
    notes = out["work_items"][0]["notes"]
    assert "Resurfaced rotors" in notes
    assert out["year"] == "2018"
    details = " ".join(
        str(a.get("detail") or "") for a in (out.get("advisor_actions") or [])
    )
    assert "2017" in details


def test_same_notes_field_amends_both():
    server = _ro()
    server["work_items"][0]["notes"] = "Replaced caliper"
    server["updated"] = "2026-08-11T12:08:00"
    incoming = _ro()
    incoming["work_items"][0]["notes"] = "Bled brakes"
    incoming["updated"] = "2026-08-11T12:10:00"
    out = merge_repair_order(
        server=server,
        incoming=incoming,
        base_updated="2026-08-11T12:00:00",
        actor="Alex",
    )
    notes = out["work_items"][0]["notes"]
    assert "Replaced caliper" in notes
    assert "Bled brakes" in notes
    assert "Alex" in notes


def test_stale_put_does_not_drop_work_item():
    server = _ro()
    server["work_items"].append(
        {
            "id": "WI-002",
            "concern": "Oil leak",
            "notes": "",
            "status": "open",
            "parts": [],
        }
    )
    server["updated"] = "2026-08-11T12:09:00"
    incoming = _ro(updated="2026-08-11T12:10:00")  # only WI-001
    out = merge_repair_order(
        server=server,
        incoming=incoming,
        base_updated="2026-08-11T12:00:00",
        actor="Alex",
    )
    ids = {w["id"] for w in out["work_items"]}
    assert ids == {"WI-001", "WI-002"}


def test_offline_double_push_notes_and_part():
    """Two PCs loaded the same base, edited offline, pushed in sequence."""
    base = _ro()
    tech = deepcopy(base)
    tech["work_items"][0]["notes"] = "Pads 4mm\nNeed caliper"
    tech["updated"] = "2026-08-11T13:00:00"
    after_tech = merge_repair_order(
        server=base,
        incoming=tech,
        base_updated="2026-08-11T12:00:00",
        actor="Alex",
    )
    # First push matches base → authoritative.
    assert after_tech["work_items"][0]["notes"] == "Pads 4mm\nNeed caliper"

    advisor = deepcopy(base)
    advisor["work_items"][0]["parts"] = [
        {
            "id": "PN-001",
            "description": "Caliper",
            "status": "new_request",
            "part_number": "FO-1",
        }
    ]
    advisor["year"] = "2018"
    advisor["updated"] = "2026-08-11T13:01:00"
    after_both = merge_repair_order(
        server=after_tech,
        incoming=advisor,
        base_updated="2026-08-11T12:00:00",
        actor="Sam",
    )
    assert "Need caliper" in after_both["work_items"][0]["notes"]
    parts = after_both["work_items"][0]["parts"]
    assert any(p.get("description") == "Caliper" for p in parts)


def test_empty_incoming_notes_do_not_wipe_shop():
    server = _ro()
    server["work_items"][0]["notes"] = "Important diag"
    server["updated"] = "2026-08-11T12:15:00"
    incoming = deepcopy(server)
    incoming["work_items"][0]["notes"] = ""
    incoming["updated"] = "2026-08-11T12:20:00"
    out = merge_repair_order(
        server=server,
        incoming=incoming,
        base_updated="2026-08-11T12:00:00",
        actor="Sam",
    )
    assert out["work_items"][0]["notes"] == "Important diag"


def test_status_does_not_go_backward():
    server = _ro(status="done", updated="2026-08-11T12:30:00")
    incoming = _ro(status="open", updated="2026-08-11T12:31:00")
    out = merge_repair_order(
        server=server,
        incoming=incoming,
        base_updated="2026-08-11T12:00:00",
        actor="Alex",
    )
    assert out["status"] == "done"


def test_create_when_no_server_copy():
    incoming = _ro(year="2019")
    out = merge_repair_order(
        server=None, incoming=incoming, base_updated="", actor="Sam"
    )
    assert out["year"] == "2019"
    assert "_actor" not in out


def test_merge_text_appends_and_dedupes():
    assert merge_text("hello", "hello world", actor="A") == "hello world"
    assert merge_text("hello world", "hello", actor="A") == "hello world"
    both = merge_text("aaa", "bbb", actor="Kim")
    assert "aaa" in both and "bbb" in both and "Kim" in both


def test_new_work_item_from_incoming_is_kept():
    server = _ro(updated="2026-08-11T12:08:00")
    incoming = _ro(updated="2026-08-11T12:10:00")
    incoming["work_items"].append(
        {"id": "WI-009", "concern": "Battery", "notes": "Load test", "status": "open"}
    )
    out = merge_repair_order(
        server=server,
        incoming=incoming,
        base_updated="2026-08-11T12:00:00",
        actor="Alex",
    )
    ids = {w["id"] for w in out["work_items"]}
    assert "WI-001" in ids and "WI-009" in ids
