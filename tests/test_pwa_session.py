"""Phone PWA PIN sessions on carro-server (not the shop API token)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from carro_server.pin import hash_pin
from carro_server.volumes import VolumeManager
from carro_server.upload_tokens import UploadTokenStore


@pytest.fixture()
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import carro_server.main as m

    monkeypatch.setattr(m, "TOKEN", "shop-secret")
    vols = VolumeManager(root=tmp_path)
    monkeypatch.setattr(m, "VOLUMES", vols)
    monkeypatch.setattr(m, "SESSIONS_PATH", tmp_path / "app_sessions.json")
    monkeypatch.setattr(m, "UPLOADS", UploadTokenStore(tmp_path / "upload_sessions.json"))
    roster = {
        "version": 1,
        "updated": "2026-08-11T00:00:00",
        "admin_pin_hash": hash_pin("0000"),
        "technicians": [
            {"id": "tech-1", "name": "Alex", "pin_hash": hash_pin("1234")},
        ],
    }
    (tmp_path / "technicians.json").write_text(
        __import__("json").dumps(roster, indent=2) + "\n", encoding="utf-8"
    )
    advisors = {
        "version": 1,
        "updated": "2026-08-11T00:00:00",
        "advisors": [
            {
                "id": "adv-1",
                "name": "Sam",
                "pin_hash": hash_pin("5678"),
                "working_privilege": True,
            }
        ],
    }
    (tmp_path / "advisors.json").write_text(
        __import__("json").dumps(advisors, indent=2) + "\n", encoding="utf-8"
    )
    return TestClient(m.app), m


def test_people_is_public_and_strips_hashes(server):
    client, _m = server
    r = client.get("/people")
    assert r.status_code == 200
    body = r.json()
    assert body["empty"] is False
    ids = {p["id"] for p in body["people"]}
    assert ids == {"tech-1", "adv-1"}
    for p in body["people"]:
        assert "pin_hash" not in p


def test_shop_token_still_lists_technicians(server):
    client, _m = server
    r = client.get("/technicians", headers={"Authorization": "Bearer shop-secret"})
    assert r.status_code == 200
    assert r.json()["technicians"][0]["pin_hash"]


def test_pin_login_cookie_and_session(server):
    client, _m = server
    r = client.post("/session/login", json={"id": "tech-1", "pin": "1234"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "technician"
    assert body["name"] == "Alex"
    assert body["token"]
    assert client.cookies.get("carro_session") == body["token"]

    who = client.get("/session")
    assert who.status_code == 200
    assert who.json()["id"] == "tech-1"

    ros = client.get("/ros")
    assert ros.status_code == 200
    assert ros.json() == []


def test_wrong_pin_rejected(server):
    client, _m = server
    r = client.post("/session/login", json={"id": "tech-1", "pin": "9999"})
    assert r.status_code == 401


def test_session_cannot_read_roster_hashes(server):
    client, _m = server
    client.post("/session/login", json={"id": "adv-1", "pin": "5678"})
    r = client.get("/technicians")
    assert r.status_code == 403


def test_create_ro_as_advisor(server):
    client, _m = server
    client.post("/session/login", json={"id": "adv-1", "pin": "5678"})
    r = client.post(
        "/ros",
        json={
            "first_name": "Pat",
            "last_name": "Lee",
            "year": "2014",
            "make": "Ford",
            "model": "Focus",
            "complaint": "No crank",
        },
    )
    assert r.status_code == 200, r.text
    order = r.json()
    assert order["id"].startswith("RO-")
    assert order["last_name"] == "Lee"
    assert order["work_items"]
    got = client.get(f"/ros/{order['id']}")
    assert got.status_code == 200
    assert got.json()["complaint"] == "No crank" or got.json()["work_items"]


def test_missing_auth_rejected_when_token_set(server):
    client, _m = server
    r = client.get("/ros")
    assert r.status_code in (401, 403)


def test_push_subscribe_after_pin_login(server):
    client, m = server
    client.post("/session/login", json={"id": "tech-1", "pin": "1234"})
    vapid = client.get("/push/vapid")
    assert vapid.status_code == 200, vapid.text
    assert vapid.json()["public_key"]
    assert vapid.json()["subscribed"] is False
    r = client.post(
        "/push/subscribe",
        json={
            "endpoint": "https://web.push.apple.com/test-endpoint",
            "keys": {"p256dh": "abc", "auth": "def"},
        },
    )
    assert r.status_code == 200, r.text
    again = client.get("/push/vapid")
    assert again.json()["subscribed"] is True
    off = client.post("/push/unsubscribe", json={})
    assert off.status_code == 200
    assert client.get("/push/vapid").json()["subscribed"] is False
