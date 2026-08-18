"""Shop part supersession catalog — old PN linked to the current number."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from carro.config import CONFIG_DIR
from carro.core.models import now_iso

SUPERSESSIONS_FILE = CONFIG_DIR / "part_supersessions.json"


def empty_roster() -> dict[str, Any]:
    return {"version": 1, "updated": "", "links": []}


def normalize_pn(raw: object) -> str:
    """Uppercase, collapse spaces; keep hyphens/slashes used on real PNs."""
    return re.sub(r"\s+", "", str(raw or "").strip()).upper()


def load_roster() -> dict[str, Any]:
    if not SUPERSESSIONS_FILE.is_file():
        return empty_roster()
    try:
        raw = json.loads(SUPERSESSIONS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_roster()
    if not isinstance(raw, dict):
        return empty_roster()
    links = raw.get("links")
    if not isinstance(links, list):
        links = []
    cleaned: list[dict[str, str]] = []
    seen_old: set[str] = set()
    for entry in links:
        if not isinstance(entry, dict):
            continue
        row = _clean_link(entry, existing=cleaned)
        if not row:
            continue
        key = normalize_pn(row["old_number"])
        if key in seen_old:
            continue
        seen_old.add(key)
        cleaned.append(row)
    return {
        "version": int(raw.get("version") or 1),
        "updated": str(raw.get("updated") or ""),
        "links": cleaned,
    }


def save_roster(roster: dict[str, Any]) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cleaned: list[dict[str, str]] = []
    seen_old: set[str] = set()
    for entry in roster.get("links") or []:
        if not isinstance(entry, dict):
            continue
        row = _clean_link(entry, existing=cleaned)
        if not row:
            continue
        key = normalize_pn(row["old_number"])
        if key in seen_old:
            continue
        seen_old.add(key)
        cleaned.append(row)
    payload = {
        "version": int(roster.get("version") or 1),
        "updated": str(roster.get("updated") or now_iso()),
        "links": cleaned,
    }
    SUPERSESSIONS_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return SUPERSESSIONS_FILE


def roster_for_sync() -> dict[str, Any]:
    return load_roster()


def list_links() -> list[dict[str, str]]:
    return list(load_roster().get("links") or [])


def _new_id(existing: list[dict[str, str]]) -> str:
    n = 1
    used = {str(s.get("id") or "").lower() for s in existing}
    while True:
        cand = f"ss-{n:03d}"
        if cand not in used:
            return cand
        n += 1


def _clean_link(entry: dict[str, Any], *, existing: list[dict[str, str]]) -> dict[str, str] | None:
    old = normalize_pn(entry.get("old_number"))
    new = normalize_pn(entry.get("new_number"))
    if not old or not new or old == new:
        return None
    sid = str(entry.get("id") or "").strip()
    if not sid:
        sid = _new_id(existing)
    return {
        "id": sid,
        "old_number": old,
        "new_number": new,
        "name": f"{old}→{new}",
        "manufacturer": str(entry.get("manufacturer") or "").strip(),
        "note": str(entry.get("note") or "").strip(),
        "updated": str(entry.get("updated") or "").strip(),
    }


def upsert_link(
    old_number: str,
    new_number: str,
    *,
    manufacturer: str = "",
    note: str = "",
) -> dict[str, str]:
    old = normalize_pn(old_number)
    new = normalize_pn(new_number)
    if not old:
        raise ValueError("Old part number required")
    if not new:
        raise ValueError("Replacement part number required")
    if old == new:
        raise ValueError("Replacement must be a different number")
    roster = load_roster()
    links = list(roster.get("links") or [])
    ts = now_iso()
    for row in links:
        if normalize_pn(row.get("old_number")) == old:
            row["new_number"] = new
            row["name"] = f"{old}→{new}"
            if manufacturer.strip():
                row["manufacturer"] = manufacturer.strip()
            if note.strip():
                row["note"] = note.strip()
            row["updated"] = ts
            roster["links"] = links
            roster["updated"] = ts
            save_roster(roster)
            return row
    entry = {
        "id": _new_id(links),
        "old_number": old,
        "new_number": new,
        "name": f"{old}→{new}",
        "manufacturer": manufacturer.strip(),
        "note": note.strip(),
        "updated": ts,
    }
    links.append(entry)
    roster["links"] = links
    roster["updated"] = ts
    save_roster(roster)
    return entry


def remove_link(link_id: str) -> bool:
    sid = (link_id or "").strip()
    if not sid:
        return False
    roster = load_roster()
    links = list(roster.get("links") or [])
    kept = [s for s in links if str(s.get("id") or "") != sid]
    if len(kept) == len(links):
        return False
    roster["links"] = kept
    roster["updated"] = now_iso()
    save_roster(roster)
    return True


def replacement_for(part_number: str) -> str:
    """Immediate next number, or empty if this PN is current."""
    key = normalize_pn(part_number)
    if not key:
        return ""
    for row in list_links():
        if normalize_pn(row.get("old_number")) == key:
            return str(row.get("new_number") or "")
    return ""


def current_number(part_number: str) -> str:
    """Walk the supersession chain (A→B→C) and return the live PN."""
    cur = normalize_pn(part_number)
    if not cur:
        return ""
    seen: set[str] = set()
    while cur and cur not in seen:
        seen.add(cur)
        nxt = replacement_for(cur)
        if not nxt:
            return cur
        cur = nxt
    return cur


def lookup(part_number: str) -> dict[str, str] | None:
    key = normalize_pn(part_number)
    if not key:
        return None
    for row in list_links():
        if normalize_pn(row.get("old_number")) == key or normalize_pn(row.get("new_number")) == key:
            current = current_number(row.get("old_number") or key)
            return {**row, "current_number": current}
    return None


def annotate_suggestion(row: dict[str, Any]) -> dict[str, Any]:
    pn = str(row.get("part_number") or "")
    current = current_number(pn)
    out = dict(row)
    if current and pn and current != normalize_pn(pn):
        out["superseded_by"] = current
    else:
        out["superseded_by"] = ""
    return out


def replace_roster(remote: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(remote, dict):
        raise ValueError("part supersessions roster must be an object")
    links = remote.get("links")
    if links is not None and not isinstance(links, list):
        raise ValueError("links must be a list")
    payload = {
        "version": int(remote.get("version") or 1),
        "updated": str(remote.get("updated") or now_iso()),
        "links": links or [],
    }
    save_roster(payload)
    return load_roster()
