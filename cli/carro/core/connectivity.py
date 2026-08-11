"""Cached shop-server reachability for offline banner + soft API paths."""

from __future__ import annotations

import threading
import time
from typing import Any

from carro.storage.remote import RemoteClient

# UI polls /sync/status every ~10–15s; cache a bit shorter so reconnect feels snappy.
_CACHE_TTL_SEC = 12.0
_PROBE_TIMEOUT_SEC = 2.5

_lock = threading.Lock()
_cache: dict[str, Any] = {
    "at": 0.0,
    "configured": False,
    "reachable": False,
    "error": None,
}


def _probe_now() -> dict[str, Any]:
    remote = RemoteClient()
    if not remote.enabled:
        return {
            "configured": False,
            "reachable": False,
            "offline": False,
            "error": None,
        }
    try:
        import httpx

        with httpx.Client(timeout=_PROBE_TIMEOUT_SEC) as client:
            r = client.get(f"{remote.base}/health", headers=remote._headers())
            r.raise_for_status()
        return {
            "configured": True,
            "reachable": True,
            "offline": False,
            "error": None,
        }
    except Exception as exc:
        return {
            "configured": True,
            "reachable": False,
            "offline": True,
            "error": str(exc)[:200],
        }


def server_connectivity(*, force: bool = False) -> dict[str, Any]:
    """
    Return {configured, reachable, offline, error}.
    offline = configured but unreachable (shop WiFi / server drop).
    """
    now = time.monotonic()
    with _lock:
        age = now - float(_cache.get("at") or 0)
        if not force and age < _CACHE_TTL_SEC and _cache.get("at"):
            configured = bool(_cache.get("configured"))
            reachable = bool(_cache.get("reachable"))
            return {
                "configured": configured,
                "reachable": reachable,
                "offline": bool(configured and not reachable),
                "error": _cache.get("error"),
            }

    probed = _probe_now()
    with _lock:
        _cache["at"] = time.monotonic()
        _cache["configured"] = probed["configured"]
        _cache["reachable"] = probed["reachable"]
        _cache["error"] = probed.get("error")
    return probed


def invalidate_connectivity_cache() -> None:
    with _lock:
        _cache["at"] = 0.0


def mark_server_reachable() -> None:
    """Call after a successful remote call so the banner clears without waiting."""
    with _lock:
        _cache["at"] = time.monotonic()
        _cache["configured"] = True
        _cache["reachable"] = True
        _cache["error"] = None


def mark_server_unreachable(error: str | None = None) -> None:
    remote = RemoteClient()
    with _lock:
        _cache["at"] = time.monotonic()
        _cache["configured"] = bool(remote.enabled)
        _cache["reachable"] = False
        _cache["error"] = (error or "")[:200] or None
