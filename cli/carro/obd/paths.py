"""Shared filesystem locations for the obdscan ↔ Car-RO handoff.

Keep in lockstep with obdscan (`SAVED_CODES_DIR`, `LAST_VEHICLE_FILE`, adapters).
"""

from __future__ import annotations

import os
from pathlib import Path


def documents_dir() -> Path:
    """User Documents folder (honors XDG_DOCUMENTS_DIR / user-dirs.dirs)."""
    env = (os.environ.get("XDG_DOCUMENTS_DIR") or "").strip()
    if env:
        return Path(env).expanduser()
    dirs_file = Path.home() / ".config" / "user-dirs.dirs"
    if dirs_file.is_file():
        try:
            for line in dirs_file.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("XDG_DOCUMENTS_DIR="):
                    raw = line.split("=", 1)[1].strip().strip('"')
                    raw = raw.replace("$HOME", str(Path.home()))
                    if raw:
                        return Path(raw).expanduser()
        except OSError:
            pass
    return Path.home() / "Documents"


def saved_codes_dir() -> Path:
    return documents_dir() / "Saved Codes"


def last_vehicle_file() -> Path:
    return Path.home() / ".cache" / "obdscan" / "last_vehicle.json"


def adapters_file() -> Path:
    return Path.home() / ".config" / "obdscan" / "adapters.json"


def session_lock_file() -> Path:
    return Path.home() / ".cache" / "obdscan" / "session.lock"
