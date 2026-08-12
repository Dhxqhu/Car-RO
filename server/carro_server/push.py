"""Web Push (VAPID) for the phone PWA — iOS Home Screen apps included."""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def vapid_path(root: Path) -> Path:
    return Path(root) / "vapid.json"


def subs_path(root: Path) -> Path:
    return Path(root) / "push_subscriptions.json"


def load_or_create_vapid(root: Path) -> dict[str, str]:
    path = vapid_path(root)
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and raw.get("public_key") and raw.get("private_key"):
                return {
                    "public_key": str(raw["public_key"]),
                    "private_key": str(raw["private_key"]),
                }
        except (OSError, json.JSONDecodeError):
            pass
    pk = ec.generate_private_key(ec.SECP256R1())
    priv = pk.private_numbers().private_value.to_bytes(32, "big")
    pub = pk.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    keys = {"public_key": _b64url(pub), "private_key": _b64url(priv)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keys, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return keys


def _load_subs(root: Path) -> list[dict[str, Any]]:
    path = subs_path(root)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = raw.get("subscriptions") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        return []
    return [s for s in rows if isinstance(s, dict) and s.get("endpoint")]


def _save_subs(root: Path, rows: list[dict[str, Any]]) -> None:
    path = subs_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"subscriptions": rows}, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def upsert_subscription(
    root: Path,
    *,
    person_id: str,
    person_name: str,
    role: str,
    endpoint: str,
    keys: dict[str, str],
) -> dict[str, Any]:
    endpoint = (endpoint or "").strip()
    p256dh = str((keys or {}).get("p256dh") or "").strip()
    auth = str((keys or {}).get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        raise ValueError("endpoint, keys.p256dh, and keys.auth required")
    rows = [s for s in _load_subs(root) if str(s.get("endpoint") or "") != endpoint]
    row = {
        "person_id": person_id,
        "person_name": person_name,
        "role": role,
        "endpoint": endpoint,
        "keys": {"p256dh": p256dh, "auth": auth},
        "updated": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    rows.append(row)
    _save_subs(root, rows)
    return row


def remove_subscription(root: Path, *, person_id: str, endpoint: str = "") -> int:
    endpoint = (endpoint or "").strip()
    before = _load_subs(root)
    after = []
    for s in before:
        same_person = str(s.get("person_id") or "") == person_id
        same_ep = not endpoint or str(s.get("endpoint") or "") == endpoint
        if same_person and same_ep:
            continue
        after.append(s)
    _save_subs(root, after)
    return len(before) - len(after)


def has_subscription(root: Path, person_id: str) -> bool:
    pid = (person_id or "").strip()
    return any(str(s.get("person_id") or "") == pid for s in _load_subs(root))


def vapid_mailto() -> str:
    raw = (os.environ.get("CARRO_VAPID_MAILTO") or "mailto:carro@localhost").strip()
    if raw.startswith("mailto:") or raw.startswith("https://"):
        return raw
    return f"mailto:{raw}"


def notify_person(
    root: Path,
    *,
    person_id: str,
    title: str,
    body: str,
    url: str = "/",
) -> int:
    """Best-effort Web Push. Never raises to the caller."""
    pid = (person_id or "").strip()
    if not pid:
        return 0
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return 0
    keys = load_or_create_vapid(root)
    sent = 0
    keep: list[dict[str, Any]] = []
    payload = json.dumps({"title": title, "body": body, "url": url})
    for sub in _load_subs(root):
        if str(sub.get("person_id") or "") != pid:
            keep.append(sub)
            continue
        info = {
            "endpoint": sub.get("endpoint"),
            "keys": sub.get("keys") or {},
        }
        try:
            webpush(
                subscription_info=info,
                data=payload,
                vapid_private_key=keys["private_key"],
                vapid_claims={"sub": vapid_mailto()},
            )
            sent += 1
            keep.append(sub)
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status not in (404, 410):
                keep.append(sub)
        except Exception:
            keep.append(sub)
    _save_subs(root, keep)
    return sent
