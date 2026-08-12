"""Auto-archive of closed weekly tech reports."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from carro.core.db import LocalStore
from carro.core.weekly_reports import (
    archive_closed_week_if_needed,
    previous_closed_week_start,
    sunday_on_or_before,
    week_end_saturday,
)


@pytest.fixture()
def store(tmp_path: Path) -> LocalStore:
    return LocalStore(db_path=tmp_path / "carro.db")


def test_previous_closed_week_start_boundaries():
    # Sunday 2026-08-09 → prior week starts 2026-08-02
    assert previous_closed_week_start(date(2026, 8, 9)) == date(2026, 8, 2)
    # Monday after that week
    assert previous_closed_week_start(date(2026, 8, 10)) == date(2026, 8, 2)
    # Saturday of current week still points at prior closed week
    assert previous_closed_week_start(date(2026, 8, 15)) == date(2026, 8, 2)
    # Next Sunday rolls forward
    assert previous_closed_week_start(date(2026, 8, 16)) == date(2026, 8, 9)


class _FakeRemote:
    def __init__(self, *, enabled: bool = True, existing: dict[str, Any] | None = None):
        self.enabled = enabled
        self._existing = existing
        self.saved: list[dict[str, Any]] = []
        self.save_calls = 0

    def get_weekly_report_snapshot(self, week_start: str) -> dict[str, Any]:
        if self._existing and self._existing.get("week_start") == week_start:
            return {"snapshot": self._existing}
        return {"snapshot": None}

    def list_ros(self) -> list[dict[str, Any]]:
        return []

    def list_shifts(self, **_kwargs: Any) -> dict[str, Any]:
        return {"shifts": []}

    def save_weekly_report(
        self,
        week_start: str,
        *,
        week_end: str,
        payload: dict[str, Any],
        created_by: str = "",
        created_by_id: str = "",
    ) -> dict[str, Any]:
        self.save_calls += 1
        snap = {
            "week_start": week_start,
            "week_end": week_end,
            "payload": payload,
            "created_by": created_by,
            "created_by_id": created_by_id,
        }
        self.saved.append(snap)
        self._existing = snap
        return {"ok": True, "snapshot": snap}


def test_archive_skipped_when_no_server(store: LocalStore):
    remote = _FakeRemote(enabled=False)
    out = archive_closed_week_if_needed(
        store, remote=remote, today=date(2026, 8, 12)
    )
    assert out["ok"] is False
    assert out["skipped"] == "no_server"
    assert remote.save_calls == 0


def test_archive_skipped_when_snapshot_exists(store: LocalStore):
    prev = previous_closed_week_start(date(2026, 8, 12))
    remote = _FakeRemote(
        existing={
            "week_start": prev.isoformat(),
            "week_end": week_end_saturday(prev).isoformat(),
            "payload": {"techs": []},
        }
    )
    out = archive_closed_week_if_needed(
        store, remote=remote, today=date(2026, 8, 12)
    )
    assert out["ok"] is True
    assert out["skipped"] == "exists"
    assert remote.save_calls == 0


def test_archive_inserts_payload_with_efficiency(store: LocalStore):
    today = date(2026, 8, 12)  # Wednesday
    prev = previous_closed_week_start(today)
    assert sunday_on_or_before(today) == date(2026, 8, 9)
    assert prev == date(2026, 8, 2)

    remote = _FakeRemote()
    out = archive_closed_week_if_needed(store, remote=remote, today=today)
    assert out.get("archived") is True
    assert out["week_start"] == prev.isoformat()
    assert remote.save_calls == 1
    payload = remote.saved[0]["payload"]
    assert payload["week_start"] == prev.isoformat()
    assert payload["week_end"] == week_end_saturday(prev).isoformat()
    assert "efficiency" in payload
    assert payload["efficiency"]["week_start"] == prev.isoformat()
    assert remote.saved[0]["created_by"] == "autosync"

    # Second call must not overwrite
    out2 = archive_closed_week_if_needed(store, remote=remote, today=today)
    assert out2.get("skipped") == "exists"
    assert remote.save_calls == 1
