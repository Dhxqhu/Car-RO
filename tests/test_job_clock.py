from carro_server.job_clock import (
    release_tech_current,
    start_item_timer,
    tech_has_live_timer,
)


def _order(**overrides):
    base = {
        "id": "RO-1",
        "status": "open",
        "current_tech_id": "",
        "current_tech_name": "",
        "current_since": "",
        "current_item_id": "",
        "work_items": [
            {
                "id": "WI-1",
                "concern": "Brakes",
                "status": "open",
                "timer_started_at": "",
                "timer_tech_id": "",
                "timer_tech_name": "",
                "worked_minutes": 0,
                "time_log": [],
            },
            {
                "id": "WI-2",
                "concern": "Oil leak",
                "status": "open",
                "timer_started_at": "",
                "timer_tech_id": "",
                "timer_tech_name": "",
                "worked_minutes": 0,
                "time_log": [],
            },
        ],
    }
    base.update(overrides)
    return base


def test_start_item_timer_sets_current_and_item():
    order = _order()
    start_item_timer(order, tech_id="tech-1", tech_name="Alex", item_id="WI-2")
    assert order["current_tech_id"] == "tech-1"
    assert order["current_item_id"] == "WI-2"
    assert order["status"] == "in_progress"
    item = next(it for it in order["work_items"] if it["id"] == "WI-2")
    assert item["timer_tech_id"] == "tech-1"
    assert item["timer_started_at"]
    assert item["status"] == "in_progress"


def test_start_moves_timer_off_previous_item():
    order = _order()
    start_item_timer(order, tech_id="tech-1", tech_name="Alex", item_id="WI-1")
    first = order["work_items"][0]
    first["timer_started_at"] = "2000-01-01T00:00:00"
    start_item_timer(order, tech_id="tech-1", tech_name="Alex", item_id="WI-2")
    assert not order["work_items"][0]["timer_started_at"]
    assert order["work_items"][0]["worked_minutes"] > 0
    assert order["current_item_id"] == "WI-2"
    assert order["work_items"][1]["timer_started_at"]


def test_release_stops_only_this_tech():
    order = _order()
    start_item_timer(order, tech_id="tech-1", tech_name="Alex", item_id="WI-1")
    assert tech_has_live_timer(order, tech_id="tech-1", tech_name="Alex")
    assert release_tech_current(order, tech_id="tech-1", tech_name="Alex", item_id="WI-1")
    assert not order["work_items"][0]["timer_started_at"]
    assert not order["current_tech_id"]
    assert not tech_has_live_timer(order, tech_id="tech-1", tech_name="Alex")
