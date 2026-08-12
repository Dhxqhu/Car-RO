"""PIN hash verify — same scheme as cli/carro/core/technicians.py (no cli import)."""

from __future__ import annotations

import hashlib
import re
import secrets

_PIN_RE = re.compile(r"^\d{4}$")


def validate_pin(pin: str) -> str:
    pin = (pin or "").strip()
    if not _PIN_RE.match(pin):
        raise ValueError("PIN must be exactly 4 digits")
    return pin


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
