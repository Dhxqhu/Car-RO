"""
Background autosync timer (minutes). Default off (0).

Runs while the carro engine or interactive CLI menu is up so bay PCs can keep
the shop server current for a future advisor app without manual sync.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

from carro.config import load_config, resolve_autosync_minutes
from carro.core.db import LocalStore
from carro.core.sync_ops import perform_sync

log = logging.getLogger("carro.autosync")

_lock = threading.Lock()
_stop = threading.Event()
_thread: threading.Thread | None = None
_store: LocalStore | None = None
_status: dict[str, Any] = {
    "enabled": False,
    "interval_minutes": 0,
    "running": False,
    "last_run_at": None,
    "last_ok": None,
    "last_message": None,
    "last_error": None,
    "next_due_at": None,
}


def autosync_status() -> dict[str, Any]:
    with _lock:
        st = dict(_status)
    cfg_mins = resolve_autosync_minutes()
    st["interval_minutes"] = cfg_mins
    st["enabled"] = cfg_mins > 0
    return st


def start_autosync(store: LocalStore | None = None) -> None:
    """Idempotent: ensure the background worker is running."""
    global _thread, _store
    with _lock:
        if store is not None:
            _store = store
        elif _store is None:
            _store = LocalStore()
        if _thread is not None and _thread.is_alive():
            return
        _stop.clear()
        _thread = threading.Thread(
            target=_worker,
            name="carro-autosync",
            daemon=True,
        )
        _thread.start()
        _status["running"] = True


def stop_autosync() -> None:
    global _thread
    _stop.set()
    t = _thread
    if t is not None and t.is_alive():
        t.join(timeout=2.0)
    with _lock:
        _thread = None
        _status["running"] = False


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _worker() -> None:
    poll = 15.0
    last_run = 0.0
    while not _stop.is_set():
        try:
            minutes = resolve_autosync_minutes(load_config())
            with _lock:
                _status["interval_minutes"] = minutes
                _status["enabled"] = minutes > 0
                _status["running"] = True

            if minutes <= 0:
                last_run = 0.0
                with _lock:
                    _status["next_due_at"] = None
                _stop.wait(poll)
                continue

            interval = float(max(1, minutes) * 60)
            now = time.time()
            if last_run <= 0.0:
                # First run shortly after enable (one poll), then every N minutes.
                with _lock:
                    _status["next_due_at"] = _iso(now + poll)
                if _stop.wait(poll):
                    break
                _run_once()
                last_run = time.time()
            elif now - last_run >= interval:
                _run_once()
                last_run = time.time()

            with _lock:
                _status["next_due_at"] = _iso(last_run + interval)
        except Exception as exc:  # noqa: BLE001
            log.warning("autosync loop error: %s", exc)
            with _lock:
                _status["last_error"] = str(exc)
                _status["last_ok"] = False
        _stop.wait(poll)


def _run_once() -> None:
    store = _store or LocalStore()
    try:
        result = perform_sync(store)
        msg = str(result.get("message") or "ok")
        with _lock:
            _status["last_run_at"] = datetime.now(tz=timezone.utc).isoformat()
            _status["last_ok"] = True
            _status["last_message"] = msg
            _status["last_error"] = None
        log.info("autosync: %s", msg)
    except Exception as exc:  # noqa: BLE001
        with _lock:
            _status["last_run_at"] = datetime.now(tz=timezone.utc).isoformat()
            _status["last_ok"] = False
            _status["last_error"] = str(exc)
            _status["last_message"] = None
        log.warning("autosync failed: %s", exc)
