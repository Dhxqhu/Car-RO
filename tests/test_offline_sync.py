"""Offline shift / message outbox + connectivity status."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from carro.core import connectivity as conn_mod
from carro.core import message_offline as msg_off
from carro.core import shift_offline as shift_off
from carro.core.db import LocalStore
from carro.core.sync_ops import perform_sync


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalStore:
    db = tmp_path / "carro.db"
    st = LocalStore(db_path=db)
    monkeypatch.setattr(
        "carro.storage.remote.load_config",
        lambda: {"server_url": "http://shop.test", "token": "t"},
    )
    monkeypatch.setattr(
        "carro.config.load_config",
        lambda: {"server_url": "http://shop.test", "token": "t"},
    )
    return st


def test_shift_start_end_offline_preserves_timestamps(
    store: LocalStore, monkeypatch: pytest.MonkeyPatch
):
    started = "2026-08-11T09:15:00-0400"
    ended = "2026-08-11T12:30:00-0400"

    class BoomRemote:
        enabled = True

        def start_shift(self, **kwargs):
            raise ConnectionError("shop wifi down")

        def end_shift(self, **kwargs):
            raise ConnectionError("shop wifi down")

    monkeypatch.setattr(shift_off, "RemoteClient", BoomRemote)

    out = shift_off.start_shift(
        store, tech_id="T1", tech_name="Alex", started_at=started
    )
    shift = out["shift"]
    assert shift["pending_sync"] is True
    assert "09:15:00" in shift["started_at"]
    assert store.pending_shift_ops_count() >= 1

    out2 = shift_off.end_shift(
        store, tech_id="T1", shift_id=shift["id"], ended_at=ended
    )
    closed = out2["shift"]
    assert closed.get("ended_at")
    assert "12:30:00" in str(closed["ended_at"])
    assert store.pending_shift_ops_count() >= 2

    # Drain with mock that records original timestamps
    calls: dict[str, Any] = {}

    class OkRemote:
        enabled = True
        _next_id = 100

        def start_shift(self, **kwargs):
            calls["start"] = kwargs
            self._next_id += 1
            return {
                "ok": True,
                "shift": {
                    "id": self._next_id,
                    "tech_id": kwargs["tech_id"],
                    "tech_name": kwargs.get("tech_name") or "",
                    "day": kwargs.get("day") or "2026-08-11",
                    "started_at": kwargs.get("started_at") or "",
                    "ended_at": None,
                },
            }

        def end_shift(self, **kwargs):
            calls["end"] = kwargs
            return {
                "ok": True,
                "shift": {
                    "id": int(kwargs.get("shift_id") or 101),
                    "tech_id": kwargs.get("tech_id") or "T1",
                    "tech_name": "Alex",
                    "day": "2026-08-11",
                    "started_at": started,
                    "ended_at": kwargs.get("ended_at") or ended,
                },
            }

        def get_open_shift(self, tech_id: str):
            return {"shift": None}

    monkeypatch.setattr(shift_off, "RemoteClient", OkRemote)
    result = shift_off.try_push_pending_shifts(store, OkRemote())
    assert result["failed"] == 0
    assert result["cleared"] >= 2
    assert "09:15:00" in str(calls.get("start", {}).get("started_at") or "")
    assert "12:30:00" in str(calls.get("end", {}).get("ended_at") or "")
    assert store.pending_shift_ops_count() == 0


def test_message_outbox_enqueue_and_drain(
    store: LocalStore, monkeypatch: pytest.MonkeyPatch
):
    class BoomRemote:
        enabled = True

        def send_message(self, payload):
            raise ConnectionError("down")

        def list_sent_messages(self, **kwargs):
            raise ConnectionError("down")

        def list_messages(self, **kwargs):
            raise ConnectionError("down")

    monkeypatch.setattr(msg_off, "RemoteClient", BoomRemote)

    out = msg_off.send_message(
        store,
        {
            "body": "Need parts",
            "from_id": "T1",
            "from_name": "Alex",
            "from_role": "technician",
            "to_id": "A1",
            "to_name": "Sam",
            "to_role": "advisor",
        },
    )
    assert out.get("pending_sync") is True
    assert store.pending_messages_count() >= 1

    sent: list[dict[str, Any]] = []

    class OkRemote:
        enabled = True

        def send_message(self, payload):
            sent.append(payload)
            return {"ok": True, "message": {**payload, "id": 55}}

        def mark_message_read(self, *a, **k):
            return {"ok": True}

        def mark_messages_delivered(self, *a, **k):
            return {"ok": True, "count": 0}

    monkeypatch.setattr(msg_off, "RemoteClient", OkRemote)
    result = msg_off.try_push_pending_messages(store, OkRemote())
    assert result["failed"] == 0
    assert result["cleared"] >= 1
    assert sent and sent[0]["body"] == "Need parts"
    assert store.pending_messages_count() == 0


def test_sync_status_offline_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    conn_mod.invalidate_connectivity_cache()

    class FakeRemote:
        enabled = True
        base = "http://shop.test"

        def _headers(self):
            return {}

    monkeypatch.setattr(conn_mod, "RemoteClient", FakeRemote)

    import httpx

    def boom_client(*args, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "Client", boom_client)
    # _probe_now uses httpx.Client as context manager — patch differently
    class BoomCM:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            raise httpx.ConnectError("refused")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(httpx, "Client", BoomCM)

    st = conn_mod.server_connectivity(force=True)
    assert st["configured"] is True
    assert st["reachable"] is False
    assert st["offline"] is True

    # LocalStore pending includes shift/message counts
    store = LocalStore(db_path=tmp_path / "s.db")
    status = store.sync_status()
    assert "pending_shifts" in status
    assert "pending_messages" in status
    assert status["pending_total"] == (
        status["pending_ros"]
        + status["pending_deletes"]
        + status["pending_shifts"]
        + status["pending_messages"]
    )


def test_perform_sync_drains_shifts(store: LocalStore, monkeypatch: pytest.MonkeyPatch):
    # Queue a local shift while remote down
    class BoomRemote:
        enabled = True

        def start_shift(self, **kwargs):
            raise ConnectionError("down")

        def check_server_compat(self, force=False):
            return {"api_version": 99}

        def health(self):
            return {"api_version": 99}

    monkeypatch.setattr(shift_off, "RemoteClient", BoomRemote)
    shift_off.start_shift(
        store,
        tech_id="T9",
        tech_name="Pat",
        started_at="2026-08-11T08:00:00-0400",
    )
    assert store.pending_shift_ops_count() >= 1

    class OkRemote:
        enabled = True
        _id = 200

        def check_server_compat(self, force=False):
            return {"api_version": 99}

        def start_shift(self, **kwargs):
            self._id += 1
            return {
                "ok": True,
                "shift": {
                    "id": self._id,
                    "tech_id": kwargs["tech_id"],
                    "tech_name": kwargs.get("tech_name") or "",
                    "day": "2026-08-11",
                    "started_at": kwargs.get("started_at") or "",
                    "ended_at": None,
                },
            }

        def end_shift(self, **kwargs):
            return {"ok": True, "shift": {}}

        def get_open_shift(self, tech_id: str):
            return {"shift": None}

        def list_pending_deletes(self):
            return []

    # perform_sync constructs RemoteClient() — patch at storage.remote and modules
    monkeypatch.setattr("carro.core.sync_ops.RemoteClient", OkRemote)
    monkeypatch.setattr(shift_off, "RemoteClient", OkRemote)
    monkeypatch.setattr(msg_off, "RemoteClient", OkRemote)
    monkeypatch.setattr(
        "carro.core.tech_ui.sync_roster_with_server", lambda: "skipped"
    )

    result = perform_sync(store, pending_only=True, sync_roster=False, do_prune=False)
    assert result.get("shifts", {}).get("failed", 0) == 0
    assert store.pending_shift_ops_count() == 0
