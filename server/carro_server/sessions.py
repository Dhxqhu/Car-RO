"""Phone / PWA sessions: PIN login → bearer/cookie token (not the shop API token)."""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SESSION_TTL = timedelta(days=14)
COOKIE_NAME = "carro_session"
MAX_FAILURES = 8
FAILURE_WINDOW_SEC = 15 * 60

_failures: dict[str, list[float]] = {}


@dataclass
class Principal:
    kind: str  # shop | technician | advisor
    id: str = ""
    name: str = ""
    token: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "ok": True,
            "kind": self.kind,
            "role": "tech"
            if self.kind == "technician"
            else ("advisor" if self.kind == "advisor" else self.kind),
            "id": self.id,
            "name": self.name,
            "technician": {"id": self.id, "name": self.name}
            if self.kind == "technician"
            else None,
            "advisor": {"id": self.id, "name": self.name}
            if self.kind == "advisor"
            else None,
        }


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_store(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"sessions": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"sessions": []}
    if not isinstance(raw, dict):
        return {"sessions": []}
    rows = raw.get("sessions")
    if not isinstance(rows, list):
        rows = []
    return {"sessions": [s for s in rows if isinstance(s, dict)]}


def save_store(path: Path, store: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def purge_expired(store: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    now = now or _now()
    keep: list[dict] = []
    for row in store.get("sessions") or []:
        exp = str(row.get("expires") or "")
        try:
            when = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when > now:
            keep.append(row)
    store["sessions"] = keep
    return store


def create_session(
    path: Path,
    *,
    kind: str,
    person_id: str,
    name: str,
    ttl: timedelta = SESSION_TTL,
) -> tuple[str, dict[str, Any]]:
    token = secrets.token_urlsafe(32)
    now = _now()
    row = {
        "token": token,
        "kind": kind,
        "id": person_id,
        "name": name,
        "created": _iso(now),
        "expires": _iso(now + ttl),
    }
    store = purge_expired(load_store(path), now=now)
    store["sessions"].append(row)
    save_store(path, store)
    return token, row


def get_session(path: Path, token: str) -> Principal | None:
    token = (token or "").strip()
    if not token:
        return None
    store = purge_expired(load_store(path))
    for row in store.get("sessions") or []:
        if secrets.compare_digest(str(row.get("token") or ""), token):
            return Principal(
                kind=str(row.get("kind") or ""),
                id=str(row.get("id") or ""),
                name=str(row.get("name") or ""),
                token=token,
            )
    return None


def revoke_session(path: Path, token: str) -> bool:
    token = (token or "").strip()
    if not token:
        return False
    store = load_store(path)
    before = len(store["sessions"])
    store["sessions"] = [
        s for s in store["sessions"] if not secrets.compare_digest(str(s.get("token") or ""), token)
    ]
    if len(store["sessions"]) == before:
        return False
    save_store(path, store)
    return True


def login_allowed(key: str) -> bool:
    now = time.time()
    hits = [t for t in _failures.get(key, []) if now - t < FAILURE_WINDOW_SEC]
    _failures[key] = hits
    return len(hits) < MAX_FAILURES


def record_failure(key: str) -> None:
    _failures.setdefault(key, []).append(time.time())


def clear_failures(key: str) -> None:
    _failures.pop(key, None)
