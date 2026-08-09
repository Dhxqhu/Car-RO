"""
FastAPI routes that will drive obdscan from the desktop GUI.

Framework only for now: status + stubs. Real ELM/DoIP work lands later by
calling into the sibling ``obdscan`` package (see ``OBDSCAN_ROOT``).

Filesystem handoff paths come from ``carro.obd.paths`` — same as CLI pull.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from carro.obd.paths import adapters_file, last_vehicle_file, saved_codes_dir

router = APIRouter(prefix="/obd", tags=["obd"])

# In-memory session placeholder until ElmSession is wired through.
_session: dict[str, Any] = {
    "connected": False,
    "port": None,
    "baud": None,
    "adapter_label": None,
    "protocol": None,
    "vin": None,
}


def _obdscan_root() -> Path | None:
    env = os.environ.get("OBDSCAN_ROOT", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if (p / "obdscan.py").is_file() or (p / "elm.py").is_file():
            return p
    # Common sibling checkout next to Car-RO
    sibling = Path(__file__).resolve().parents[3] / "obdscan"
    if (sibling / "obdscan.py").is_file():
        return sibling
    return None


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None


class ConnectBody(BaseModel):
    port: str | None = None
    baud: int | None = None
    adapter_id: str | None = Field(default=None, description="Saved adapter id from adapters.json")


class LivePidsBody(BaseModel):
    pids: list[str] = Field(default_factory=list)
    interval: float = 0.4


@router.get("/health")
def obd_health() -> dict[str, Any]:
    root = _obdscan_root()
    lv = last_vehicle_file()
    sc = saved_codes_dir()
    return {
        "ok": True,
        "obdscan_root": str(root) if root else None,
        "obdscan_found": root is not None,
        "wired": False,  # flips true when ElmSession is hooked up
        "session": dict(_session),
        "paths": {
            "saved_codes": str(sc),
            "last_vehicle": str(lv),
            "adapters": str(adapters_file()),
            "last_vehicle_exists": lv.is_file(),
            "saved_codes_exists": sc.is_dir(),
        },
    }


@router.get("/adapters")
def list_adapters() -> dict[str, Any]:
    path = adapters_file()
    raw = _read_json(path)
    adapters: list[dict[str, Any]] = []
    default_id: str | None = None
    if isinstance(raw, dict):
        default_id = str(raw.get("default") or "") or None
        items = raw.get("adapters") or {}
        # obdscan stores adapters as { id: { label, port, baud, ... } }
        if isinstance(items, dict):
            for aid, item in items.items():
                if isinstance(item, dict):
                    adapters.append({"id": str(aid), **item})
        elif isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    adapters.append(item)
    return {
        "path": str(path),
        "default_id": default_id,
        "adapters": adapters,
        "note": "Read-only scaffold — edit via obdscan CLI Config for now.",
    }


@router.get("/session")
def get_session() -> dict[str, Any]:
    return {"session": dict(_session)}


@router.post("/connect")
def connect(body: ConnectBody) -> dict[str, Any]:
    """
    Placeholder connect. Returns 501 until the GUI engine owns an ElmSession.
    """
    root = _obdscan_root()
    if not root:
        raise HTTPException(
            503,
            "obdscan not found. Set OBDSCAN_ROOT or clone obdscan next to Car-RO.",
        )
    raise HTTPException(
        501,
        "OBD connect not wired yet — use `obdscan` CLI for now. "
        f"Will use port={body.port or 'adapter-default'} baud={body.baud or 'adapter-default'}.",
    )


@router.post("/disconnect")
def disconnect() -> dict[str, Any]:
    _session.update(
        {
            "connected": False,
            "port": None,
            "baud": None,
            "protocol": None,
            "vin": None,
        }
    )
    return {"ok": True, "session": dict(_session)}


@router.get("/vehicle")
def vehicle_info() -> dict[str, Any]:
    """Best-effort vehicle context from obdscan caches (no live bus required)."""
    from carro.obd.provider import pull_vehicle_fields

    fields = pull_vehicle_fields()
    if fields:
        cached = _read_json(last_vehicle_file())
        source = "last_vehicle" if isinstance(cached, dict) and cached else "saved_codes"
        return {"source": source, "vehicle": fields}
    return {
        "source": None,
        "vehicle": None,
        "note": "No cached vehicle. Run obdscan save / vehicle info, or wire /obd/connect.",
    }


@router.get("/codes")
def read_codes() -> dict[str, Any]:
    raise HTTPException(501, "Live DTC read not wired yet — use `obdscan codes` or Saved Codes.")


@router.post("/codes/clear")
def clear_codes() -> dict[str, Any]:
    raise HTTPException(501, "Clear codes not wired yet — use `obdscan clear`.")


@router.get("/live")
def live_snapshot(pids: str = "") -> dict[str, Any]:
    _ = [p.strip() for p in pids.split(",") if p.strip()]
    raise HTTPException(501, "Live data not wired yet — use `obdscan live`.")


@router.post("/live")
def live_configure(body: LivePidsBody) -> dict[str, Any]:
    raise HTTPException(
        501,
        f"Live PID configure not wired yet (requested {len(body.pids)} PID(s)).",
    )


@router.get("/saved")
def list_saved() -> dict[str, Any]:
    directory = saved_codes_dir()
    if not directory.is_dir():
        return {"dir": str(directory), "reports": []}
    reports = []
    for path in sorted(directory.glob("dtc_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True):
        reports.append(
            {
                "name": path.name,
                "path": str(path),
                "mtime": path.stat().st_mtime,
                "size": path.stat().st_size,
            }
        )
    return {"dir": str(directory), "reports": reports[:50]}


@router.get("/saved/{name}")
def get_saved(name: str) -> dict[str, Any]:
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(400, "Invalid name")
    path = saved_codes_dir() / name
    if not path.is_file():
        raise HTTPException(404, "Report not found")
    text = path.read_text(encoding="utf-8", errors="replace")
    return {"name": name, "path": str(path), "text": text[:20000]}


@router.post("/save")
def save_codes() -> dict[str, Any]:
    raise HTTPException(501, "Save codes not wired yet — use `obdscan save`.")
