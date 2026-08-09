"""
DoIP / manufacturer-pack routes for the Scanner GUI.

Uses obdscan's doip_session + manufacturers (ethernet path). Does not take the
ELM session.lock — flip the GT327 to ENET/DoIP for these calls.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from obd_engine.session import ensure_obdscan_path, obdscan_root

router = APIRouter(prefix="/obd/doip", tags=["obd-doip"])

_INSTALL_HINT = "pip install doipclient udsoncan  (in the Car-RO / obdscan venv)"


def _import_doip() -> tuple[Any, ...]:
    """Return (HAS_DOIP, discover_vehicles, probe_pack_modules, read_interesting_dids, DoipSession, list_packs, get_pack)."""
    ensure_obdscan_path()
    from doip_session import (  # type: ignore
        HAS_DOIP,
        DoipSession,
        discover_vehicles,
        probe_pack_modules,
        read_interesting_dids,
    )
    from manufacturers import get_pack, list_packs  # type: ignore

    return (
        HAS_DOIP,
        discover_vehicles,
        probe_pack_modules,
        read_interesting_dids,
        DoipSession,
        list_packs,
        get_pack,
    )


def _require_stack() -> tuple[Any, ...]:
    if not obdscan_root():
        raise HTTPException(
            503,
            "obdscan not found. Set OBDSCAN_ROOT or clone obdscan next to Car-RO.",
        )
    try:
        mods = _import_doip()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Failed to import obdscan DoIP stack: {exc}") from exc
    has_doip = mods[0]
    if not has_doip:
        raise HTTPException(
            503,
            f"DoIP stack missing. Install with: {_INSTALL_HINT}",
        )
    return mods


class DiscoverBody(BaseModel):
    timeout: float = Field(default=5.0, ge=1.0, le=30.0)


class ProbeBody(BaseModel):
    pack: str = Field(..., description="Manufacturer pack id")
    ip: str
    max_addresses: int = Field(default=12, ge=1, le=40)


class TargetBody(BaseModel):
    pack: str
    ip: str
    la: str = Field(..., description="Logical address hex, e.g. E0 or 0x00E0")


def _parse_la(raw: str) -> int:
    s = raw.strip().lower().removeprefix("0x")
    try:
        return int(s, 16)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid logical address: {raw}") from exc


def _pack_summary(p: Any) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "maturity": p.maturity,
        "module_count": len(p.modules),
        "did_count": len(p.dids),
        "transports": list(p.transports),
        "ip_hints": list(p.ip_hints),
        "gateway_addresses": [f"{a:#06x}" for a in p.gateway_addresses],
        "default_doip_port": p.default_doip_port,
        "tester_address": f"{p.tester_address:#06x}",
    }


@router.get("/status")
def doip_status() -> dict[str, Any]:
    root = obdscan_root()
    if not root:
        return {
            "ok": False,
            "has_doip": False,
            "obdscan_found": False,
            "obdscan_root": None,
            "hint": "Set OBDSCAN_ROOT or clone obdscan next to Car-RO.",
            "note": "DoIP uses GT327 ENET — separate from ELM Bluetooth (session.lock).",
        }
    try:
        ensure_obdscan_path()
        from doip_session import HAS_DOIP  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "has_doip": False,
            "obdscan_found": True,
            "obdscan_root": str(root),
            "hint": str(exc),
            "note": "DoIP uses GT327 ENET — separate from ELM Bluetooth (session.lock).",
        }
    return {
        "ok": True,
        "has_doip": bool(HAS_DOIP),
        "obdscan_found": True,
        "obdscan_root": str(root),
        "hint": None if HAS_DOIP else _INSTALL_HINT,
        "note": "DoIP uses GT327 ENET — separate from ELM Bluetooth (session.lock).",
    }


@router.get("/packs")
def list_doip_packs() -> dict[str, Any]:
    if not obdscan_root():
        raise HTTPException(503, "obdscan not found. Set OBDSCAN_ROOT.")
    try:
        ensure_obdscan_path()
        from manufacturers import list_packs  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Failed to import manufacturers: {exc}") from exc
    packs = [_pack_summary(p) for p in list_packs()]
    return {"packs": packs}


@router.get("/packs/{pack_id}")
def get_doip_pack(pack_id: str) -> dict[str, Any]:
    if not obdscan_root():
        raise HTTPException(503, "obdscan not found. Set OBDSCAN_ROOT.")
    try:
        ensure_obdscan_path()
        from manufacturers import get_pack  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Failed to import manufacturers: {exc}") from exc
    try:
        pack = get_pack(pack_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        **_pack_summary(pack),
        "modules": [
            {
                "address": f"{m.address:#06x}",
                "name": m.name,
                "addressing": m.addressing,
                "description": m.description,
            }
            for m in pack.modules
        ],
        "dids": [
            {
                "did": d.did_hex,
                "name": d.name,
                "description": d.description,
            }
            for d in pack.dids
        ],
    }


@router.post("/discover")
def doip_discover(body: DiscoverBody | None = None) -> dict[str, Any]:
    _, discover_vehicles, *_rest = _require_stack()
    timeout = body.timeout if body else 5.0
    try:
        vehicles = discover_vehicles(timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Discover failed: {exc}") from exc
    return {
        "vehicles": [
            {
                "ip": v.ip,
                "la": f"{v.logical_address:#06x}",
                "la_int": v.logical_address,
                "vin": v.vin or "",
            }
            for v in vehicles
        ],
        "note": "GT327: flip DoIP/ENET switch ON, car powered, ethernet linked.",
    }


@router.post("/probe")
def doip_probe(body: ProbeBody) -> dict[str, Any]:
    (
        _has,
        _discover,
        probe_pack_modules,
        _dids,
        _DoipSession,
        _list_packs,
        get_pack,
    ) = _require_stack()
    try:
        pack = get_pack(body.pack)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc

    addrs = list(pack.gateway_addresses)
    for m in pack.modules:
        if m.address not in addrs:
            addrs.append(m.address)
        if len(addrs) >= body.max_addresses:
            break
    addrs = addrs[: body.max_addresses]

    try:
        results = probe_pack_modules(
            pack, body.ip, addresses=addrs, timeout_each=1.2
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Probe failed: {exc}") from exc

    rows = [
        {
            "la": f"{la:#06x}",
            "la_int": la,
            "name": name,
            "status": status,
            "alive": status == "alive",
        }
        for la, name, status in results
    ]
    return {
        "pack": pack.id,
        "ip": body.ip,
        "results": rows,
        "alive": [r for r in rows if r["alive"]],
    }


@router.post("/dids")
def doip_read_dids(body: TargetBody) -> dict[str, Any]:
    (
        _has,
        _discover,
        _probe,
        read_interesting_dids,
        DoipSession,
        _list_packs,
        get_pack,
    ) = _require_stack()
    try:
        pack = get_pack(body.pack)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    la = _parse_la(body.la)
    try:
        with DoipSession(
            pack=pack,
            ip=body.ip,
            logical_address=la,
            client_logical_address=pack.tester_address,
            tcp_port=pack.default_doip_port,
        ) as sess:
            session_msg = sess.change_session(3)
            rows = read_interesting_dids(sess, pack.dids)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"DID read failed: {exc}") from exc
    return {
        "pack": pack.id,
        "ip": body.ip,
        "la": f"{la:#06x}",
        "session": session_msg,
        "dids": [{"id": k, "value": v} for k, v in rows],
    }


@router.post("/dtcs")
def doip_read_dtcs(body: TargetBody) -> dict[str, Any]:
    (
        _has,
        _discover,
        _probe,
        _dids,
        DoipSession,
        _list_packs,
        get_pack,
    ) = _require_stack()
    try:
        pack = get_pack(body.pack)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    la = _parse_la(body.la)
    try:
        with DoipSession(
            pack=pack,
            ip=body.ip,
            logical_address=la,
            client_logical_address=pack.tester_address,
            tcp_port=pack.default_doip_port,
        ) as sess:
            sess.change_session(3)
            ok, result = sess.read_dtcs()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"DTC read failed: {exc}") from exc
    if not ok:
        return {
            "ok": False,
            "pack": pack.id,
            "ip": body.ip,
            "la": f"{la:#06x}",
            "error": str(result),
            "codes": [],
        }
    codes = [str(c) for c in (result or [])]
    return {
        "ok": True,
        "pack": pack.id,
        "ip": body.ip,
        "la": f"{la:#06x}",
        "codes": codes,
    }


@router.post("/dtcs/clear")
def doip_clear_dtcs(body: TargetBody) -> dict[str, Any]:
    (
        _has,
        _discover,
        _probe,
        _dids,
        DoipSession,
        _list_packs,
        get_pack,
    ) = _require_stack()
    try:
        pack = get_pack(body.pack)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    la = _parse_la(body.la)
    try:
        with DoipSession(
            pack=pack,
            ip=body.ip,
            logical_address=la,
            client_logical_address=pack.tester_address,
            tcp_port=pack.default_doip_port,
        ) as sess:
            sess.change_session(3)
            ok, msg = sess.clear_dtcs()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"DTC clear failed: {exc}") from exc
    return {
        "ok": ok,
        "pack": pack.id,
        "ip": body.ip,
        "la": f"{la:#06x}",
        "message": msg,
    }
