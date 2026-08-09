"""Adapter session.lock ownership rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from carro.obd import session_lock as sl


@pytest.fixture()
def lock_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "session.lock"
    monkeypatch.setattr(sl, "LOCK_FILE", path)
    path.unlink(missing_ok=True)
    return path


def test_acquire_and_release(lock_file):
    sl.acquire_lock(owner="obdscan-cli", port="/dev/rfcomm0")
    st = sl.lock_status()
    assert st["held"] is True
    assert st["owner"] == "obdscan-cli"
    assert st["port"] == "/dev/rfcomm0"
    assert sl.release_lock(owner="obdscan-cli") is True
    assert sl.lock_status()["held"] is False


def test_second_owner_blocked(lock_file):
    sl.acquire_lock(owner="obdscan-cli", port="/dev/rfcomm0")
    with pytest.raises(sl.AdapterBusyError, match="obdscan-cli"):
        sl.acquire_lock(owner="carro-engine", port="/dev/ttyUSB0")
    sl.release_lock(owner="obdscan-cli")


def test_stale_lock_replaced(lock_file):
    # Fake a dead PID
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(
        '{\n  "pid": 999999999,\n  "owner": "obdscan-cli",\n  "port": "/dev/rfcomm0"\n}\n',
        encoding="utf-8",
    )
    st = sl.lock_status()
    assert st["held"] is False
    assert st.get("stale") is True
    sl.acquire_lock(owner="carro-engine", port="/dev/rfcomm0")
    assert sl.lock_status()["owner"] == "carro-engine"
    sl.release_lock(owner="carro-engine")
