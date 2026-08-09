"""
FastAPI routes that drive obdscan from the desktop GUI.

Filesystem handoff paths come from ``carro.obd.paths`` — same as CLI pull.
Live bus ownership is ``obd_engine.session`` + shared ``session.lock``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from carro.obd.paths import adapters_file, last_vehicle_file, saved_codes_dir
from carro.obd.session_lock import lock_status
from obd_engine import session as obd_session
from obd_engine.session import AdapterBusyError

router = APIRouter(prefix="/obd", tags=["obd"])


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
    extras = obd_session.health_extras()
    lv = last_vehicle_file()
    sc = saved_codes_dir()
    return {
        "ok": True,
        **extras,
        "paths": {
            "saved_codes": str(sc),
            "last_vehicle": str(lv),
            "adapters": str(adapters_file()),
            "last_vehicle_exists": lv.is_file(),
            "saved_codes_exists": sc.is_dir(),
            "session_lock": extras.get("lock", {}).get("path"),
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
        "note": "Read-only list — edit via obdscan CLI Config for now.",
    }


@router.get("/session")
def get_session() -> dict[str, Any]:
    return {"session": obd_session.public_session(), "lock": lock_status()}


@router.post("/connect")
def connect(body: ConnectBody) -> dict[str, Any]:
    try:
        sess = obd_session.connect(
            port=body.port,
            baud=body.baud,
            adapter_id=body.adapter_id,
        )
    except AdapterBusyError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ConnectionError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:  # serial / import issues
        raise HTTPException(502, f"Connect failed: {exc}") from exc
    return {"session": sess, "lock": lock_status()}


@router.post("/disconnect")
def disconnect() -> dict[str, Any]:
    sess = obd_session.disconnect()
    return {"ok": True, "session": sess, "lock": lock_status()}


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
        "note": "No cached vehicle. Run obdscan save / vehicle info, or connect.",
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
