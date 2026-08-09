"""Handoff contract: Saved Codes / last_vehicle → RO autofill fields."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from carro.obd import provider
from carro.obd import paths as obd_paths

# Known WMI samples used across bay tooling
FORD_VIN = "3FMCR9C62PRE34322"  # → Ford, 2023
HONDA_VIN = "1HGCM82633A004352"  # → Honda


@pytest.fixture()
def handoff_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    docs = tmp_path / "Documents"
    saved = docs / "Saved Codes"
    cache = tmp_path / "cache" / "obdscan"
    saved.mkdir(parents=True)
    cache.mkdir(parents=True)
    last = cache / "last_vehicle.json"

    monkeypatch.setenv("XDG_DOCUMENTS_DIR", str(docs))
    monkeypatch.setattr(obd_paths, "last_vehicle_file", lambda: last)
    monkeypatch.setattr(provider, "last_vehicle_file", lambda: last)
    monkeypatch.setattr(provider, "saved_codes_dir", lambda: saved)
    # Block live CLI fallback in unit tests
    monkeypatch.setattr(provider, "_which_obdscan", lambda: None)

    return {"docs": docs, "saved": saved, "last": last}


def _write_report(
    saved: Path,
    *,
    name: str,
    vin: str,
    year: str | None = None,
    make: str | None = None,
    mtime: float | None = None,
) -> Path:
    lines = [
        "obdscan — saved DTC report",
        "",
        "=== Vehicle ===",
        f"VIN: {vin}",
    ]
    if year:
        lines.append(f"Year: {year}")
    if make:
        lines.append(f"Make: {make}")
    lines.extend(["", "=== Diagnostic Trouble Codes ===", "(none reported)", ""])
    path = saved / name
    path.write_text("\n".join(lines), encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_saved_codes_only_enriches_vin(handoff_dirs):
    saved = handoff_dirs["saved"]
    _write_report(
        saved,
        name=f"dtc_20260101_120000_{FORD_VIN}.txt",
        vin=FORD_VIN,
        # intentionally omit Year/Make — enrich from VIN
    )
    out = provider.pull_vehicle_fields()
    assert out["vin"] == FORD_VIN
    assert out["year"] == "2023"
    assert out["make"] == "Ford"
    assert "VIN:" in out["obd_snapshot"]


def test_empty_last_vehicle_falls_through(handoff_dirs):
    saved = handoff_dirs["saved"]
    last = handoff_dirs["last"]
    last.write_text("{}", encoding="utf-8")
    _write_report(
        saved,
        name=f"dtc_20260101_120000_{FORD_VIN}.txt",
        vin=FORD_VIN,
        year="2023",
        make="Ford",
    )
    out = provider.pull_vehicle_fields()
    assert out["vin"] == FORD_VIN
    assert out["make"] == "Ford"


def test_corrupt_last_vehicle_falls_through(handoff_dirs):
    saved = handoff_dirs["saved"]
    last = handoff_dirs["last"]
    last.write_text("{not-json", encoding="utf-8")
    _write_report(
        saved,
        name=f"dtc_20260101_120000_{FORD_VIN}.txt",
        vin=FORD_VIN,
    )
    out = provider.pull_vehicle_fields()
    assert out["vin"] == FORD_VIN


def test_prefer_vin_beats_newer_unrelated_last_vehicle(handoff_dirs):
    saved = handoff_dirs["saved"]
    last = handoff_dirs["last"]
    now = time.time()

    _write_report(
        saved,
        name=f"dtc_20260101_100000_{FORD_VIN}.txt",
        vin=FORD_VIN,
        year="2023",
        make="Ford",
        mtime=now - 100,
    )
    last.write_text(
        json.dumps(
            {
                "VIN": HONDA_VIN,
                "Year": "2003",
                "Make": "honda",
                "Protocol": "TEST",
            }
        ),
        encoding="utf-8",
    )
    os.utime(last, (now + 100, now + 100))

    wrong = provider.pull_vehicle_fields()
    assert wrong["vin"] == HONDA_VIN
    assert wrong["make"] == "Honda"

    pref = provider.pull_vehicle_fields(prefer_vin=FORD_VIN)
    assert pref["vin"] == FORD_VIN
    assert pref["make"] == "Ford"
    assert pref["year"] == "2023"


def test_filename_vin_when_body_incomplete(handoff_dirs):
    saved = handoff_dirs["saved"]
    path = saved / f"dtc_20260101_120000_{FORD_VIN}.txt"
    path.write_text("obdscan — saved DTC report\n=== Vehicle ===\nMIL: OFF\n", encoding="utf-8")
    out = provider.pull_vehicle_fields()
    assert out["vin"] == FORD_VIN
    assert out["make"] == "Ford"


def test_documents_dir_honors_xdg(handoff_dirs, monkeypatch):
    docs = handoff_dirs["docs"]
    monkeypatch.setenv("XDG_DOCUMENTS_DIR", str(docs))
    assert obd_paths.documents_dir() == docs
    assert obd_paths.saved_codes_dir() == docs / "Saved Codes"


def test_nothing_found_returns_empty(handoff_dirs):
    assert provider.pull_vehicle_fields() == {}
