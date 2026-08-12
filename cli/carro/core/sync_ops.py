"""Shared sync push used by CLI, engine API, and autosync timer."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from carro.config import (
    load_config,
    photos_dir,
    resolve_local_billed_keep,
    resolve_local_keep,
    resolve_local_photo_keep,
)
from carro.core.db import LocalStore
from carro.core.models import RepairOrder
from carro.storage.remote import RemoteClient, ServerTooOldError

log = logging.getLogger("carro.sync")


def _current_actor() -> tuple[str, str]:
    """Prefer technician when both sessions exist (shared engine dual-login)."""
    try:
        from carro.core import technicians as techmod

        tech = techmod.current_technician()
        if tech:
            return tech.name, tech.id
    except Exception:
        pass
    try:
        from carro.core import advisors as advmod

        adv = advmod.current_advisor()
        if adv:
            return adv.name, adv.id
    except Exception:
        pass
    return "", ""


def retry_unsynced_photos(order: RepairOrder) -> int:
    """
    Re-upload local photo files that never reached the shop server.
    Returns count of newly uploaded photos. Updates order.photos in place.
    """
    remote = RemoteClient()
    if not remote.enabled:
        return 0
    uploaded = 0
    dest_dir = photos_dir() / order.id
    for meta in order.photos or []:
        if not isinstance(meta, dict):
            continue
        if meta.get("remote") is True:
            continue
        if meta.get("local_cleared"):
            continue
        rel = meta.get("relpath") or meta.get("filename")
        if not rel:
            continue
        path = dest_dir / Path(str(rel)).name
        if not path.is_file():
            continue
        try:
            remote_meta = remote.upload_photo(
                order.id,
                str(path),
                tag=str(meta.get("tag") or "other"),
                filename=path.name,
                notes=str(meta.get("notes") or ""),
            )
            if isinstance(remote_meta, dict):
                meta["volume"] = remote_meta.get("volume", meta.get("volume") or "local")
            meta["remote"] = True
            uploaded += 1
        except Exception as exc:
            meta["remote"] = False
            log.debug("photo retry failed for %s/%s: %s", order.id, path.name, exc)
    return uploaded


def refresh_ro_if_clean(
    store: LocalStore,
    ro_id: str,
    order: RepairOrder | None = None,
    *,
    timeout: float = 3.0,
) -> RepairOrder | None:
    """
    If this PC has no queued edits, replace the local RO with the shop copy.
    Unreachable server or dirty local → keep local (offline edits stay queued).
    """
    current = order if order is not None else store.get(ro_id)
    if current is not None and store.needs_sync(current.id):
        return current
    remote = RemoteClient()
    if not remote.enabled:
        return current
    try:
        raw = remote.get_ro(ro_id, timeout=timeout)
        fresh = RepairOrder.from_dict(raw)
        store.save(fresh, mark_pending_sync=False)
        return fresh
    except Exception:
        return current


def try_push_ro(
    store: LocalStore,
    order: RepairOrder,
    *,
    actor: str = "",
    actor_id: str = "",
    save_photo_meta: bool = True,
) -> dict[str, Any]:
    """
    Best-effort upsert to the shop server after a local save.
    On failure the RO stays marked needs_sync for later retry — local data is never rolled back.
    After a successful PUT, adopt the (possibly merged) shop body so this PC
    matches the amended document. Offline queue is unchanged on failure.
    """
    remote = RemoteClient()
    if not remote.enabled:
        store.mark_synced(order.id)
        return {"ok": True, "skipped": True, "reason": "no_server"}

    who = (actor or "").strip()
    who_id = (actor_id or "").strip()
    if not who and not who_id:
        who, who_id = _current_actor()
    # Do not use order.technician_* as actor — stamped bay tech ≠ change author.

    photos_changed = False
    try:
        remote.check_server_compat()
        if retry_unsynced_photos(order):
            photos_changed = True
        base_updated = store.last_synced_updated(order.id)
        raw = remote.upsert_ro(
            order, actor=who, actor_id=who_id, base_updated=base_updated
        )
        adopted = order
        if isinstance(raw, dict) and raw.get("id"):
            try:
                adopted = RepairOrder.from_dict(raw)
            except Exception:
                adopted = order
        # Shop copy is source of truth after a successful push (merged or as-sent).
        store.save(adopted, mark_pending_sync=False)
        store.mark_synced(adopted.id)
        return {"ok": True, "skipped": False, "order": adopted.to_dict()}
    except ServerTooOldError as exc:
        store.mark_needs_sync(order.id)
        return {
            "ok": False,
            "error": str(exc),
            "reason": "server_too_old",
            "needs_sync": True,
        }
    except Exception as exc:
        store.mark_needs_sync(order.id)
        if photos_changed and save_photo_meta:
            try:
                store.save(order, mark_pending_sync=True)
            except Exception:
                pass
        log.warning("push RO %s failed (kept locally, will retry): %s", order.id, exc)
        return {"ok": False, "skipped": False, "error": str(exc)}


def try_push_pending_deletes(store: LocalStore, remote: RemoteClient | None = None) -> dict[str, Any]:
    remote = remote or RemoteClient()
    ids = store.list_pending_deletes()
    if not remote.enabled:
        return {"ok": True, "skipped": True, "cleared": 0, "failed": 0}
    cleared = 0
    failed = 0
    for rid in ids:
        try:
            remote.delete_ro(rid)
            store.clear_pending_delete(rid)
            cleared += 1
        except Exception as exc:
            failed += 1
            log.warning("pending delete %s failed (will retry): %s", rid, exc)
    return {"ok": failed == 0, "cleared": cleared, "failed": failed}


def perform_sync(
    store: LocalStore | None = None,
    *,
    pending_only: bool = False,
    sync_roster: bool | None = None,
    do_prune: bool | None = None,
) -> dict[str, Any]:
    """
    Push dirty local ROs (+ optional roster) to the shop server and prune cache.

    Always upserts pending (needs_sync) ROs only — never re-uploads the whole
    catalog. Continues past individual RO failures. Never prunes while unsynced
    ROs or pending deletes remain.

    pending_only: skip roster when sync_roster is not forced True (lean drain).
    sync_roster / do_prune: override defaults (None = derive from pending_only).
    """
    store = store or LocalStore()
    remote = RemoteClient()
    pending = store.sync_status()
    want_roster = (not pending_only) if sync_roster is None else bool(sync_roster)
    want_prune = True if do_prune is None else bool(do_prune)

    if not remote.enabled:
        removed = store.prune() if want_prune else []
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_server",
            "message": "No server_url configured — local only (data kept on this PC).",
            "pushed": 0,
            "failed": 0,
            "pruned": removed,
            "roster": "skipped",
            "pending": pending,
        }

    try:
        remote.check_server_compat()
    except ServerTooOldError as exc:
        return {
            "ok": False,
            "skipped": False,
            "reason": "server_too_old",
            "message": str(exc),
            "pushed": 0,
            "failed": 0,
            "pruned": 0,
            "roster": "skipped",
            "pending": pending,
        }
    except Exception as exc:
        try:
            from carro.core.connectivity import mark_server_unreachable

            mark_server_unreachable(str(exc))
        except Exception:
            pass
        return {
            "ok": False,
            "skipped": False,
            "reason": "unreachable",
            "message": (
                f"Server unreachable — local edits kept on this PC "
                f"({pending.get('pending_total', 0)} waiting to sync). {exc}"
            ),
            "pushed": 0,
            "failed": 0,
            "pruned": [],
            "roster": "skipped",
            "pending": pending,
            "error": str(exc),
        }

    try:
        from carro.core.connectivity import mark_server_reachable

        mark_server_reachable()
    except Exception:
        pass

    roster_status = "skipped"
    if want_roster:
        try:
            from carro.core.tech_ui import sync_roster_with_server

            roster_status = sync_roster_with_server()
        except Exception:
            roster_status = "skipped"

    del_result = try_push_pending_deletes(store, remote)

    from carro.core.message_offline import try_push_pending_messages
    from carro.core.shift_offline import try_push_pending_shifts

    shift_result = try_push_pending_shifts(store, remote)
    msg_result = try_push_pending_messages(store, remote)

    actor, actor_id = _current_actor()
    # Efficiency: only dirty ROs — already-synced rows stay local without re-PUT.
    orders = store.list_pending_orders()

    pushed = 0
    failed = 0
    errors: list[str] = []
    for order in orders:
        # Retry with session actor only — never invent attribution from stamped tech.
        result = try_push_ro(
            store,
            order,
            actor=actor,
            actor_id=actor_id,
        )
        if result.get("ok"):
            pushed += 1
        else:
            failed += 1
            err = str(result.get("error") or "push failed")
            errors.append(f"{order.id}: {err}")

    pending_after = store.sync_status()
    still_pending = int(pending_after.get("pending_total") or 0)
    removed: list[str] = []
    extras_failed = (
        int(del_result.get("failed") or 0)
        + int(shift_result.get("failed") or 0)
        + int(msg_result.get("failed") or 0)
    )
    if (
        want_prune
        and still_pending == 0
        and failed == 0
        and extras_failed == 0
    ):
        removed = store.prune()
    elif still_pending and want_prune:
        log.info(
            "skipping prune — %s item(s) still pending sync",
            still_pending,
        )

    cfg = load_config()
    keep_n = resolve_local_keep(cfg)
    photo_n = resolve_local_photo_keep(cfg)
    billed_n = resolve_local_billed_keep(cfg)
    ok = failed == 0 and extras_failed == 0
    shift_n = int(shift_result.get("cleared") or 0)
    msg_n = int(msg_result.get("cleared") or 0)
    if ok:
        if (
            pushed == 0
            and int(del_result.get("cleared") or 0) == 0
            and shift_n == 0
            and msg_n == 0
        ):
            message = f"Nothing pending; roster: {roster_status}"
        else:
            message = (
                f"Pushed {pushed} RO(s), {shift_n} shift op(s), "
                f"{msg_n} message(s); roster: {roster_status}"
            )
    else:
        message = (
            f"Synced {pushed} RO(s), {failed} failed — local copies kept "
            f"({still_pending} pending). Roster: {roster_status}"
        )
    return {
        "ok": ok,
        "skipped": False,
        "message": message,
        "pushed": pushed,
        "failed": failed,
        "errors": errors[:20],
        "pruned": removed,
        "roster": roster_status,
        "deletes": del_result,
        "shifts": shift_result,
        "messages": msg_result,
        "pending": pending_after,
        "local_keep": keep_n,
        "local_photo_keep": photo_n,
        "local_billed_keep": billed_n,
    }
