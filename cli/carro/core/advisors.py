"""Advisor roster, PIN hashes, desk session — parallel to technicians (separate login wall)."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from carro.config import CONFIG_DIR
from carro.core.models import now_iso
from carro.core.technicians import (
    ensure_pin_available,
    hash_pin,
    has_admin_pin,
    load_roster as load_tech_roster,
    set_admin_pin as set_tech_admin_pin,
    unlock_admin,
    validate_pin,
    verify_admin_pin,
    verify_pin,
)

ADVISORS_FILE = CONFIG_DIR / "advisors.json"
ADVISOR_SESSION_FILE = CONFIG_DIR / "advisor_session.json"
SESSION_TTL = timedelta(hours=8)

_PIN_RE = re.compile(r"^\d{4}$")


@dataclass
class Advisor:
    id: str
    name: str
    pin_hash: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "pin_hash": self.pin_hash}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Advisor:
        return cls(
            id=str(data.get("id") or "").strip(),
            name=str(data.get("name") or "").strip(),
            pin_hash=str(data.get("pin_hash") or "").strip(),
        )


def empty_roster() -> dict[str, Any]:
    return {
        "version": 1,
        "updated": "",
        "advisors": [],
    }


def load_roster() -> dict[str, Any]:
    if not ADVISORS_FILE.is_file():
        return empty_roster()
    try:
        raw = json.loads(ADVISORS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_roster()
    if not isinstance(raw, dict):
        return empty_roster()
    advisors = raw.get("advisors")
    if not isinstance(advisors, list):
        advisors = []
    return {
        "version": int(raw.get("version") or 1),
        "updated": str(raw.get("updated") or ""),
        "advisors": [a for a in advisors if isinstance(a, dict)],
    }


def save_roster(roster: dict[str, Any]) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    roster = deepcopy(roster)
    roster["version"] = 1
    roster["updated"] = now_iso()
    payload = {
        "version": 1,
        "updated": roster["updated"],
        "advisors": list(roster.get("advisors") or []),
    }
    ADVISORS_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return ADVISORS_FILE


def has_advisors() -> bool:
    return bool(load_roster().get("advisors"))


def list_advisors(roster: dict[str, Any] | None = None) -> list[Advisor]:
    roster = roster or load_roster()
    out: list[Advisor] = []
    for item in roster.get("advisors") or []:
        if isinstance(item, dict) and item.get("id") and item.get("name"):
            out.append(Advisor.from_dict(item))
    return out


def get_advisor(advisor_id: str, roster: dict[str, Any] | None = None) -> Advisor | None:
    advisor_id = (advisor_id or "").strip()
    for a in list_advisors(roster):
        if a.id == advisor_id:
            return a
    return None


def pin_conflicts_advisor(
    pin: str,
    *,
    roster: dict[str, Any] | None = None,
    exclude_advisor_id: str | None = None,
    admin_pin_plain: str | None = None,
) -> bool:
    """True if PIN matches admin, a technician, or another advisor."""
    pin = validate_pin(pin)
    roster = roster or load_roster()
    tech_roster = load_tech_roster()
    if admin_pin_plain is not None and pin == validate_pin(admin_pin_plain):
        return True
    if verify_pin(pin, str(tech_roster.get("admin_pin_hash") or "")):
        return True
    # Reuse tech pin check (techs only; admin already checked)
    from carro.core.technicians import list_technicians

    for tech in list_technicians(tech_roster):
        if verify_pin(pin, tech.pin_hash):
            return True
    for adv in list_advisors(roster):
        if exclude_advisor_id and adv.id == exclude_advisor_id:
            continue
        if verify_pin(pin, adv.pin_hash):
            return True
    return False


def ensure_advisor_pin_available(
    pin: str,
    *,
    roster: dict[str, Any] | None = None,
    exclude_advisor_id: str | None = None,
    admin_pin_plain: str | None = None,
) -> str:
    pin = validate_pin(pin)
    if pin_conflicts_advisor(
        pin,
        roster=roster,
        exclude_advisor_id=exclude_advisor_id,
        admin_pin_plain=admin_pin_plain,
    ):
        raise ValueError("PIN already used (admin, technician, or another advisor)")
    return pin


def slugify_advisor_id(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "advisor"
    return base[:32]


def unique_advisor_id(name: str, roster: dict[str, Any] | None = None) -> str:
    roster = roster or load_roster()
    existing = {a.id for a in list_advisors(roster)}
    base = slugify_advisor_id(name)
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


def add_advisor(
    name: str,
    pin: str,
    *,
    roster: dict[str, Any] | None = None,
    advisor_id: str | None = None,
    admin_pin_plain: str | None = None,
) -> Advisor:
    roster = roster or load_roster()
    name = (name or "").strip()
    if not name:
        raise ValueError("Advisor name required")
    ensure_advisor_pin_available(pin, roster=roster, admin_pin_plain=admin_pin_plain)
    pin_hash = hash_pin(pin)
    aid = (advisor_id or unique_advisor_id(name, roster)).strip()
    advisor = Advisor(id=aid, name=name, pin_hash=pin_hash)
    advisors = list(roster.get("advisors") or [])
    advisors.append(advisor.to_dict())
    roster["advisors"] = advisors
    save_roster(roster)
    return advisor


def update_advisor_pin(
    advisor_id: str, pin: str, *, roster: dict[str, Any] | None = None
) -> None:
    roster = roster or load_roster()
    if not get_advisor(advisor_id, roster):
        raise ValueError(f"Unknown advisor: {advisor_id}")
    ensure_advisor_pin_available(pin, roster=roster, exclude_advisor_id=advisor_id)
    pin_hash = hash_pin(pin)
    advisors = list(roster.get("advisors") or [])
    for item in advisors:
        if isinstance(item, dict) and item.get("id") == advisor_id:
            item["pin_hash"] = pin_hash
            break
    roster["advisors"] = advisors
    save_roster(roster)


def rename_advisor(advisor_id: str, name: str, *, roster: dict[str, Any] | None = None) -> None:
    roster = roster or load_roster()
    name = (name or "").strip()
    if not name:
        raise ValueError("Name required")
    advisors = list(roster.get("advisors") or [])
    found = False
    for item in advisors:
        if isinstance(item, dict) and item.get("id") == advisor_id:
            item["name"] = name
            found = True
            break
    if not found:
        raise ValueError(f"Unknown advisor: {advisor_id}")
    roster["advisors"] = advisors
    save_roster(roster)


def remove_advisor(advisor_id: str, *, roster: dict[str, Any] | None = None) -> None:
    roster = roster or load_roster()
    advisors = [
        a
        for a in (roster.get("advisors") or [])
        if not (isinstance(a, dict) and a.get("id") == advisor_id)
    ]
    if len(advisors) == len(roster.get("advisors") or []):
        raise ValueError(f"Unknown advisor: {advisor_id}")
    if not advisors:
        raise ValueError("Cannot remove the last advisor")
    roster["advisors"] = advisors
    save_roster(roster)
    sess = load_session()
    if sess and sess.get("advisor_id") == advisor_id:
        clear_session()


def bootstrap_first_advisor(
    name: str,
    pin: str,
    *,
    admin_pin: str,
    set_admin: bool = False,
) -> Advisor:
    """
    Create the first advisor. Requires admin PIN (existing or set_admin with new PIN).
    """
    if has_advisors():
        raise ValueError("Advisors already exist — log in instead")
    admin_pin = validate_pin(admin_pin)
    if set_admin or not has_admin_pin():
        set_tech_admin_pin(admin_pin)
    elif not verify_admin_pin(admin_pin):
        raise ValueError("Incorrect admin PIN")
    advisor = add_advisor(name, pin, admin_pin_plain=admin_pin)
    unlock_admin(admin_pin)
    return advisor


def login_advisor(advisor_id: str, pin: str, *, roster: dict[str, Any] | None = None) -> Advisor:
    advisor = get_advisor(advisor_id, roster)
    if not advisor or not verify_pin(pin, advisor.pin_hash):
        raise ValueError("Incorrect PIN")
    save_session(advisor)
    return advisor


# --- session -----------------------------------------------------------------

_current: Advisor | None = None


def load_session() -> dict[str, Any] | None:
    if not ADVISOR_SESSION_FILE.is_file():
        return None
    try:
        raw = json.loads(ADVISOR_SESSION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    unlocked = str(raw.get("unlocked_at") or "")
    try:
        when = datetime.fromisoformat(unlocked)
    except ValueError:
        return None
    if datetime.now() - when > SESSION_TTL:
        clear_session()
        return None
    return raw


def save_session(advisor: Advisor) -> None:
    global _current
    _current = advisor
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "advisor_id": advisor.id,
        "name": advisor.name,
        "role": "advisor",
        "unlocked_at": now_iso(),
    }
    ADVISOR_SESSION_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def clear_session() -> None:
    global _current
    _current = None
    if ADVISOR_SESSION_FILE.is_file():
        try:
            ADVISOR_SESSION_FILE.unlink()
        except OSError:
            pass


def current_advisor() -> Advisor | None:
    global _current
    if _current is not None:
        if get_advisor(_current.id):
            return _current
        clear_session()
        return None
    sess = load_session()
    if not sess:
        return None
    advisor = get_advisor(str(sess.get("advisor_id") or ""))
    if not advisor:
        clear_session()
        return None
    _current = advisor
    return advisor


def require_advisor() -> Advisor:
    advisor = current_advisor()
    if not advisor:
        raise PermissionError("Advisor login required")
    return advisor


def roster_for_sync(roster: dict[str, Any] | None = None) -> dict[str, Any]:
    roster = roster or load_roster()
    return {
        "version": 1,
        "updated": str(roster.get("updated") or ""),
        "advisors": list(roster.get("advisors") or []),
    }


def apply_remote_roster(remote: dict[str, Any]) -> bool:
    if not isinstance(remote, dict):
        return False
    remote_advisors = remote.get("advisors")
    if not isinstance(remote_advisors, list):
        return False
    local = load_roster()
    remote_updated = str(remote.get("updated") or "")
    local_updated = str(local.get("updated") or "")
    if local.get("advisors") and remote_updated and local_updated:
        if remote_updated <= local_updated:
            return False
    local["advisors"] = [a for a in remote_advisors if isinstance(a, dict)]
    local["updated"] = remote_updated or now_iso()
    save_roster(local)
    advisor = current_advisor()
    if advisor and not get_advisor(advisor.id):
        clear_session()
    return True
