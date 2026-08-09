"""
Process-wide OBD session owned by the Car-RO engine.

Uses obdscan's ElmSession when OBDSCAN_ROOT (or sibling checkout) is available,
and the shared adapter lock so CLI / GUI do not fight the same dongle.
"""

from __future__ import annotations

import atexit
import os
import sys
from pathlib import Path
from typing import Any

from carro.obd.session_lock import AdapterBusyError, acquire_lock, lock_status, release_lock

OWNER = "carro-engine"

_state: dict[str, Any] = {
    "connected": False,
    "port": None,
    "baud": None,
    "adapter_label": None,
    "protocol": None,
    "vin": None,
    "elm_version": None,
    "ecu_alive": None,
}
_elm: Any = None
_atexit_registered = False
_live_pids: list[str] | None = None
_profile_store: Any = None
_dtc_db: dict[str, str] | None = None


def obdscan_root() -> Path | None:
    env = os.environ.get("OBDSCAN_ROOT", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if (p / "elm.py").is_file():
            return p
    sibling = Path(__file__).resolve().parents[3] / "obdscan"
    if (sibling / "elm.py").is_file():
        return sibling
    return None


def ensure_obdscan_path() -> Path:
    root = obdscan_root()
    if not root:
        raise RuntimeError(
            "obdscan not found. Set OBDSCAN_ROOT or clone obdscan next to Car-RO."
        )
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    return root


# Back-compat alias for internal callers
_ensure_obdscan_path = ensure_obdscan_path


def public_session() -> dict[str, Any]:
    return dict(_state)


def connect(
    *,
    port: str | None = None,
    baud: int | None = None,
    adapter_id: str | None = None,
) -> dict[str, Any]:
    global _elm, _atexit_registered
    root = _ensure_obdscan_path()

    from adapters import adapter_label, load_store, resolve_connection  # type: ignore
    from elm import ElmSession  # type: ignore

    label: str
    if adapter_id:
        store = load_store()
        adapters = store.get("adapters") or {}
        ad = adapters.get(adapter_id)
        if not isinstance(ad, dict):
            raise ValueError(f"Unknown adapter id: {adapter_id}")
        from platform_ports import default_serial_port  # type: ignore

        use_port = port or str(ad.get("port") or default_serial_port())
        use_baud = int(baud if baud is not None else ad.get("baud") or 38400)
        label = adapter_label(ad)
    else:
        conn = resolve_connection(cli_port=port, cli_baud=baud)
        use_port = str(conn["port"])
        use_baud = int(conn["baud"])
        label = str(conn.get("label") or use_port)

    if _state["connected"] and _elm is not None:
        if _state.get("port") == use_port and _state.get("baud") == use_baud:
            return public_session()
        disconnect()

    acquire_lock(owner=OWNER, port=use_port)

    session = ElmSession(use_port, use_baud, timeout=2.0)
    try:
        info = session.open()
    except Exception:
        release_lock(owner=OWNER)
        raise

    _elm = session
    _state.update(
        {
            "connected": True,
            "port": use_port,
            "baud": use_baud,
            "adapter_label": label,
            "protocol": getattr(info, "protocol", None),
            "vin": None,
            "elm_version": getattr(info, "version", None),
            "ecu_alive": getattr(info, "ecu_alive", None),
            "obdscan_root": str(root),
        }
    )
    if not _atexit_registered:
        atexit.register(lambda: disconnect(quiet=True))
        _atexit_registered = True
    return public_session()


def disconnect(*, quiet: bool = False) -> dict[str, Any]:
    global _elm
    _ = quiet
    if _elm is not None:
        try:
            _elm.close()
        except Exception:
            pass
        _elm = None
    release_lock(owner=OWNER)
    _state.update(
        {
            "connected": False,
            "port": None,
            "baud": None,
            "adapter_label": None,
            "protocol": None,
            "vin": None,
            "elm_version": None,
            "ecu_alive": None,
        }
    )
    return public_session()


def health_extras() -> dict[str, Any]:
    root = obdscan_root()
    return {
        "obdscan_root": str(root) if root else None,
        "obdscan_found": root is not None,
        "wired": root is not None,
        "session": public_session(),
        "lock": lock_status(),
    }


def require_elm() -> Any:
    """Return the live ElmSession or raise RuntimeError."""
    if _elm is None or not _state.get("connected"):
        raise RuntimeError("Not connected — use Scanner Connect first.")
    return _elm


def set_vin(vin: str | None) -> None:
    _state["vin"] = vin


_DEFAULT_LIVE = ["RPM", "SPEED", "COOLANT", "LOAD", "THROTTLE"]


def get_live_pids() -> list[str]:
    global _live_pids
    if _live_pids is None:
        _live_pids = list(_DEFAULT_LIVE)
    return list(_live_pids)


def set_live_pids(pids: list[str]) -> list[str]:
    global _live_pids
    cleaned = [p.strip().upper() for p in pids if p and str(p).strip()]
    _live_pids = cleaned
    return list(_live_pids)


def profile_store() -> Any:
    global _profile_store
    ensure_obdscan_path()
    if _profile_store is None:
        from custom_pids import ProfileStore  # type: ignore

        _profile_store = ProfileStore()
    else:
        _profile_store.load()
    return _profile_store


def dtc_db() -> dict[str, str]:
    """Load generic DTC definitions; reload if a prior attempt returned empty."""
    global _dtc_db
    ensure_obdscan_path()
    if _dtc_db is None or len(_dtc_db) == 0:
        from dtc_db import load_dtc_db  # type: ignore

        _dtc_db = load_dtc_db()
    return _dtc_db


__all__ = [
    "AdapterBusyError",
    "connect",
    "disconnect",
    "dtc_db",
    "ensure_obdscan_path",
    "get_live_pids",
    "health_extras",
    "obdscan_root",
    "profile_store",
    "public_session",
    "require_elm",
    "set_live_pids",
    "set_vin",
]
