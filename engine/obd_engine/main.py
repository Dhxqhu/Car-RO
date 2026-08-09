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
from obd_engine import adapter_setup, ops
from obd_engine import session as obd_session
from obd_engine.session import AdapterBusyError

router = APIRouter(prefix="/obd", tags=["obd"])


def _need_elm() -> None:
    try:
        obd_session.require_elm()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


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


class RawBody(BaseModel):
    command: str
    wait: float = Field(default=1.5, ge=0.2, le=10.0)


class AdapterDefaultBody(BaseModel):
    adapter_id: str


class AdapterUpsertBody(BaseModel):
    id: str
    label: str = ""
    port: str = ""
    baud: int = 38400
    transport: str = "serial"
    notes: str = ""
    make_default: bool = False


class AutosetupUsbBody(BaseModel):
    port: str | None = None


class AutosetupBtBody(BaseModel):
    bt_addr: str | None = None
    rfcomm: int = Field(default=0, ge=0, le=9)
    scan_seconds: float = Field(default=8.0, ge=2.0, le=30.0)


class ProfileSelectBody(BaseModel):
    profile_id: str


class ProfileCreateBody(BaseModel):
    id: str
    label: str = ""
    makes: list[str] = Field(default_factory=list)
    notes: str = ""
    activate: bool = True


class ProfilePidBody(BaseModel):
    name: str
    pid: str
    unit: str = ""
    formula: str = "raw"
    mult: float = 1.0
    offset: float = 0.0
    wide: bool = False
    note: str = ""


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
        "note": "Shared with obdscan CLI (~/.config/obdscan/adapters.json).",
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
        "note": "No cached vehicle. Connect and Refresh live, or run obdscan save.",
    }


@router.post("/vehicle/live")
def vehicle_live() -> dict[str, Any]:
    _need_elm()
    try:
        result = ops.collect_vehicle_info()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Vehicle info failed: {exc}") from exc
    return {"source": "live", "vehicle": result["fields"], "raw": result["vehicle"]}


@router.get("/codes")
def read_codes(force: bool = False) -> dict[str, Any]:
    _need_elm()
    try:
        return ops.read_codes(force=force)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Read codes failed: {exc}") from exc


@router.post("/codes/clear")
def clear_codes() -> dict[str, Any]:
    _need_elm()
    try:
        return ops.clear_codes()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Clear codes failed: {exc}") from exc


@router.get("/lookup")
def lookup(codes: str = "") -> dict[str, Any]:
    import re

    # Join "P 0420" → "P0420" before splitting on whitespace/commas
    cleaned = re.sub(r"([PBCUpbcu])\s+(\d{4}\b)", r"\1\2", codes.strip())
    parts = [p.strip() for p in re.split(r"[\s,;]+", cleaned) if p.strip()]
    if not parts:
        raise HTTPException(400, "Pass codes=P0420,P0301")
    try:
        return ops.lookup_codes(parts)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Lookup failed: {exc}") from exc


@router.get("/live")
def live_snapshot(pids: str = "") -> dict[str, Any]:
    _need_elm()
    names = [p.strip() for p in pids.split(",") if p.strip()] or None
    try:
        return ops.live_snapshot(names)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Live snapshot failed: {exc}") from exc


@router.post("/live")
def live_configure(body: LivePidsBody) -> dict[str, Any]:
    try:
        return ops.configure_live(body.pids)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@router.get("/pids")
def list_pids() -> dict[str, Any]:
    try:
        return {
            "pids": ops.catalog_list(),
            "selected": obd_session.get_live_pids(),
            "active_profile": obd_session.profile_store().active_id,
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, str(exc)) from exc


@router.get("/readiness")
def get_readiness() -> dict[str, Any]:
    _need_elm()
    try:
        return ops.readiness()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Readiness failed: {exc}") from exc


@router.get("/freeze")
def get_freeze() -> dict[str, Any]:
    _need_elm()
    try:
        return ops.freeze_frame()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Freeze frame failed: {exc}") from exc


@router.get("/raw/help")
def raw_help() -> dict[str, Any]:
    try:
        return ops.raw_help()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, str(exc)) from exc


@router.post("/raw")
def raw_cmd(body: RawBody) -> dict[str, Any]:
    _need_elm()
    try:
        return ops.raw_command(body.command, wait=body.wait)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Raw command failed: {exc}") from exc


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
def save_codes(force: bool = False) -> dict[str, Any]:
    _need_elm()
    try:
        return ops.save_codes_report(force=force)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Save failed: {exc}") from exc


@router.put("/adapters/default")
def set_default_adapter(body: AdapterDefaultBody) -> dict[str, Any]:
    obd_session.ensure_obdscan_path()
    from adapters import load_store, save_store  # type: ignore

    store = load_store()
    adapters = store.get("adapters") or {}
    if body.adapter_id not in adapters:
        raise HTTPException(404, f"Unknown adapter id: {body.adapter_id}")
    store["default"] = body.adapter_id
    path = save_store(store)
    return {"ok": True, "default_id": body.adapter_id, "path": str(path)}


@router.post("/adapters")
def upsert_adapter(body: AdapterUpsertBody) -> dict[str, Any]:
    obd_session.ensure_obdscan_path()
    from adapters import load_store, save_store  # type: ignore

    store = load_store()
    adapters = store.setdefault("adapters", {})
    aid = body.id.strip()
    if not aid:
        raise HTTPException(400, "id required")
    adapters[aid] = {
        "label": body.label or aid,
        "port": body.port,
        "baud": int(body.baud),
        "transport": body.transport or "serial",
        "notes": body.notes or "",
    }
    if body.make_default or not store.get("default"):
        store["default"] = aid
    path = save_store(store)
    return {"ok": True, "id": aid, "path": str(path), "default_id": store.get("default")}


@router.get("/adapters/discover")
def discover_adapters() -> dict[str, Any]:
    try:
        return adapter_setup.discover()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Discover failed: {exc}") from exc


@router.post("/adapters/autosetup/usb")
def autosetup_usb(body: AutosetupUsbBody | None = None) -> dict[str, Any]:
    try:
        result = adapter_setup.autosetup_usb(port=(body.port if body else None))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"USB autosetup failed: {exc}") from exc
    if not result.get("ok"):
        raise HTTPException(404, result.get("error") or "USB autosetup failed")
    return result


@router.post("/adapters/autosetup/bluetooth")
def autosetup_bluetooth(body: AutosetupBtBody | None = None) -> dict[str, Any]:
    body = body or AutosetupBtBody()
    try:
        result = adapter_setup.autosetup_bluetooth(
            bt_addr=body.bt_addr,
            rfcomm=body.rfcomm,
            scan_seconds=body.scan_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Bluetooth autosetup failed: {exc}") from exc
    # Partial success (profile saved, ELM not seen) still 200 with ok flag
    if not result.get("ok") and not result.get("adapter_id"):
        raise HTTPException(404, result.get("error") or "Bluetooth autosetup failed")
    return result


@router.get("/profiles")
def list_profiles() -> dict[str, Any]:
    try:
        store = obd_session.profile_store()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, str(exc)) from exc
    summaries = [
        {
            "id": pid,
            "label": label,
            "pid_count": count,
            "makes": makes,
            "years": years,
            "active": pid == store.active_id,
        }
        for pid, label, count, makes, years in store.list_summaries()
    ]
    return {
        "path": str(store.path),
        "active_id": store.active_id,
        "profiles": summaries,
    }


@router.post("/profiles/select")
def select_profile(body: ProfileSelectBody) -> dict[str, Any]:
    store = obd_session.profile_store()
    if not store.select(body.profile_id):
        raise HTTPException(404, f"Unknown profile: {body.profile_id}")
    return {"ok": True, "active_id": store.active_id}


@router.post("/profiles")
def create_profile(body: ProfileCreateBody) -> dict[str, Any]:
    store = obd_session.profile_store()
    try:
        prof = store.create(
            body.id,
            label=body.label,
            makes=body.makes or None,
            notes=body.notes,
            activate=body.activate,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "profile": {"id": prof["id"], "label": prof["label"]}}


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: str) -> dict[str, Any]:
    store = obd_session.profile_store()
    if not store.delete(profile_id):
        raise HTTPException(404, f"Unknown profile: {profile_id}")
    return {"ok": True, "active_id": store.active_id}


@router.get("/profiles/active/pids")
def active_profile_pids() -> dict[str, Any]:
    store = obd_session.profile_store()
    return {
        "active_id": store.active_id,
        "pids": store.pids,
    }


@router.put("/profiles/active/pids")
def set_active_pid(body: ProfilePidBody) -> dict[str, Any]:
    store = obd_session.profile_store()
    pid_hex = body.pid.strip().upper().removeprefix("0X")
    if len(pid_hex) != 2:
        raise HTTPException(400, "pid must be a 2-digit hex Mode 01 ID (e.g. 0C for RPM)")
    try:
        store.set_pid(
            body.name,
            {
                "pid": pid_hex,
                "unit": body.unit,
                "formula": body.formula,
                "mult": body.mult,
                "offset": body.offset,
                "wide": body.wide,
                "note": body.note,
            },
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "active_id": store.active_id, "pids": store.pids}


@router.delete("/profiles/active/pids/{name}")
def remove_active_pid(name: str) -> dict[str, Any]:
    store = obd_session.profile_store()
    if not store.remove_pid(name):
        raise HTTPException(404, f"PID not found: {name}")
    return {"ok": True, "active_id": store.active_id, "pids": store.pids}
