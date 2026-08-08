"""Pull vehicle / DTC info from obdscan when available."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from carro.vin import make_from_vin, year_from_vin

SAVED_CODES = Path.home() / "Documents" / "Saved Codes"
LAST_VEHICLE = Path.home() / ".cache" / "obdscan" / "last_vehicle.json"


def _which_obdscan() -> str | None:
    return shutil.which("obdscan")


def pull_vehicle_fields() -> dict[str, str]:
    """
    Best-effort autofill dict: year, make, vin, obd_snapshot.
    Tries last_vehicle cache, then newest Saved Codes report, then `obdscan info`.
    """
    out: dict[str, str] = {}

    if LAST_VEHICLE.is_file():
        try:
            import json

            raw = json.loads(LAST_VEHICLE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k in ("VIN", "Year", "Make", "Protocol", "MIL"):
                    if raw.get(k) and str(raw[k]) not in {"—", ""}:
                        key = k.lower() if k != "VIN" else "vin"
                        out[key] = str(raw[k])
                out["obd_snapshot"] = "\n".join(f"{k}: {v}" for k, v in raw.items())
                _enrich_vin(out)
                return out
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    report = _newest_dtc_report()
    if report:
        parsed = _parse_saved_report(report)
        out.update(parsed)
        _enrich_vin(out)
        if out:
            return out

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
            out["obd_snapshot"] = text.strip()[:4000]
            m = re.search(r"\b([A-HJ-NPR-Z0-9]{17})\b", text.upper())
            if m:
                out["vin"] = m.group(1)
            _enrich_vin(out)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return out


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


def _newest_dtc_report() -> Path | None:
    if not SAVED_CODES.is_dir():
        return None
    files = sorted(SAVED_CODES.glob("dtc_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _parse_saved_report(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict[str, str] = {"obd_snapshot": text[:4000]}
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
    return out
