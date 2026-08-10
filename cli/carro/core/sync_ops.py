"""Shared sync push used by CLI, engine API, and autosync timer."""

from __future__ import annotations

from typing import Any

from carro.config import load_config, resolve_local_keep, resolve_local_photo_keep
from carro.core.db import LocalStore
from carro.storage.remote import RemoteClient


def perform_sync(store: LocalStore | None = None) -> dict[str, Any]:
    """
    Push local ROs (+ technician roster) to the shop server and prune local cache.
    Returns a result dict suitable for API / logging. Does not raise for missing server.
    """
    store = store or LocalStore()
    remote = RemoteClient()
    if not remote.enabled:
        removed = store.prune()
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_server",
            "message": "No server_url configured — local only.",
            "pushed": 0,
            "pruned": removed,
            "roster": "skipped",
        }

    remote.health()  # may raise
    roster_status = "skipped"
    try:
        from carro.core.tech_ui import sync_roster_with_server

        roster_status = sync_roster_with_server()
    except Exception:
        roster_status = "skipped"

    actor = ""
    actor_id = ""
    try:
        from carro.core import technicians as techmod

        tech = techmod.current_technician()
        if tech:
            actor, actor_id = tech.name, tech.id
    except Exception:
        pass

    n = 0
    for order in store.list_orders():
        # Prefer logged-in tech as the change actor so they are not notified of their own sync
        remote.upsert_ro(
            order,
            actor=actor or order.technician_name or "",
            actor_id=actor_id or order.technician_id or "",
        )
        n += 1
    removed = store.prune()
    cfg = load_config()
    keep_n = resolve_local_keep(cfg)
    photo_n = resolve_local_photo_keep(cfg)
    return {
        "ok": True,
        "skipped": False,
        "message": f"Pushed {n} RO(s); technician roster: {roster_status}",
        "pushed": n,
        "pruned": removed,
        "roster": roster_status,
        "local_keep": keep_n,
        "local_photo_keep": photo_n,
    }
