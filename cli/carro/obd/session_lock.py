"""
Exclusive adapter session lock — keep in lockstep with obdscan ``session_lock.py``.

Lock file: ~/.cache/obdscan/session.lock
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOCK_FILE = Path.home() / ".cache" / "obdscan" / "session.lock"

Owner = str  # "obdscan-cli" | "carro-engine" | "obdscan-gui"


class AdapterBusyError(RuntimeError):
    """Another living process holds the adapter lock."""


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read_lock() -> dict[str, Any] | None:
    if not LOCK_FILE.is_file():
        return None
    try:
        raw = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def lock_status() -> dict[str, Any]:
    data = read_lock()
    if not data:
        return {"held": False, "path": str(LOCK_FILE)}
    pid = int(data.get("pid") or 0)
    alive = _pid_alive(pid)
    return {
        "held": alive,
        "stale": not alive,
        "path": str(LOCK_FILE),
        "pid": pid,
        "owner": data.get("owner"),
        "port": data.get("port"),
        "started_at": data.get("started_at"),
        "alive": alive,
    }


def acquire_lock(*, owner: Owner, port: str) -> None:
    status = lock_status()
    if status.get("held"):
        pid = status.get("pid")
        other = status.get("owner") or "unknown"
        if pid == os.getpid() and other == owner:
            _write_lock(owner=owner, port=port)
            return
        raise AdapterBusyError(
            f"Adapter in use by {other} (pid {pid}). "
            "Close that session first, or wait for a stale lock to clear."
        )
    if status.get("stale"):
        try:
            LOCK_FILE.unlink(missing_ok=True)
        except OSError:
            pass
    _write_lock(owner=owner, port=port)


def release_lock(*, owner: Owner | None = None) -> bool:
    data = read_lock()
    if not data:
        return False
    pid = int(data.get("pid") or 0)
    if pid != os.getpid():
        return False
    if owner is not None and data.get("owner") != owner:
        return False
    try:
        LOCK_FILE.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _write_lock(*, owner: Owner, port: str) -> None:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "owner": owner,
        "port": port,
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_at": time.time(),
    }
    tmp = LOCK_FILE.with_suffix(".lock.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(LOCK_FILE)
