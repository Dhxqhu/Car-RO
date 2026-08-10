"""
Background autosync timer (minutes). Default off (0).

Runs while the carro engine or interactive CLI menu is up so bay PCs can keep
the shop server current without manual sync.

Even when autosync_minutes is 0, pending (unsynced) local edits are retried
every couple of minutes whenever a server_url is configured — so a temporary
outage does not leave work stranded on one bay.
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
from carro.storage.remote import RemoteClient

log = logging.getLogger("carro.autosync")

# When full autosync is off, still retry dirty ROs this often (seconds).
_PENDING_RETRY_SEC = 120.0

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
    "pending_retry": False,
}


def autosync_status() -> dict[str, Any]:
    with _lock:
        st = dict(_status)
    cfg_mins = resolve_autosync_minutes()
    st["interval_minutes"] = cfg_mins
    st["enabled"] = cfg_mins > 0
    try:
        store = _store or LocalStore()
        st["pending"] = store.sync_status()
    except Exception:
        st["pending"] = {"pending_total": 0}
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
    last_full = 0.0
    last_pending = 0.0
    while not _stop.is_set():
        try:
            minutes = resolve_autosync_minutes(load_config())
            store = _store or LocalStore()
            remote_on = RemoteClient().enabled
            pending_n = 0
            try:
                pending_n = int(store.pending_sync_count())
            except Exception:
                pending_n = 0

            with _lock:
                _status["interval_minutes"] = minutes
                _status["enabled"] = minutes > 0
                _status["running"] = True
                _status["pending_retry"] = bool(remote_on and pending_n > 0)

            now = time.time()

            if minutes > 0:
                interval = float(max(1, minutes) * 60)
                if last_full <= 0.0:
                    with _lock:
                        _status["next_due_at"] = _iso(now + poll)
                    if _stop.wait(poll):
                        break
                    _run_once(pending_only=False)
                    last_full = time.time()
                    last_pending = last_full
                elif now - last_full >= interval:
                    _run_once(pending_only=False)
                    last_full = time.time()
                    last_pending = last_full
                with _lock:
                    _status["next_due_at"] = _iso(last_full + interval)
            else:
                # Autosync off: still drain the pending queue when the server returns.
                with _lock:
                    _status["next_due_at"] = None
                if remote_on and pending_n > 0 and (now - last_pending) >= _PENDING_RETRY_SEC:
                    _run_once(pending_only=True)
                    last_pending = time.time()
        except Exception as exc:  # noqa: BLE001
            log.warning("autosync loop error: %s", exc)
            with _lock:
                _status["last_error"] = str(exc)
                _status["last_ok"] = False
        _stop.wait(poll)


def _run_once(*, pending_only: bool = False) -> None:
    store = _store or LocalStore()
    try:
        # Calendar-day queue rollover (next_day → daily, leftover daily → next_day)
        try:
            from carro.core.queue_lanes import rollover_all_orders
            from carro.core.sync_ops import try_push_ro

            for order in rollover_all_orders(store.list_orders()):
                store.save(order)
                try_push_ro(
                    store,
                    order,
                    actor="autosync",
                    actor_id="",
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("queue rollover: %s", exc)

        result = perform_sync(store, pending_only=pending_only)
        msg = str(result.get("message") or "ok")
        with _lock:
            _status["last_run_at"] = datetime.now(tz=timezone.utc).isoformat()
            _status["last_ok"] = bool(result.get("ok"))
            _status["last_message"] = msg
            _status["last_error"] = (
                None if result.get("ok") else str(result.get("error") or msg)
            )
        log.info("autosync%s: %s", " (pending)" if pending_only else "", msg)
    except Exception as exc:  # noqa: BLE001
        with _lock:
            _status["last_run_at"] = datetime.now(tz=timezone.utc).isoformat()
            _status["last_ok"] = False
            _status["last_error"] = str(exc)
            _status["last_message"] = None
        log.warning("autosync failed: %s", exc)
