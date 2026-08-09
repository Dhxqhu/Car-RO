"""Pull vehicle / DTC info from obdscan when available."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from carro.obd.paths import last_vehicle_file, saved_codes_dir
from carro.vin import make_from_vin, year_from_vin

# Re-export for callers / engine that historically imported these constants.
SAVED_CODES = saved_codes_dir()
LAST_VEHICLE = last_vehicle_file()

_SNAPSHOT_MAX = 12000  # DTC block can be long; keep enough for PDF/notes


def _which_obdscan() -> str | None:
    return shutil.which("obdscan")


def pull_vehicle_fields(*, prefer_vin: str | None = None) -> dict[str, str]:
    """
    Best-effort autofill dict: year, make, vin, obd_snapshot.

    Priority (newest useful source wins):
      1. last_vehicle.json cache (written by obdscan on vehicle info / save)
      2. Newest matching ``dtc_*.txt`` under Documents/Saved Codes
      3. ``obdscan info`` subprocess (needs a live adapter)

    If ``prefer_vin`` is set (e.g. current RO VIN), prefer a Saved Codes report
    whose filename or body matches that VIN over a newer unrelated car.
    """
    prefer = (prefer_vin or "").strip().upper()
    if prefer and not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", prefer):
        prefer = ""

    candidates: list[tuple[float, str, dict[str, str]]] = []

    cached = _load_last_vehicle()
    if cached:
        mtime, fields = cached
        if not prefer or (fields.get("vin") or "").upper() == prefer:
            candidates.append((mtime, "last_vehicle", fields))

    report = _pick_dtc_report(prefer_vin=prefer or None)
    if report:
        path, mtime = report
        parsed = _parse_saved_report(path)
        if parsed.get("vin") or parsed.get("obd_snapshot"):
            # Prefer VIN-matched report even if slightly older than last_vehicle
            # for a different car.
            score = mtime
            if prefer and (parsed.get("vin") or "").upper() == prefer:
                score += 1e12
            candidates.append((score, f"saved:{path.name}", parsed))

    if candidates:
        candidates.sort(key=lambda t: t[0], reverse=True)
        _src_mtime, _src, out = candidates[0]
        _enrich_vin(out)
        out.setdefault("_source", _src)
        return {k: v for k, v in out.items() if not k.startswith("_")}

    out: dict[str, str] = {}
    exe = _which_obdscan()
    if exe:
        try:
            proc = subprocess.run(
                [exe, "info"],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            text = (proc.stdout or "") + "\n" + (proc.stderr or "")
            snap = text.strip()
            if snap:
                out["obd_snapshot"] = snap[:_SNAPSHOT_MAX]
            m = re.search(r"\b([A-HJ-NPR-Z0-9]{17})\b", text.upper())
            if m:
                out["vin"] = m.group(1)
            _enrich_vin(out)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return out


def _load_last_vehicle() -> tuple[float, dict[str, str]] | None:
    path = last_vehicle_file()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict) or not raw:
        return None

    out: dict[str, str] = {}
    for k in ("VIN", "Year", "Make", "Protocol", "MIL"):
        if raw.get(k) and str(raw[k]) not in {"—", ""}:
            key = "vin" if k == "VIN" else k.lower()
            val = str(raw[k])
            if key == "vin":
                val = val.upper()
            elif key == "make":
                val = val.title()
            out[key] = val
    # Accept already-lowercased keys from future writers
    for k in ("vin", "year", "make"):
        if not out.get(k) and raw.get(k) and str(raw[k]) not in {"—", ""}:
            val = str(raw[k])
            if k == "vin":
                val = val.upper()
            elif k == "make":
                val = val.title()
            out[k] = val

    snap_lines = [f"{k}: {v}" for k, v in raw.items() if k != "saved_at"]
    if snap_lines:
        out["obd_snapshot"] = "\n".join(snap_lines)[:_SNAPSHOT_MAX]

    if not out.get("vin") and not out.get("obd_snapshot"):
        return None

    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    _enrich_vin(out)
    return mtime, out


def _pick_dtc_report(*, prefer_vin: str | None = None) -> tuple[Path, float] | None:
    directory = saved_codes_dir()
    if not directory.is_dir():
        return None
    files = list(directory.glob("dtc_*.txt"))
    if not files:
        return None

    prefer = (prefer_vin or "").strip().upper()

    def sort_key(p: Path) -> tuple[int, float]:
        try:
            mtime = p.stat().st_mtime
        except OSError:
            mtime = 0.0
        vin_hit = 1 if prefer and prefer in p.name.upper() else 0
        return (vin_hit, mtime)

    best = max(files, key=sort_key)
    try:
        mtime = best.stat().st_mtime
    except OSError:
        mtime = 0.0
    # If we preferred a VIN but the winner doesn't match and has no VIN in name,
    # still return newest — body parse may match; caller compares.
    return best, mtime


def _newest_dtc_report() -> Path | None:
    """Back-compat helper (newest report, no VIN preference)."""
    picked = _pick_dtc_report()
    return picked[0] if picked else None


def _enrich_vin(out: dict[str, str]) -> None:
    vin = out.get("vin") or out.get("VIN")
    if not vin:
        return
    out["vin"] = vin.upper()
    if not out.get("year"):
        y = year_from_vin(vin)
        if y:
            out["year"] = str(y)
    if not out.get("make"):
        make, _ = make_from_vin(vin)
        if make:
            out["make"] = make.title()


def _parse_saved_report(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict[str, str] = {"obd_snapshot": text[:_SNAPSHOT_MAX]}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip().lower(), val.strip()
        if key == "vin" and val not in {"—", ""}:
            out["vin"] = val.upper()
        elif key == "year" and val not in {"—", ""}:
            out["year"] = val
        elif key == "make" and val not in {"—", ""}:
            out["make"] = val.title()
    # Filename often embeds VIN when body is incomplete
    if not out.get("vin"):
        m = re.search(r"_([A-HJ-NPR-Z0-9]{17})\.txt$", path.name.upper())
        if m:
            out["vin"] = m.group(1)
    return out
