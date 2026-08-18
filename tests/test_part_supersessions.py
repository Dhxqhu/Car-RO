"""Shop part supersession catalog: old PN linked to the live number."""

from __future__ import annotations

from pathlib import Path

import pytest

from carro.core import part_supersessions as ssmod


@pytest.fixture()
def catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ssmod, "SUPERSESSIONS_FILE", tmp_path / "part_supersessions.json")
    return ssmod


def test_normalize_pn_strips_space_and_uppercases(catalog):
    assert catalog.normalize_pn("  ab 123-c ") == "AB123-C"


def test_upsert_and_lookup(catalog):
    row = catalog.upsert_link("fl-123", "fl-456", manufacturer="Ford")
    assert row["old_number"] == "FL-123"
    assert row["new_number"] == "FL-456"
    assert row["name"] == "FL-123→FL-456"
    assert catalog.replacement_for("fl-123") == "FL-456"
    assert catalog.replacement_for("FL-456") == ""
    hit = catalog.lookup("fl-123")
    assert hit is not None
    assert hit["current_number"] == "FL-456"


def test_upsert_same_old_number_updates(catalog):
    first = catalog.upsert_link("A1", "B1")
    second = catalog.upsert_link("a1", "C1")
    assert first["id"] == second["id"]
    assert catalog.replacement_for("A1") == "C1"
    assert len(catalog.list_links()) == 1


def test_reject_same_old_and_new(catalog):
    with pytest.raises(ValueError, match="different"):
        catalog.upsert_link("ABC", "abc")
    with pytest.raises(ValueError, match="Old"):
        catalog.upsert_link("", "NEW")


def test_chain_walks_to_current(catalog):
    catalog.upsert_link("A", "B")
    catalog.upsert_link("B", "C")
    assert catalog.current_number("a") == "C"
    assert catalog.current_number("B") == "C"
    assert catalog.current_number("C") == "C"


def test_cycle_does_not_loop_forever(catalog):
    catalog.upsert_link("A", "B")
    catalog.upsert_link("B", "A")
    assert catalog.current_number("A") in {"A", "B"}


def test_annotate_suggestion_marks_old_number(catalog):
    catalog.upsert_link("OLD-1", "NEW-1")
    marked = catalog.annotate_suggestion({"part_number": "old-1", "description": "filter"})
    assert marked["superseded_by"] == "NEW-1"
    live = catalog.annotate_suggestion({"part_number": "NEW-1", "description": "filter"})
    assert live["superseded_by"] == ""


def test_remove_link(catalog):
    row = catalog.upsert_link("OLD", "NEW")
    assert catalog.remove_link(row["id"]) is True
    assert catalog.replacement_for("OLD") == ""
    assert catalog.remove_link(row["id"]) is False


def test_add_part_records_supersession(catalog):
    from carro.core.models import RepairOrder
    from carro.core.work_items import add_part

    order = RepairOrder(
        id="RO-1",
        first_name="Pat",
        last_name="Lee",
        make="Ford",
        work_items=[
            {"id": "WI-001", "concern": "Oil leak", "status": "open", "item_type": "repair"},
        ],
    )
    add_part(
        order,
        "WI-001",
        description="Oil filter",
        part_number="FL-910",
        supersedes="FL-400",
    )
    assert catalog.replacement_for("FL-400") == "FL-910"
    add_part(
        order,
        "WI-001",
        description="Old gasket",
        part_number="GSK-1",
        superseded_by="GSK-9",
    )
    assert catalog.replacement_for("GSK-1") == "GSK-9"
