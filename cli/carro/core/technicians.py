"""Technician roster, 4-digit PIN hashes, and bay session."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from carro.config import CONFIG_DIR
from carro.core.models import now_iso

TECHNICIANS_FILE = CONFIG_DIR / "technicians.json"
SESSION_FILE = CONFIG_DIR / "session.json"
ADMIN_SESSION_FILE = CONFIG_DIR / "admin_session.json"
SESSION_TTL = timedelta(hours=8)
ADMIN_SESSION_TTL = timedelta(hours=2)

_PIN_RE = re.compile(r"^\d{4}$")


@dataclass
class Technician:
    id: str
    name: str
    pin_hash: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "pin_hash": self.pin_hash}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Technician:
        return cls(
            id=str(data.get("id") or "").strip(),
            name=str(data.get("name") or "").strip(),
            pin_hash=str(data.get("pin_hash") or "").strip(),
        )


def empty_roster() -> dict[str, Any]:
    return {
        "version": 1,
        "updated": "",
        "admin_pin_hash": "",
        "technicians": [],
    }


def load_roster() -> dict[str, Any]:
    if not TECHNICIANS_FILE.is_file():
        return empty_roster()
    try:
        raw = json.loads(TECHNICIANS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_roster()
    if not isinstance(raw, dict):
        return empty_roster()
    techs = raw.get("technicians")
    if not isinstance(techs, list):
        techs = []
    return {
        "version": int(raw.get("version") or 1),
        "updated": str(raw.get("updated") or ""),
        "admin_pin_hash": str(raw.get("admin_pin_hash") or ""),
        "technicians": [t for t in techs if isinstance(t, dict)],
    }


def save_roster(roster: dict[str, Any]) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    roster = deepcopy(roster)
    roster["version"] = 1
    roster["updated"] = now_iso()
    payload = {
        "version": 1,
        "updated": roster["updated"],
        "admin_pin_hash": str(roster.get("admin_pin_hash") or ""),
        "technicians": list(roster.get("technicians") or []),
    }
    TECHNICIANS_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return TECHNICIANS_FILE


def has_technicians() -> bool:
    return bool(load_roster().get("technicians"))


def list_technicians(roster: dict[str, Any] | None = None) -> list[Technician]:
    roster = roster or load_roster()
    out: list[Technician] = []
    for item in roster.get("technicians") or []:
        if isinstance(item, dict) and item.get("id") and item.get("name"):
            out.append(Technician.from_dict(item))
    return out


def get_technician(tech_id: str, roster: dict[str, Any] | None = None) -> Technician | None:
    tech_id = (tech_id or "").strip()
    for t in list_technicians(roster):
        if t.id == tech_id:
            return t
    return None


def validate_pin(pin: str) -> str:
    pin = (pin or "").strip()
    if not _PIN_RE.match(pin):
        raise ValueError("PIN must be exactly 4 digits")
    return pin


def generate_pin() -> str:
    """Random 4-digit PIN that does not conflict with the current roster."""
    roster = load_roster()
    for _ in range(200):
        pin = f"{secrets.randbelow(10_000):04d}"
        if not pin_conflicts(pin, roster=roster):
            return pin
    raise RuntimeError("Could not generate a free PIN")


def hash_pin(pin: str) -> str:
    pin = validate_pin(pin)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), salt.encode("utf-8"), 120_000
    )
    return f"pbkdf2_sha256$120000${salt}${digest.hex()}"


def verify_pin(pin: str, pin_hash: str) -> bool:
    pin = (pin or "").strip()
    if not _PIN_RE.match(pin) or not pin_hash:
        return False
    try:
        algo, rounds_s, salt, hexdigest = pin_hash.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        rounds = int(rounds_s)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), salt.encode("utf-8"), rounds
    )
    return secrets.compare_digest(digest.hex(), hexdigest)


def pin_conflicts(
    pin: str,
    *,
    roster: dict[str, Any] | None = None,
    exclude_tech_id: str | None = None,
    check_admin: bool = True,
    admin_pin_plain: str | None = None,
) -> bool:
    """
    True if PIN matches admin, another technician, or any advisor.
    `admin_pin_plain` covers first-run before admin hash is saved.
    """
    pin = validate_pin(pin)
    roster = roster or load_roster()
    if admin_pin_plain is not None and pin == validate_pin(admin_pin_plain):
        return True
    if check_admin and verify_pin(pin, str(roster.get("admin_pin_hash") or "")):
        return True
    for tech in list_technicians(roster):
        if exclude_tech_id and tech.id == exclude_tech_id:
            continue
        if verify_pin(pin, tech.pin_hash):
            return True
    try:
        from carro.core import advisors as advmod

        for adv in advmod.list_advisors():
            if verify_pin(pin, adv.pin_hash):
                return True
    except Exception:
        pass
    return False


def ensure_pin_available(
    pin: str,
    *,
    roster: dict[str, Any] | None = None,
    exclude_tech_id: str | None = None,
    check_admin: bool = True,
    admin_pin_plain: str | None = None,
) -> str:
    pin = validate_pin(pin)
    if pin_conflicts(
        pin,
        roster=roster,
        exclude_tech_id=exclude_tech_id,
        check_admin=check_admin,
        admin_pin_plain=admin_pin_plain,
    ):
        raise ValueError("PIN already used (admin, technician, or advisor)")
    return pin


def find_tech_by_pin(pin: str, roster: dict[str, Any] | None = None) -> Technician | None:
    for tech in list_technicians(roster):
        if verify_pin(pin, tech.pin_hash):
            return tech
    return None


def login_technician(tech_id: str, pin: str, *, roster: dict[str, Any] | None = None) -> Technician:
    """Verify PIN for a specific technician and start a session."""
    tech = get_technician(tech_id, roster)
    if not tech or not verify_pin(pin, tech.pin_hash):
        raise ValueError("Incorrect PIN")
    save_session(tech)
    return tech


def slugify_tech_id(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "tech"
    return base[:32]


def unique_tech_id(name: str, roster: dict[str, Any] | None = None) -> str:
    roster = roster or load_roster()
    existing = {t.id for t in list_technicians(roster)}
    base = slugify_tech_id(name)
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


def add_technician(
    name: str,
    pin: str,
    *,
    roster: dict[str, Any] | None = None,
    tech_id: str | None = None,
    admin_pin_plain: str | None = None,
) -> Technician:
    roster = roster or load_roster()
    name = (name or "").strip()
    if not name:
        raise ValueError("Technician name required")
    ensure_pin_available(pin, roster=roster, admin_pin_plain=admin_pin_plain)
    pin_hash = hash_pin(pin)
    tid = (tech_id or unique_tech_id(name, roster)).strip()
    tech = Technician(id=tid, name=name, pin_hash=pin_hash)
    techs = list(roster.get("technicians") or [])
    techs.append(tech.to_dict())
    roster["technicians"] = techs
    save_roster(roster)
    return tech


def update_technician_pin(tech_id: str, pin: str, *, roster: dict[str, Any] | None = None) -> None:
    roster = roster or load_roster()
    if not get_technician(tech_id, roster):
        raise ValueError(f"Unknown technician: {tech_id}")
    ensure_pin_available(pin, roster=roster, exclude_tech_id=tech_id)
    pin_hash = hash_pin(pin)
    techs = list(roster.get("technicians") or [])
    for item in techs:
        if isinstance(item, dict) and item.get("id") == tech_id:
            item["pin_hash"] = pin_hash
            break
    roster["technicians"] = techs
    save_roster(roster)


def rename_technician(tech_id: str, name: str, *, roster: dict[str, Any] | None = None) -> None:
    roster = roster or load_roster()
    name = (name or "").strip()
    if not name:
        raise ValueError("Name required")
    techs = list(roster.get("technicians") or [])
    found = False
    for item in techs:
        if isinstance(item, dict) and item.get("id") == tech_id:
            item["name"] = name
            found = True
            break
    if not found:
        raise ValueError(f"Unknown technician: {tech_id}")
    roster["technicians"] = techs
    save_roster(roster)


def remove_technician(tech_id: str, *, roster: dict[str, Any] | None = None) -> None:
    roster = roster or load_roster()
    techs = [
        t
        for t in (roster.get("technicians") or [])
        if not (isinstance(t, dict) and t.get("id") == tech_id)
    ]
    if len(techs) == len(roster.get("technicians") or []):
        raise ValueError(f"Unknown technician: {tech_id}")
    if not techs:
        raise ValueError("Cannot remove the last technician")
    roster["technicians"] = techs
    save_roster(roster)
    sess = load_session()
    if sess and sess.get("tech_id") == tech_id:
        clear_session()


def set_admin_pin(pin: str, *, roster: dict[str, Any] | None = None) -> None:
    roster = roster or load_roster()
    # Admin must not match any technician login PIN
    ensure_pin_available(pin, roster=roster, check_admin=False)
    roster["admin_pin_hash"] = hash_pin(pin)
    save_roster(roster)


def verify_admin_pin(pin: str, *, roster: dict[str, Any] | None = None) -> bool:
    roster = roster or load_roster()
    return verify_pin(pin, str(roster.get("admin_pin_hash") or ""))


def has_admin_pin(*, roster: dict[str, Any] | None = None) -> bool:
    roster = roster or load_roster()
    return bool(str(roster.get("admin_pin_hash") or "").strip())


def unlock_admin(pin: str, *, roster: dict[str, Any] | None = None) -> None:
    """Start an admin session (shop management / time corrections)."""
    if not has_admin_pin(roster=roster):
        raise ValueError("No admin PIN set — finish technician setup first")
    if not verify_admin_pin(pin, roster=roster):
        raise ValueError("Incorrect admin PIN")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"unlocked_at": now_iso()}
    ADMIN_SESSION_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def lock_admin() -> None:
    if ADMIN_SESSION_FILE.is_file():
        try:
            ADMIN_SESSION_FILE.unlink()
        except OSError:
            pass


def admin_unlocked() -> bool:
    if not ADMIN_SESSION_FILE.is_file():
        return False
    try:
        raw = json.loads(ADMIN_SESSION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        lock_admin()
        return False
    if not isinstance(raw, dict):
        lock_admin()
        return False
    unlocked = str(raw.get("unlocked_at") or "")
    try:
        when = datetime.fromisoformat(unlocked)
    except ValueError:
        lock_admin()
        return False
    if datetime.now() - when > ADMIN_SESSION_TTL:
        lock_admin()
        return False
    return True


def require_admin_session() -> None:
    if not admin_unlocked():
        raise PermissionError("Admin unlock required")


# --- session -----------------------------------------------------------------

_current: Technician | None = None


def load_session() -> dict[str, Any] | None:
    if not SESSION_FILE.is_file():
        return None
    try:
        raw = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
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


def save_session(tech: Technician) -> None:
    global _current
    _current = tech
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "tech_id": tech.id,
        "name": tech.name,
        "unlocked_at": now_iso(),
    }
    SESSION_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def clear_session() -> None:
    global _current
    _current = None
    if SESSION_FILE.is_file():
        try:
            SESSION_FILE.unlink()
        except OSError:
            pass


def current_technician() -> Technician | None:
    global _current
    if _current is not None:
        # Ensure still in roster
        if get_technician(_current.id):
            return _current
        clear_session()
        return None
    sess = load_session()
    if not sess:
        return None
    tech = get_technician(str(sess.get("tech_id") or ""))
    if not tech:
        clear_session()
        return None
    _current = tech
    return tech


def login_with_pin(pin: str) -> Technician:
    tech = find_tech_by_pin(pin)
    if not tech:
        raise ValueError("Incorrect PIN")
    save_session(tech)
    return tech


def stamp_order(order: Any, *, overwrite: bool = False) -> Any:
    """Attach current technician to a RepairOrder."""
    tech = current_technician()
    if not tech:
        return order
    if order.technician_id and not overwrite:
        return order
    order.technician_id = tech.id
    order.technician_name = tech.name
    return order


def roster_for_sync(roster: dict[str, Any] | None = None) -> dict[str, Any]:
    roster = roster or load_roster()
    return {
        "version": 1,
        "updated": str(roster.get("updated") or ""),
        "admin_pin_hash": str(roster.get("admin_pin_hash") or ""),
        "technicians": list(roster.get("technicians") or []),
    }


def apply_remote_roster(remote: dict[str, Any]) -> bool:
    """
    Replace local roster if remote payload is valid and newer (or local empty).
    Returns True if local was updated.
    """
    if not isinstance(remote, dict):
        return False
    remote_techs = remote.get("technicians")
    if not isinstance(remote_techs, list):
        return False
    local = load_roster()
    remote_updated = str(remote.get("updated") or "")
    local_updated = str(local.get("updated") or "")
    if local.get("technicians") and remote_updated and local_updated:
        if remote_updated <= local_updated:
            return False
    local["admin_pin_hash"] = str(remote.get("admin_pin_hash") or local.get("admin_pin_hash") or "")
    local["technicians"] = [t for t in remote_techs if isinstance(t, dict)]
    local["updated"] = remote_updated or now_iso()
    save_roster(local)
    # Re-validate session against new roster
    tech = current_technician()
    if tech and not get_technician(tech.id):
        clear_session()
    return True
