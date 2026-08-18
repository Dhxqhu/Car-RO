from carro.core.tech_ui import merge_named_records
from carro_server.roster_merge import merge_person_rows


def test_merge_pulls_shop_techs_when_timestamps_match():
    local = [{"id": "max", "name": "Max", "pin_hash": "a"}]
    remote = [
        {"id": "max", "name": "Max", "pin_hash": "a"},
        {"id": "sam", "name": "Sam", "pin_hash": "b"},
    ]
    merged, local_changed, remote_changed = merge_named_records(
        local, remote, local_updated="2026-08-09T22:51:28", remote_updated="2026-08-09T22:51:28"
    )
    ids = {row["id"] for row in merged}
    assert ids == {"max", "sam"}
    assert local_changed is True
    assert remote_changed is False


def test_merge_keeps_local_only_tech_and_pushes():
    local = [
        {"id": "max", "name": "Max", "pin_hash": "a"},
        {"id": "pat", "name": "Pat", "pin_hash": "c"},
    ]
    remote = [{"id": "max", "name": "Max", "pin_hash": "a"}]
    merged, local_changed, remote_changed = merge_named_records(
        local, remote, local_updated="2026-08-17T21:00:00", remote_updated="2026-08-09T22:51:28"
    )
    ids = {row["id"] for row in merged}
    assert ids == {"max", "pat"}
    assert local_changed is False
    assert remote_changed is True


def test_merge_equal_ids_prefers_newer_local_name():
    local = [{"id": "max", "name": "Maxwell", "pin_hash": "a"}]
    remote = [{"id": "max", "name": "Max", "pin_hash": "a"}]
    merged, local_changed, remote_changed = merge_named_records(
        local, remote, local_updated="2026-08-18T01:00:00", remote_updated="2026-08-09T22:51:28"
    )
    assert merged[0]["name"] == "Maxwell"
    assert local_changed is False
    assert remote_changed is True


def test_server_put_merges_stale_tester_without_dropping_shop_tech():
    existing = [{"id": "samuel", "name": "Samuel", "pin_hash": "s"}]
    incoming = [{"id": "max", "name": "Max", "pin_hash": "m"}]
    merged = merge_person_rows(existing, incoming, replace=False)
    assert {row["id"] for row in merged} == {"samuel", "max"}


def test_server_put_replace_drops_omitted_people():
    existing = [{"id": "samuel", "name": "Samuel", "pin_hash": "s"}]
    incoming = [{"id": "max", "name": "Max", "pin_hash": "m"}]
    merged = merge_person_rows(existing, incoming, replace=True)
    assert [row["id"] for row in merged] == ["max"]
