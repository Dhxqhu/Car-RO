"""
ELM bus operations for the Scanner GUI — mirrors obdscan CLI modules.

Uses the process-wide ElmSession from ``obd_engine.session``.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from carro.obd.paths import last_vehicle_file, saved_codes_dir
from obd_engine import session as obd_session


def _elm():
    return obd_session.require_elm()


def _load_obdscan_constants() -> Any:
    """Load PID_CATALOG / RAW_* from obdscan.py without running the CLI."""
    import sys
    import types

    obd_session.ensure_obdscan_path()
    mod_name = "_carro_obdscan_catalog"
    if mod_name in sys.modules:
        return sys.modules[mod_name]

    root = obd_session.ensure_obdscan_path()
    src = (root / "obdscan.py").read_text(encoding="utf-8")
    cut = src.find("\ndef main(")
    if cut < 0:
        cut = src.find("\nif __name__")
    chunk = src[:cut] if cut > 0 else src
    mod = types.ModuleType(mod_name)
    mod.__file__ = str(root / "obdscan.py")
    exec(compile(chunk, str(root / "obdscan.py"), "exec"), mod.__dict__)  # noqa: S102
    sys.modules[mod_name] = mod
    return mod


def _catalog() -> dict[str, tuple[str, str, Callable]]:
    obd_session.ensure_obdscan_path()
    from custom_pids import customs_to_catalog  # type: ignore

    mod = _load_obdscan_constants()
    base = dict(mod.PID_CATALOG)
    store = obd_session.profile_store()
    base.update(customs_to_catalog(store.pids))
    return base


def catalog_list() -> list[dict[str, Any]]:
    cat = _catalog()
    store = obd_session.profile_store()
    customs = set(store.pids)
    rows = []
    for name, (pid, unit, _fmt) in sorted(cat.items(), key=lambda kv: (kv[1][0], kv[0])):
        rows.append(
            {
                "name": name,
                "pid": pid,
                "unit": unit,
                "custom": name in customs,
            }
        )
    return rows


def read_codes(*, force: bool = False) -> dict[str, Any]:
    from elm import parse_dtc_response  # type: ignore

    elm = _elm()
    info = getattr(elm, "info", None)
    ecu_alive = bool(getattr(info, "ecu_alive", True)) if info else True
    if not ecu_alive and not force:
        return {
            "ok": False,
            "ecu_alive": False,
            "codes": [],
            "note": "No ECU detected. Retry with force=true to query anyway.",
        }

    db = obd_session.dtc_db()
    from dtc_db import lookup_code  # type: ignore

    rows: list[dict[str, str]] = []
    for label, cmd in (("Stored", "03"), ("Pending", "07"), ("Permanent", "0A")):
        resp = elm.cmd(cmd, wait=2.0)
        if any(x in resp.upper() for x in ("NO DATA", "UNABLE", "ERROR")):
            continue
        for code in parse_dtc_response(resp):
            rows.append(
                {
                    "type": label,
                    "code": code,
                    "description": lookup_code(db, code),
                }
            )
    return {"ok": True, "ecu_alive": ecu_alive, "codes": rows}


def clear_codes() -> dict[str, Any]:
    elm = _elm()
    resp = elm.cmd("04", wait=2.0)
    cleaned = re.sub(r"\s", "", resp.upper())
    ok = "OK" in resp.upper() or "44" in cleaned
    return {"ok": ok, "response": resp.strip()}


def _normalize_dtc_token(raw: str) -> str:
    """Accept P0420, p0420, P 0420, or bare 0420 → P0420."""
    s = re.sub(r"[\s_\-]+", "", raw.strip().upper())
    if not s:
        return ""
    if re.fullmatch(r"[0-9A-F]{4}", s):
        s = "P" + s
    return s


def lookup_codes(codes: list[str]) -> dict[str, Any]:
    obd_session.ensure_obdscan_path()
    from dtc_db import lookup_code  # type: ignore

    db = obd_session.dtc_db()
    results = []
    for raw in codes:
        code = _normalize_dtc_token(raw)
        if not code:
            continue
        desc = lookup_code(db, code)
        results.append(
            {
                "code": code,
                "description": desc,
                "found": code in db,
            }
        )
    return {"results": results, "db_size": len(db)}


def live_snapshot(pids: list[str] | None = None) -> dict[str, Any]:
    from elm import parse_mode01  # type: ignore

    elm = _elm()
    cat = _catalog()
    names = pids or obd_session.get_live_pids()
    values: dict[str, Any] = {}
    for name in names:
        key = name.strip().upper()
        if key not in cat:
            values[key] = {"value": None, "unit": "", "error": "unknown PID name"}
            continue
        pid, unit, fmt = cat[key]
        resp = elm.cmd(f"01{pid}", wait=1.0)
        data = parse_mode01(resp, pid)
        if not data:
            values[key] = {"value": None, "unit": unit, "raw": resp.strip()}
        else:
            text = fmt(data)
            values[key] = {"value": text, "unit": unit}
    return {"pids": names, "values": values}


def configure_live(pids: list[str]) -> dict[str, Any]:
    cat = _catalog()
    unknown = [p.upper() for p in pids if p.strip().upper() not in cat]
    selected = obd_session.set_live_pids(pids)
    return {"pids": selected, "unknown": unknown}


def readiness() -> dict[str, Any]:
    from elm import parse_mode01  # type: ignore

    elm = _elm()
    resp = elm.cmd("0101", wait=1.5)
    data = parse_mode01(resp, "01")
    if not data or len(data) < 4:
        return {"ok": False, "raw": resp.strip(), "monitors": []}
    a, b, c, d = data[0], data[1], data[2], data[3]
    mil_on = bool(a & 0x80)
    dtc_count = a & 0x7F
    spark = not bool(b & 0x08)
    monitors: list[dict[str, str]] = []

    def status(available: bool, incomplete: bool) -> str:
        if not available:
            return "n/a"
        return "incomplete" if incomplete else "ready"

    for name, available, incomplete in (
        ("Misfire", bool(b & 0x01), bool(b & 0x10)),
        ("Fuel system", bool(b & 0x02), bool(b & 0x20)),
        ("Components", bool(b & 0x04), bool(b & 0x40)),
    ):
        monitors.append({"name": name, "status": status(available, incomplete)})
    for name, bit in (
        ("Catalyst", 0x01),
        ("Heated catalyst", 0x02),
        ("Evaporative system", 0x04),
        ("Secondary air", 0x08),
        ("A/C refrigerant", 0x10),
        ("Oxygen sensor", 0x20),
        ("Oxygen sensor heater", 0x40),
        ("EGR system", 0x80),
    ):
        monitors.append(
            {"name": name, "status": status(bool(c & bit), bool(d & bit))}
        )
    return {
        "ok": True,
        "raw": resp.strip(),
        "mil": mil_on,
        "dtc_count": dtc_count,
        "ignition": "spark" if spark else "compression",
        "monitors": monitors,
    }


def freeze_frame() -> dict[str, Any]:
    from elm import parse_mode01  # type: ignore

    elm = _elm()
    cat = _catalog()
    dtc_raw = elm.cmd("0202", wait=1.5)
    samples = []
    for name in ("RPM", "SPEED", "COOLANT", "LOAD", "THROTTLE"):
        if name not in cat:
            continue
        pid, _unit, fmt = cat[name]
        raw = elm.cmd(f"02{pid}00", wait=1.0)
        hexes = [h.upper() for h in re.findall(r"[0-9A-Fa-f]{2}", raw)]
        val = "—"
        for i in range(len(hexes) - 3):
            if hexes[i] == "42" and hexes[i + 1] == pid.upper():
                data = [int(h, 16) for h in hexes[i + 2 : i + 6]]
                if data and data[0] == 0 and len(hexes) > i + 3:
                    data = [int(h, 16) for h in hexes[i + 3 : i + 7]]
                try:
                    val = fmt(data)
                except Exception:
                    # Mode 02 sometimes needs mode01-style parse fallback
                    m01 = parse_mode01(raw.replace("42", "41", 1), pid)
                    val = fmt(m01) if m01 else "—"
                break
        samples.append({"name": name, "pid": pid, "value": val})
    return {"dtc_raw": dtc_raw.strip(), "frame": "00", "samples": samples}


def raw_command(command: str, *, wait: float = 1.5) -> dict[str, Any]:
    elm = _elm()
    cmd = command.strip()
    if not cmd:
        raise ValueError("Empty command")
    resp = elm.cmd(cmd, wait=wait)
    return {"command": cmd, "response": resp.strip()}


def raw_help() -> dict[str, Any]:
    mod = _load_obdscan_constants()
    at = list(getattr(mod, "RAW_AT_COMMANDS", []))
    obd = list(getattr(mod, "RAW_OBD_COMMANDS", []))
    pid_cmds = [
        {"command": f"01{row['pid']}", "description": f"{row['name']} ({row['unit']})"}
        for row in catalog_list()[:80]
    ]
    return {
        "at": [{"command": c, "description": d} for c, d in at],
        "obd": [{"command": c, "description": d} for c, d in obd],
        "pids": pid_cmds,
    }


def _read_vin(elm: Any) -> str | None:
    resp = elm.cmd("0902", wait=2.5)
    ascii_chars = []
    for h in re.findall(r"[0-9A-Fa-f]{2}", resp):
        v = int(h, 16)
        if 32 <= v < 127:
            ascii_chars.append(chr(v))
    vin = "".join(ascii_chars)
    m = re.search(r"[A-HJ-NPR-Z0-9]{17}", vin.upper())
    return m.group(0) if m else (vin.strip() or None)


def _read_mil(elm: Any) -> str | None:
    from elm import parse_mode01  # type: ignore

    resp = elm.cmd("0101", wait=1.2)
    data = parse_mode01(resp, "01")
    if not data:
        return None
    mil = "ON" if data[0] & 0x80 else "OFF"
    return f"{mil} ({data[0] & 0x7F} codes)"


def _persist_last_vehicle(info: dict[str, str]) -> None:
    path = last_vehicle_file()
    # Also write obdscan cache path for CLI compatibility
    try:
        obd_session.ensure_obdscan_path()
        from pathlib import Path as P

        cli_path = P.home() / ".cache" / "obdscan" / "last_vehicle.json"
        for dest in {path, cli_path}:
            dest.parent.mkdir(parents=True, exist_ok=True)
            payload = dict(info)
            payload["saved_at"] = datetime.now().isoformat(timespec="seconds")
            tmp = dest.with_suffix(".json.tmp")
            tmp.write_text(
                __import__("json").dumps(payload, indent=2) + "\n", encoding="utf-8"
            )
            tmp.replace(dest)
    except OSError:
        pass


def collect_vehicle_info() -> dict[str, Any]:
    from elm import parse_mode01  # type: ignore

    elm = _elm()
    cat = _catalog()
    out: dict[str, str] = {}
    vin = _read_vin(elm)
    out["VIN"] = vin or "—"
    if vin:
        obd_session.set_vin(vin)
        from custom_pids import make_guess_from_vin, model_year_from_vin  # type: ignore

        year = model_year_from_vin(vin)
        if year is not None:
            out["Year"] = str(year)
        make, wmi = make_guess_from_vin(vin)
        if make:
            out["Make"] = make
        if wmi:
            out["WMI"] = wmi
    mil = _read_mil(elm)
    out["MIL"] = mil or "—"
    for label, name, unit in (
        ("Battery (PID 42)", "CTRL_MOD_V", "V"),
        ("Fuel level", "FUEL_LEVEL", "%"),
        ("Runtime", "RUNTIME", "s"),
    ):
        if name not in cat:
            out[label] = "—"
            continue
        pid, _u, fmt = cat[name]
        resp = elm.cmd(f"01{pid}", wait=1.0)
        data = parse_mode01(resp, pid)
        val = fmt(data) if data else "—"
        out[label] = f"{val} {unit}" if val != "—" else "—"
    for atcmd, label in (("ATI", "Adapter"), ("ATRV", "Voltage"), ("ATDP", "Protocol")):
        resp = elm.cmd(atcmd, wait=0.5)
        line = next(
            (
                ln.strip()
                for ln in resp.splitlines()
                if ln.strip() and ln.strip().upper() not in {atcmd, "OK", ">"}
            ),
            "—",
        )
        out[label] = line
    info = getattr(elm, "info", None)
    if info:
        out["ELM"] = getattr(info, "version", None) or "—"
        if getattr(info, "voltage", None) and out.get("Voltage") in (None, "—"):
            out["Voltage"] = info.voltage
        if getattr(info, "protocol", None) and out.get("Protocol") in (None, "—"):
            out["Protocol"] = info.protocol
    out["Port"] = str(obd_session.public_session().get("port") or "—")
    store = obd_session.profile_store()
    if store.active_id:
        out["Profile"] = store.active_id
    _persist_last_vehicle(out)
    # Flatten for GUI: also lowercase keys
    fields = {
        "vin": out.get("VIN", ""),
        "year": out.get("Year", ""),
        "make": out.get("Make", ""),
        "obd_snapshot": "\n".join(f"{k}: {v}" for k, v in out.items()),
    }
    return {"vehicle": out, "fields": {k: v for k, v in fields.items() if v and v != "—"}}


def save_codes_report(*, force: bool = False) -> dict[str, Any]:
    from dtc_db import lookup_code  # type: ignore

    codes_result = read_codes(force=force)
    if not codes_result.get("ok") and not force:
        return {
            "ok": False,
            "path": None,
            "note": codes_result.get("note") or "Could not read codes",
            "codes": codes_result.get("codes") or [],
        }
    rows = [(c["type"], c["code"]) for c in codes_result.get("codes") or []]
    vehicle_wrap = collect_vehicle_info()
    vehicle = vehicle_wrap["vehicle"]
    db = obd_session.dtc_db()

    saved_dir = saved_codes_dir()
    saved_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    vin = vehicle.get("VIN", "—")
    vin_part = ""
    if vin and vin != "—" and re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin.upper()):
        vin_part = f"_{vin.upper()}"
    path = saved_dir / f"dtc_{stamp}{vin_part}.txt"

    lines: list[str] = [
        "obdscan — saved DTC report",
        f"Saved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "=== Vehicle ===",
    ]
    for label, value in vehicle.items():
        lines.append(f"{label}: {value}")
    lines.extend(["", "=== Diagnostic Trouble Codes ==="])
    if not rows:
        lines.append("(none reported)")
    else:
        lines.append(f"{'Type':<12} {'Code':<8} Description")
        lines.append("-" * 72)
        for bucket, code in rows:
            lines.append(f"{bucket:<12} {code:<8} {lookup_code(db, code)}")
        lines.append("")
        lines.append(f"Total: {len(rows)} code(s)")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "path": str(path),
        "codes": codes_result.get("codes") or [],
        "vehicle": vehicle,
    }
