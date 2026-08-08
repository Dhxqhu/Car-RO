"""VIN helpers (make / model year) — aligned with obdscan conventions."""

from __future__ import annotations

from datetime import datetime

WMI_TO_MAKE: dict[str, str] = {
    "1FA": "ford", "1FB": "ford", "1FC": "ford", "1FD": "ford", "1FT": "ford",
    "1FM": "ford", "1ZV": "ford", "2FA": "ford", "2FM": "ford", "2FT": "ford",
    "3FA": "ford", "3FM": "ford",
    "1G1": "chevy", "1G6": "cadillac", "1GC": "chevy", "1GT": "gmc",
    "2G1": "chevy", "3G1": "chevy", "1GN": "chevy",
    "1C3": "chrysler", "1C4": "chrysler", "1C6": "ram", "2C3": "chrysler",
    "1J4": "jeep", "1J8": "jeep",
    "1N4": "nissan", "1N6": "nissan", "3N1": "nissan", "JN1": "nissan",
    "4T1": "toyota", "4T3": "toyota", "5TD": "toyota", "JTD": "toyota",
    "2T1": "toyota", "5TF": "toyota", "5TE": "toyota",
    "1HG": "honda", "2HG": "honda", "19X": "honda", "JHM": "honda",
    "5FN": "honda", "SHH": "honda",
    "KM8": "hyundai", "KMH": "hyundai", "5NP": "hyundai",
    "KND": "kia", "5XY": "kia",
    "WBA": "bmw", "WBS": "bmw", "5UX": "bmw", "5YM": "bmw",
    "WDD": "mercedes", "WDC": "mercedes", "4JG": "mercedes",
    "WAU": "audi", "WA1": "audi", "TRU": "audi",
    "WVW": "vw", "3VW": "vw", "1VW": "vw",
    "JF1": "subaru", "JF2": "subaru", "4S3": "subaru", "4S4": "subaru",
    "JM1": "mazda", "JM3": "mazda", "3MZ": "mazda",
}

_VIN_YEAR_CODES = "ABCDEFGHJKLMNPRSTVWXY123456789"


def make_from_vin(vin: str | None) -> tuple[str | None, str | None]:
    if not vin or len(vin) < 3:
        return None, None
    wmi = vin[:3].upper()
    return WMI_TO_MAKE.get(wmi), wmi


def year_from_vin(vin: str | None, *, now_year: int | None = None) -> int | None:
    if not vin or len(vin) < 10:
        return None
    code = vin[9].upper()
    idx = _VIN_YEAR_CODES.find(code)
    if idx < 0:
        return None
    ref = now_year if now_year is not None else datetime.now().year
    candidates = [1980 + idx, 2010 + idx, 2040 + idx]
    return min(candidates, key=lambda y: (abs(y - ref), -y))
