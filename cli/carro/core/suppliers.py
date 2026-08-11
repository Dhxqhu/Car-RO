"""Shop parts suppliers roster — uniform names for ordering history."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from carro.config import CONFIG_DIR
from carro.core.models import now_iso

SUPPLIERS_FILE = CONFIG_DIR / "suppliers.json"
_ID_RE = re.compile(r"^sup-[a-z0-9]+$", re.I)


def empty_roster() -> dict[str, Any]:
    return {"version": 1, "updated": "", "suppliers": []}


def load_roster() -> dict[str, Any]:
    if not SUPPLIERS_FILE.is_file():
        return empty_roster()
    try:
        raw = json.loads(SUPPLIERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_roster()
    if not isinstance(raw, dict):
        return empty_roster()
    suppliers = raw.get("suppliers")
    if not isinstance(suppliers, list):
        suppliers = []
    cleaned: list[dict[str, str]] = []
    for entry in suppliers:
        if not isinstance(entry, dict):
            continue
        sid = str(entry.get("id") or "").strip()
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        if not sid:
            sid = _new_id(cleaned)
        cleaned.append({"id": sid, "name": name})
    return {
        "version": int(raw.get("version") or 1),
        "updated": str(raw.get("updated") or ""),
        "suppliers": cleaned,
    }


def save_roster(roster: dict[str, Any]) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": int(roster.get("version") or 1),
        "updated": str(roster.get("updated") or now_iso()),
        "suppliers": [
            {"id": str(s.get("id") or "").strip(), "name": str(s.get("name") or "").strip()}
            for s in (roster.get("suppliers") or [])
            if isinstance(s, dict) and str(s.get("name") or "").strip()
        ],
    }
    SUPPLIERS_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return SUPPLIERS_FILE


def roster_for_sync() -> dict[str, Any]:
    return load_roster()


def list_suppliers() -> list[dict[str, str]]:
    return list(load_roster().get("suppliers") or [])


def _new_id(existing: list[dict[str, str]]) -> str:
    n = 1
    used = {str(s.get("id") or "").lower() for s in existing}
    while True:
        cand = f"sup-{n:03d}"
        if cand not in used:
            return cand
        n += 1


def add_supplier(name: str) -> dict[str, str]:
    """Add a supplier; case-insensitive de-dupe returns the existing entry."""
    clean = (name or "").strip()
    if not clean:
        raise ValueError("Supplier name required")
    roster = load_roster()
    suppliers = list(roster.get("suppliers") or [])
    key = clean.casefold()
    for s in suppliers:
        if str(s.get("name") or "").strip().casefold() == key:
            return {"id": str(s.get("id") or ""), "name": str(s.get("name") or "")}
    entry = {"id": _new_id(suppliers), "name": clean}
    suppliers.append(entry)
    roster["suppliers"] = suppliers
    roster["updated"] = now_iso()
    save_roster(roster)
    return entry


def remove_supplier(supplier_id: str) -> bool:
    sid = (supplier_id or "").strip()
    if not sid:
        return False
    roster = load_roster()
    suppliers = list(roster.get("suppliers") or [])
    kept = [s for s in suppliers if str(s.get("id") or "") != sid]
    if len(kept) == len(suppliers):
        return False
    roster["suppliers"] = kept
    roster["updated"] = now_iso()
    save_roster(roster)
    return True


def rename_supplier(supplier_id: str, name: str) -> dict[str, str]:
    sid = (supplier_id or "").strip()
    clean = (name or "").strip()
    if not sid:
        raise ValueError("Supplier id required")
    if not clean:
        raise ValueError("Supplier name required")
    roster = load_roster()
    suppliers = list(roster.get("suppliers") or [])
    key = clean.casefold()
    target: dict[str, str] | None = None
    for s in suppliers:
        if str(s.get("id") or "") == sid:
            target = s
            continue
        if str(s.get("name") or "").strip().casefold() == key:
            raise ValueError(f"Supplier already exists: {s.get('name')}")
    if not target:
        raise ValueError("Supplier not found")
    target["name"] = clean
    roster["suppliers"] = suppliers
    roster["updated"] = now_iso()
    save_roster(roster)
    return {"id": sid, "name": clean}


def replace_roster(remote: dict[str, Any]) -> dict[str, Any]:
    """Replace local roster from shop-server payload (sync pull/push target)."""
    if not isinstance(remote, dict):
        raise ValueError("suppliers roster must be an object")
    suppliers = remote.get("suppliers")
    if suppliers is not None and not isinstance(suppliers, list):
        raise ValueError("suppliers must be a list")
    payload = {
        "version": int(remote.get("version") or 1),
        "updated": str(remote.get("updated") or now_iso()),
        "suppliers": [
            {
                "id": str(s.get("id") or "").strip() or _new_id([]),
                "name": str(s.get("name") or "").strip(),
            }
            for s in (suppliers or [])
            if isinstance(s, dict) and str(s.get("name") or "").strip()
        ],
    }
    # Re-id any blanks uniquely
    seen: list[dict[str, str]] = []
    for s in payload["suppliers"]:
        if not s["id"] or s["id"] in {x["id"] for x in seen}:
            s["id"] = _new_id(seen)
        seen.append(s)
    payload["suppliers"] = seen
    save_roster(payload)
    return payload
