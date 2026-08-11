"""
Background autosync timer (minutes). Default 15.

Runs while the carro engine or interactive CLI menu is up so bay PCs can keep
the shop server current without manual sync.

Even when autosync_minutes is 0, pending (unsynced) local edits are retried
every couple of minutes whenever a server_url is configured — so a temporary
outage does not leave work stranded on one bay.

Designed to stay light: no server calls when quiet, pending-only pushes,
backoff when unreachable, queue rollover only on maintenance ticks.
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

# Retry dirty ROs this often when the queue is non-empty (seconds).
_PENDING_RETRY_SEC = 120.0
# Worker wake interval to re-read config / pending counts (no HTTP by itself).
_WAKE_SEC = 15.0
_BACKOFF_START = 30.0
_BACKOFF_CAP = 300.0

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


def _pending_total(store: LocalStore) -> int:
    try:
        return int(store.pending_sync_count())
    except Exception:
        try:
            return int((store.sync_status() or {}).get("pending_total") or 0)
        except Exception:
            return 0


def _worker() -> None:
    last_full = 0.0
    last_pending = 0.0
    backoff = _BACKOFF_START
    unreachable_until = 0.0

    while not _stop.is_set():
        wake = _WAKE_SEC
        try:
            minutes = resolve_autosync_minutes(load_config())
            store = _store or LocalStore()
            remote_on = RemoteClient().enabled
            pending_n = _pending_total(store) if remote_on else 0

            with _lock:
                _status["interval_minutes"] = minutes
                _status["enabled"] = minutes > 0
                _status["running"] = True
                _status["pending_retry"] = bool(remote_on and pending_n > 0)

            now = time.time()

            if not remote_on:
                with _lock:
                    _status["next_due_at"] = None
                if _stop.wait(wake):
                    break
                continue

            if now < unreachable_until:
                wake = min(wake, max(1.0, unreachable_until - now))
                with _lock:
                    if minutes > 0 and last_full > 0:
                        _status["next_due_at"] = _iso(last_full + minutes * 60)
                    else:
                        _status["next_due_at"] = None
                if _stop.wait(wake):
                    break
                continue

            ran = False
            ok = True

            # Maintenance tick (timed) or first short delay after start.
            if minutes > 0:
                interval = float(max(1, minutes) * 60)
                if last_full <= 0.0:
                    with _lock:
                        _status["next_due_at"] = _iso(now + _WAKE_SEC)
                    if _stop.wait(_WAKE_SEC):
                        break
                    ok = _run_once(maintenance=True)
                    ran = True
                    last_full = time.time()
                    last_pending = last_full
                elif now - last_full >= interval:
                    ok = _run_once(maintenance=True)
                    ran = True
                    last_full = time.time()
                    last_pending = last_full
                with _lock:
                    _status["next_due_at"] = _iso(last_full + interval)

            # Mid-interval (or autosync-off) pending drain — only when dirty.
            if (
                not ran
                and pending_n > 0
                and (now - last_pending) >= _PENDING_RETRY_SEC
            ):
                with _lock:
                    if minutes <= 0:
                        _status["next_due_at"] = None
                ok = _run_once(maintenance=False)
                ran = True
                last_pending = time.time()
            elif minutes <= 0:
                with _lock:
                    _status["next_due_at"] = None

            if ran:
                if ok:
                    backoff = _BACKOFF_START
                    unreachable_until = 0.0
                else:
                    # Only back off when the failure was reachability (see _run_once).
                    with _lock:
                        reason = str(_status.get("last_error") or "")
                    if "unreachable" in reason.lower() or "Server unreachable" in reason:
                        unreachable_until = time.time() + backoff
                        backoff = min(_BACKOFF_CAP, backoff * 2)
                        wake = min(wake, backoff)
        except Exception as exc:  # noqa: BLE001
            log.warning("autosync loop error: %s", exc)
            with _lock:
                _status["last_error"] = str(exc)
                _status["last_ok"] = False
        if _stop.wait(wake):
            break


def _run_once(*, maintenance: bool) -> bool:
    """
    maintenance=True: queue rollover + pending push + roster + prune.
    maintenance=False: pending push only (no rollover / no roster).
    Returns True if sync reported ok (or skipped cleanly).
    """
    store = _store or LocalStore()
    try:
        if maintenance:
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

        # Always pending-only pushes; maintenance also syncs roster + prune.
        result = perform_sync(
            store,
            pending_only=True,
            sync_roster=maintenance,
            do_prune=maintenance,
        )
        msg = str(result.get("message") or "ok")
        ok = bool(result.get("ok"))
        reason = str(result.get("reason") or "")
        err = None if ok else str(result.get("error") or msg)
        if reason == "unreachable" and err and "unreachable" not in err.lower():
            err = f"unreachable: {err}"
        with _lock:
            _status["last_run_at"] = datetime.now(tz=timezone.utc).isoformat()
            _status["last_ok"] = ok
            _status["last_message"] = msg
            _status["last_error"] = err
        log.info(
            "autosync%s: %s",
            " (maintenance)" if maintenance else " (pending)",
            msg,
        )
        return ok
    except Exception as exc:  # noqa: BLE001
        with _lock:
            _status["last_run_at"] = datetime.now(tz=timezone.utc).isoformat()
            _status["last_ok"] = False
            _status["last_error"] = str(exc)
            _status["last_message"] = None
        log.warning("autosync failed: %s", exc)
        return False
