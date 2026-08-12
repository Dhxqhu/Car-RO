from carro_server.notify_targets import recipients_for_event, roster_people


PEOPLE = [
    {"id": "tech-1", "name": "Alex", "role": "technician"},
    {"id": "tech-2", "name": "Sam", "role": "technician"},
    {"id": "adv-1", "name": "Jordan", "role": "advisor"},
]


def test_roster_people_strips_hashes():
    rows = roster_people(
        {"technicians": [{"id": "t1", "name": "A", "pin_hash": "x"}]},
        {"advisors": [{"id": "a1", "name": "B", "pin_hash": "y"}]},
    )
    assert rows == [
        {"id": "t1", "name": "A", "role": "technician"},
        {"id": "a1", "name": "B", "role": "advisor"},
    ]


def test_assignment_notifies_tech_and_advisors_not_actor():
    ev = {
        "type": "item_assigned",
        "ro_id": "RO-1",
        "summary": "Alex",
        "payload": {"assigned_to_id": "tech-1", "assigned_to_name": "Alex", "actor_id": "adv-1"},
    }
    got = recipients_for_event(ev, actor_id="adv-1", actor_name="Jordan", people=PEOPLE)
    assert got == ["tech-1"]


def test_assignment_by_advisor_also_skips_that_advisor():
    ev = {
        "type": "item_assigned",
        "ro_id": "RO-1",
        "summary": "Alex",
        "payload": {"assigned_to_id": "tech-1", "assigned_to_name": "Alex"},
    }
    got = recipients_for_event(ev, actor_id="adv-1", actor_name="Jordan", people=PEOPLE)
    assert "adv-1" not in got
    assert "tech-1" in got


def test_wait_cleared_only_assigned_tech():
    ev = {
        "type": "item_wait_cleared",
        "ro_id": "RO-1",
        "summary": "Parts in",
        "payload": {"assigned_to_id": "tech-2", "assigned_to_name": "Sam"},
    }
    got = recipients_for_event(ev, actor_id="adv-1", actor_name="Jordan", people=PEOPLE)
    assert got == ["tech-2"]


def test_found_issue_notifies_advisors_not_reporter():
    ev = {
        "type": "found_issue_created",
        "ro_id": "RO-1",
        "summary": "Coolant leak",
        "payload": {"actor_id": "tech-1"},
    }
    got = recipients_for_event(ev, actor_id="tech-1", actor_name="Alex", people=PEOPLE)
    assert got == ["adv-1"]


def test_message_only_recipient():
    ev = {
        "type": "shop_message",
        "payload": {"from_id": "tech-1", "to_id": "adv-1"},
    }
    got = recipients_for_event(ev, actor_id="tech-1", actor_name="Alex", people=PEOPLE)
    assert got == ["adv-1"]
