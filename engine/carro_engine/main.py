"""Thin FastAPI wrapper around carro core for the desktop GUI."""

from __future__ import annotations

import secrets
import shutil
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Allow running from repo without install
_ROOT = Path(__file__).resolve().parents[2]
_CLI = _ROOT / "cli"
_SERVER = _ROOT / "server"
for p in (_CLI, _SERVER):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from carro.config import (  # noqa: E402
    CONFIG_FILE,
    disk_info,
    ensure_dirs,
    format_keep_setting,
    keep_presets,
    load_config,
    photo_keep_presets,
    recommend_local_keep,
    recommend_local_photo_keep,
    resolve_local_billed_keep,
    resolve_local_keep,
    resolve_local_parts_received_keep_hours,
    resolve_idle_nudge_hours,
    resolve_local_photo_keep,
    resolve_pa_inspection_types,
    save_config,
)
from carro.core import technicians as techmod  # noqa: E402
from carro.core import advisors as advmod  # noqa: E402
from carro.core.db import LocalStore  # noqa: E402
from carro.core.history import customer_vehicle_fields_from, vehicle_history  # noqa: E402
from carro.core.logo_setup import clear_logo, install_logo, logo_status  # noqa: E402
from carro.core.models import RepairOrder  # noqa: E402
from carro.core.pdf import export_pdf  # noqa: E402
from carro.obd.provider import pull_vehicle_fields  # noqa: E402
from carro.photos.providers.local import LocalPhotoIngress  # noqa: E402
from carro.storage.photos import attach_photos, ensure_local_photos  # noqa: E402
from carro.storage.remote import RemoteClient  # noqa: E402
from carro.core.autosync import autosync_status, start_autosync, stop_autosync  # noqa: E402
from carro.core.sync_ops import perform_sync  # noqa: E402
from carro.version import APP_VERSION, version_payload  # noqa: E402
from obd_engine.doip_routes import router as doip_router  # noqa: E402
from obd_engine.main import router as obd_router  # noqa: E402

store = LocalStore()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # One-shot shop API compat check (no update nags — only if this build needs a newer server).
    try:
        remote = RemoteClient()
        if remote.enabled:
            remote.check_server_compat()
    except Exception as exc:
        import logging

        logging.getLogger("carro.engine").warning("Shop server compat check: %s", exc)
    try:
        import logging
        from carro.core.tech_ui import sync_roster_with_server

        if RemoteClient().enabled:
            status = sync_roster_with_server()
            logging.getLogger("carro.engine").info("Roster sync on engine start: %s", status)
    except Exception as exc:
        import logging

        logging.getLogger("carro.engine").warning("Roster sync on engine start: %s", exc)
    start_autosync(store)
    try:
        from carro.core.day_plans import set_day_plan_notify

        set_day_plan_notify(_notify_tech_message)
    except Exception:
        pass
    try:
        yield
    finally:
        try:
            from carro.core.day_plans import set_day_plan_notify

            set_day_plan_notify(None)
        except Exception:
            pass
        stop_autosync()


app = FastAPI(title="carro-engine", version=APP_VERSION, lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(obd_router)
app.include_router(doip_router)


class LoginBody(BaseModel):
    tech_id: str
    pin: str


class AdvisorLoginBody(BaseModel):
    advisor_id: str
    pin: str


class AddTechBody(BaseModel):
    name: str
    pin: str
    admin_pin: str | None = Field(default=None, alias="admin_pin")

    model_config = {"populate_by_name": True}


class AddAdvisorBody(BaseModel):
    name: str
    pin: str
    admin_pin: str | None = Field(default=None, alias="admin_pin")

    model_config = {"populate_by_name": True}


class BootstrapBody(BaseModel):
    """First tech or first advisor when roster empty; may set global admin PIN."""

    name: str
    pin: str
    admin_pin: str = Field(alias="admin_pin")
    set_admin: bool = False

    model_config = {"populate_by_name": True}


class ConfigBody(BaseModel):
    shop_name: str | None = None
    server_url: str | None = None
    token: str | None = None
    clear_token: bool | None = None
    theme: str | None = None
    textual_theme: str | None = None
    logo_path: str | None = None
    local_keep: str | int | None = None
    local_photo_keep: str | int | None = None
    local_billed_keep: int | None = None
    local_parts_received_keep_hours: float | None = None
    idle_nudge_hours: float | None = None
    autosync_minutes: int | None = None
    pa_inspection_types: bool | None = None
    photos_dir: str | None = None
    photos_inbox_dir: str | None = None
    photos_provider: str | None = None


class HistoryPackBody(BaseModel):
    vin: str = ""
    name: str = ""
    exclude_id: str | None = None
    kind: Literal["text", "pdf", "pdf-lite"] = "text"


class HistoryNewFromBody(BaseModel):
    prior_id: str
    # Which session to attribute when both tech + advisor are logged into a shared engine.
    prefer_actor: Literal["advisor", "tech"] = "advisor"


class CreateRoBody(BaseModel):
    prefer_actor: Literal["advisor", "tech"] = "advisor"


class AppointmentBody(BaseModel):
    id: str | None = None
    scheduled_at: str = ""
    all_day: bool = False
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    year: str = ""
    make: str = ""
    model: str = ""
    vin: str = ""
    notes: str = ""
    tag: str = "other"
    requested_tech_id: str = ""
    requested_tech_name: str = ""
    prior_ro_id: str = ""
    service_plan_id: str = ""
    service_plan_line_id: str = ""
    service_plan_enroll: str = ""


class AppointmentArchiveBody(BaseModel):
    status: Literal["canceled", "no_show"]


class AppointmentConfirmBody(BaseModel):
    outcome: Literal["confirmed", "canceled", "no_answer", "veto_next", "veto"]


class ServicePlanBody(BaseModel):
    id: str | None = None
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    year: str = ""
    make: str = ""
    model: str = ""
    vin: str = ""
    notes: str = ""
    lines: list[dict[str, Any]] | None = None


class ServicePlanLineBody(BaseModel):
    id: str | None = None
    label: str = ""
    interval_months: int = 12
    tag: str = "service"
    last_done_at: str = ""
    next_due: str = ""
    notes: str = ""
    delete: bool = False


class ServicePlanCallBody(BaseModel):
    outcome: Literal["confirmed", "no_answer", "skip", "canceled", "veto_next", "veto"]


class PhoneUploadBody(BaseModel):
    tag: str = "intake"
    mode: Literal["phone", "shortcut"] = "phone"


class IngestPhotosBody(BaseModel):
    tag: str = "intake"
    notes: str = ""


class PullObdBody(BaseModel):
    """force=True applies snapshot after a VIN mismatch confirm."""

    force: bool = False


@app.get("/health")
def health() -> dict[str, Any]:
    cfg = load_config()
    return {"ok": True, "shop_name": cfg.get("shop_name") or "", **version_payload()}


@app.get("/version")
def version_info() -> dict[str, Any]:
    return {"ok": True, **version_payload()}


def _push_ro(
    order: RepairOrder,
    *,
    actor: str = "",
    actor_id: str = "",
) -> dict[str, Any]:
    """
    Upsert to shop server after local save. Failures leave the RO marked for retry —
    local SQLite data is never discarded.

    Pass actor/actor_id from the route that performed the change. When omitted,
    prefers the logged-in technician over advisor (shared-engine dual login).
    Advisor-only desk routes should pass the advisor explicitly.
    """
    from carro.core.sync_ops import try_push_ro

    who = (actor or "").strip()
    who_id = (actor_id or "").strip()
    if not who and not who_id:
        tech = techmod.current_technician()
        adv = advmod.current_advisor()
        if tech:
            who, who_id = tech.name, tech.id
        elif adv:
            who, who_id = adv.name, adv.id
    # Never fall back to order.technician_* — that is the stamped bay tech,
    # not who made this change (advisor create would look like the tech).
    return try_push_ro(
        store,
        order,
        actor=who,
        actor_id=who_id,
    )


def _require_order(ro_id: str) -> RepairOrder:
    """Load RO for an edit: pull shop copy first unless this PC has queued changes."""
    from carro.core.sync_ops import refresh_ro_if_clean

    order = refresh_ro_if_clean(store, ro_id, store.get(ro_id))
    if not order:
        raise HTTPException(404, "RO not found")
    return order


def _notify_tech_message(
    *,
    to_id: str,
    to_name: str,
    body: str,
    from_id: str,
    from_name: str,
    from_role: str = "advisor",
    ro_id: str = "",
    work_item_id: str = "",
) -> None:
    """Best-effort shop message to one technician (bell + inbox)."""
    tid = (to_id or "").strip()
    if not tid:
        return
    remote = RemoteClient()
    if not remote.enabled:
        return
    sender_id = (from_id or "").strip() or "system"
    if sender_id == tid:
        return
    role = (from_role or "advisor").strip().lower()
    if role not in ("technician", "advisor"):
        role = "advisor"
    try:
        remote.send_message(
            {
                "body": (body or "").strip() or "Update",
                "from_id": sender_id,
                "from_name": (from_name or "").strip() or "Desk",
                "from_role": role,
                "to_id": tid,
                "to_name": (to_name or "").strip(),
                "to_role": "technician",
                "ro_id": (ro_id or "").strip(),
                "work_item_id": (work_item_id or "").strip(),
            }
        )
    except Exception:
        pass


def _actor_from(tech: Any = None, advisor: Any = None, *, prefer: str = "tech") -> tuple[str, str]:
    """Pick display actor for event attribution from route-local sessions."""
    if prefer == "advisor":
        if advisor:
            return advisor.name, advisor.id
        if tech:
            return tech.name, tech.id
    else:
        if tech:
            return tech.name, tech.id
        if advisor:
            return advisor.name, advisor.id
    return "", ""


def _bay_worker() -> tuple[str, str]:
    """Logged-in technician, or advisor with working privilege (bay worker)."""
    tech = techmod.current_technician()
    if tech:
        return tech.id, tech.name
    advisor = advmod.current_advisor()
    if advisor and advmod.has_working_privilege(advisor):
        return advisor.id, advisor.name
    raise HTTPException(
        401,
        "Log in as a technician, or as an advisor with working privilege",
    )


def _merge_actor() -> tuple[str, str]:
    """Technician or any advisor may merge related work items."""
    tech = techmod.current_technician()
    if tech:
        return tech.id, tech.name
    advisor = advmod.current_advisor()
    if advisor:
        return advisor.id, advisor.name
    raise HTTPException(401, "Log in as a technician or advisor to merge work items")


@app.get("/events")
def engine_events(
    since: str = "",
    since_id: int = 0,
    ro_id: str = "",
    limit: int = 100,
    exclude_actor: str = "",
    exclude_actor_id: str = "",
    exclude_self: bool = True,
) -> dict[str, Any]:
    """
    Shop-server event feed. By default excludes the current technician so
    tech↔tech (and later advisor) notifications never fire for the person who made the change.
    """
    remote = RemoteClient()
    if not remote.enabled:
        return {
            "events": [],
            "note": "No server_url — live events require carro-server.",
        }
    if exclude_self and not exclude_actor and not exclude_actor_id:
        tech = techmod.current_technician()
        if tech:
            exclude_actor = tech.name
            exclude_actor_id = tech.id
    try:
        return remote.list_events(
            since=since,
            since_id=since_id,
            ro_id=ro_id,
            limit=limit,
            exclude_actor=exclude_actor,
            exclude_actor_id=exclude_actor_id,
        )
    except Exception as exc:
        # Older shop servers may not have /events yet — keep the tech UI quiet.
        return {
            "events": [],
            "note": f"Live events unavailable on server ({exc}). Update carro-server for team notifications.",
        }


class ShopMessageBody(BaseModel):
    body: str
    to_id: str
    to_role: Literal["technician", "advisor"]
    to_name: str = ""
    ro_id: str = ""
    work_item_id: str = ""
    reply_to: int | None = None


class MessageReadBody(BaseModel):
    for_id: str = ""


class MessagesDeliveredBody(BaseModel):
    ids: list[int] = []


class ShiftStartBody(BaseModel):
    tech_id: str = ""
    tech_name: str = ""
    started_at: str = ""
    day: str = ""


class ShiftEndBody(BaseModel):
    tech_id: str = ""
    shift_id: int | None = None
    ended_at: str = ""


class ShiftPatchBody(BaseModel):
    started_at: str | None = None
    ended_at: str | None = None
    clear_end: bool = False
    day: str | None = None
    admin_pin: str = ""


def _messaging_actor(*, prefer: str | None = None) -> tuple[str, str, str]:
    """
    Return (id, name, role) for shop messaging.

    When both tech and advisor sessions exist on one PC (dual login), callers must
    pass prefer=technician|advisor so the tech app and advisor app keep separate inboxes.
    """
    tech = techmod.current_technician()
    advisor = advmod.current_advisor()
    pref = (prefer or "").strip().lower()
    if pref in ("technician", "tech"):
        if tech:
            return tech.id, tech.name, "technician"
        if advisor:
            return advisor.id, advisor.name, "advisor"
    elif pref == "advisor":
        if advisor:
            return advisor.id, advisor.name, "advisor"
        if tech:
            return tech.id, tech.name, "technician"
    else:
        # No explicit role: prefer sole session; if both, prefer tech (bay PC default).
        if tech and not advisor:
            return tech.id, tech.name, "technician"
        if advisor and not tech:
            return advisor.id, advisor.name, "advisor"
        if tech:
            return tech.id, tech.name, "technician"
        if advisor:
            return advisor.id, advisor.name, "advisor"
    raise HTTPException(401, "Log in as a technician or advisor to use messages")


def _messaging_prefer_from_request(
    as_role: str | None = None,
    x_carro_as_role: str | None = None,
) -> str | None:
    raw = (as_role or x_carro_as_role or "").strip().lower()
    if raw in ("technician", "tech", "advisor"):
        return "technician" if raw in ("technician", "tech") else "advisor"
    return None


def _reject_tech_client_for_advisor_action(
    as_role: str | None = None,
    x_carro_as_role: str | None = None,
) -> None:
    """Block tech-app calls from riding a dual-login advisor session."""
    prefer = _messaging_prefer_from_request(as_role, x_carro_as_role)
    if prefer == "technician":
        raise HTTPException(
            403,
            "This action is advisor-only (use the advisor desk)",
        )


def _require_advisor_for_desk(
    *,
    as_role: str | None = None,
    x_carro_as_role: str | None = None,
    detail: str = "Log in as an advisor",
) -> Any:
    _reject_tech_client_for_advisor_action(as_role, x_carro_as_role)
    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, detail)
    return advisor


def _require_remote_for_messages() -> RemoteClient:
    remote = RemoteClient()
    if not remote.enabled:
        raise HTTPException(
            400,
            "Shop messaging needs a server_url — messages are shared across bay PCs.",
        )
    return remote


@app.get("/messages/people")
def message_people(
    as_role: str | None = None,
    x_carro_as_role: str | None = Header(default=None, alias="X-Carro-As-Role"),
) -> dict[str, Any]:
    """Combined roster for the compose picker — every other tech and advisor."""
    techs = [
        {"id": t.id, "name": t.name, "role": "technician"}
        for t in techmod.list_technicians()
    ]
    advisors = [
        {"id": a.id, "name": a.name, "role": "advisor"}
        for a in advmod.list_advisors()
    ]
    prefer = _messaging_prefer_from_request(as_role, x_carro_as_role)
    me_id, _, me_role = _messaging_actor(prefer=prefer)
    people = [p for p in techs + advisors if p["id"] != me_id]
    people.sort(key=lambda p: ((p["role"] != "advisor"), p["name"].lower()))
    return {
        "people": people,
        "me": {"id": me_id, "role": me_role},
        "server_required": True,
    }


@app.get("/messages")
def get_messages(
    unread: bool = False,
    limit: int = 100,
    as_role: str | None = None,
    x_carro_as_role: str | None = Header(default=None, alias="X-Carro-As-Role"),
) -> dict[str, Any]:
    from carro.core import message_offline as msg_off

    _require_remote_for_messages()
    prefer = _messaging_prefer_from_request(as_role, x_carro_as_role)
    me_id, _, _ = _messaging_actor(prefer=prefer)
    return msg_off.list_inbox(store, me_id=me_id, unread=unread, limit=limit)


@app.get("/messages/sent")
def get_sent_messages(
    limit: int = 100,
    as_role: str | None = None,
    x_carro_as_role: str | None = Header(default=None, alias="X-Carro-As-Role"),
) -> dict[str, Any]:
    from carro.core import message_offline as msg_off

    _require_remote_for_messages()
    prefer = _messaging_prefer_from_request(as_role, x_carro_as_role)
    me_id, _, _ = _messaging_actor(prefer=prefer)
    return msg_off.list_sent(store, me_id=me_id, limit=limit)


@app.get("/messages/thread")
def get_message_thread(
    with_id: str = "",
    limit: int = 200,
    as_role: str | None = None,
    x_carro_as_role: str | None = Header(default=None, alias="X-Carro-As-Role"),
) -> dict[str, Any]:
    """Chronological conversation between me and with_id (inbox + sent merged)."""
    from carro.core import message_offline as msg_off

    _require_remote_for_messages()
    prefer = _messaging_prefer_from_request(as_role, x_carro_as_role)
    me_id, me_name, me_role = _messaging_actor(prefer=prefer)
    other = (with_id or "").strip()
    if not other:
        raise HTTPException(400, "with_id required")
    inbox = msg_off.list_inbox(store, me_id=me_id, unread=False, limit=max(limit, 100))
    sent = msg_off.list_sent(store, me_id=me_id, limit=max(limit, 100))
    offline = bool(inbox.get("offline") or sent.get("offline"))
    rows: list[dict[str, Any]] = []
    for m in list(inbox.get("messages") or []) + list(sent.get("messages") or []):
        if not isinstance(m, dict):
            continue
        a = str(m.get("from_id") or "")
        b = str(m.get("to_id") or "")
        if (a == me_id and b == other) or (a == other and b == me_id):
            rows.append(m)
    # de-dupe by id, oldest first
    by_id: dict[str, dict[str, Any]] = {}
    for m in rows:
        mid = m.get("id")
        key = str(m.get("client_id") or mid or "")
        if key:
            by_id[key] = m
    messages = sorted(by_id.values(), key=lambda m: str(m.get("at") or ""))
    if len(messages) > limit:
        messages = messages[-limit:]
    out: dict[str, Any] = {
        "messages": messages,
        "me": {"id": me_id, "name": me_name, "role": me_role},
        "with_id": other,
        "offline": offline,
    }
    if offline:
        out["note"] = (
            "Shop server unreachable — showing cached / queued messages. "
            "Updates sync on reconnect."
        )
    return out


@app.post("/messages")
def post_message(
    body: ShopMessageBody,
    as_role: str | None = None,
    x_carro_as_role: str | None = Header(default=None, alias="X-Carro-As-Role"),
) -> dict[str, Any]:
    from carro.core import message_offline as msg_off

    _require_remote_for_messages()
    prefer = _messaging_prefer_from_request(as_role, x_carro_as_role)
    from_id, from_name, from_role = _messaging_actor(prefer=prefer)
    to_id = body.to_id.strip()
    if to_id == from_id:
        raise HTTPException(400, "Cannot message yourself")
    payload = {
        "body": body.body,
        "from_id": from_id,
        "from_name": from_name,
        "from_role": from_role,
        "to_id": to_id,
        "to_name": (body.to_name or "").strip(),
        "to_role": body.to_role,
        "ro_id": (body.ro_id or "").strip(),
        "work_item_id": (body.work_item_id or "").strip(),
        "reply_to": body.reply_to,
    }
    try:
        return msg_off.send_message(store, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/messages/{message_id}/read")
def post_message_read(
    message_id: int,
    body: MessageReadBody | None = None,
    as_role: str | None = None,
    x_carro_as_role: str | None = Header(default=None, alias="X-Carro-As-Role"),
) -> dict[str, Any]:
    from carro.core import message_offline as msg_off

    _require_remote_for_messages()
    prefer = _messaging_prefer_from_request(as_role, x_carro_as_role)
    me_id, _, _ = _messaging_actor(prefer=prefer)
    for_id = (body.for_id if body else "") or me_id
    if for_id != me_id:
        raise HTTPException(403, "Can only mark your own inbox messages as read")
    try:
        return msg_off.mark_read(store, message_id, for_id=me_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/messages/delivered")
def post_messages_delivered(
    body: MessagesDeliveredBody,
    as_role: str | None = None,
    x_carro_as_role: str | None = Header(default=None, alias="X-Carro-As-Role"),
) -> dict[str, Any]:
    """Ack that inbox messages reached this bay (batch)."""
    from carro.core import message_offline as msg_off

    _require_remote_for_messages()
    prefer = _messaging_prefer_from_request(as_role, x_carro_as_role)
    me_id, _, _ = _messaging_actor(prefer=prefer)
    ids = [int(x) for x in (body.ids or []) if int(x) > 0]
    return msg_off.mark_delivered(store, ids, for_id=me_id)


@app.post("/messages/{message_id}/renotify")
def post_message_renotify(
    message_id: int,
    as_role: str | None = None,
    x_carro_as_role: str | None = Header(default=None, alias="X-Carro-As-Role"),
) -> dict[str, Any]:
    remote = _require_remote_for_messages()
    prefer = _messaging_prefer_from_request(as_role, x_carro_as_role)
    me_id, _, _ = _messaging_actor(prefer=prefer)
    try:
        return remote.renotify_message(message_id, from_id=me_id)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            502,
            f"Could not renotify (will retry when online): {exc}",
        ) from exc


@app.get("/shifts/active")
def engine_shifts_active() -> dict[str, Any]:
    from carro.core import shift_offline as shift_off

    return shift_off.list_active_merged(store)


@app.get("/shifts/mine")
def engine_shift_mine() -> dict[str, Any]:
    from carro.core import shift_offline as shift_off

    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician")
    return shift_off.get_open_shift(store, tech.id)


@app.post("/shifts/start")
def engine_shift_start(body: ShiftStartBody | None = None) -> dict[str, Any]:
    from carro.core import shift_offline as shift_off

    body = body or ShiftStartBody()
    advisor = advmod.current_advisor()
    tech = techmod.current_technician()
    tech_id = (body.tech_id or "").strip()
    tech_name = (body.tech_name or "").strip()
    started_at = (body.started_at or "").strip()
    day = (body.day or "").strip()
    if advisor and tech_id:
        pass  # advisor clocking someone in
    elif tech:
        tech_id = tech.id
        tech_name = tech.name
    else:
        raise HTTPException(401, "Log in as a technician or advisor")
    if not tech_id:
        raise HTTPException(400, "tech_id required")
    try:
        return shift_off.start_shift(
            store,
            tech_id=tech_id,
            tech_name=tech_name,
            started_at=started_at,
            day=day,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/shifts/end")
def engine_shift_end(body: ShiftEndBody | None = None) -> dict[str, Any]:
    from carro.core import shift_offline as shift_off

    body = body or ShiftEndBody()
    advisor = advmod.current_advisor()
    tech = techmod.current_technician()
    tech_id = (body.tech_id or "").strip()
    ended_at = (body.ended_at or "").strip()
    shift_id = body.shift_id
    if advisor and (tech_id or shift_id is not None):
        pass
    elif tech:
        tech_id = tech.id
    else:
        raise HTTPException(401, "Log in as a technician or advisor")
    try:
        return shift_off.end_shift(
            store, tech_id=tech_id, shift_id=shift_id, ended_at=ended_at
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/shifts")
def engine_list_shifts(
    tech_id: str = "",
    day_from: str = "",
    day_to: str = "",
    limit: int = 200,
) -> dict[str, Any]:
    from carro.core import shift_offline as shift_off

    if not advmod.current_advisor() and not techmod.current_technician():
        raise HTTPException(401, "Login required")
    return shift_off.list_shifts_merged(
        store,
        tech_id=tech_id,
        day_from=day_from,
        day_to=day_to,
        limit=limit,
    )


@app.patch("/shifts/{shift_id}")
def engine_patch_shift(
    shift_id: int, body: ShiftPatchBody | None = None
) -> dict[str, Any]:
    from carro.core import shift_offline as shift_off
    from carro.storage.remote import RemoteClient

    body = body or ShiftPatchBody()
    advisor = advmod.current_advisor()
    tech = techmod.current_technician()
    if not advisor and not tech:
        raise HTTPException(401, "Log in as a technician or advisor")

    target = shift_off.resolve_shift(store, int(shift_id))
    if not target:
        # Try refresh from remote list once
        remote = RemoteClient()
        if remote.enabled:
            try:
                listed = remote.list_shifts(limit=2000).get("shifts") or []
                hit = next(
                    (s for s in listed if int(s.get("id") or 0) == int(shift_id)),
                    None,
                )
                if isinstance(hit, dict):
                    target = shift_off.upsert_from_remote(store, hit)
            except Exception:
                target = None
    if not target:
        raise HTTPException(404, "Punch not found")

    if advisor:
        edited_by = advisor.name or advisor.id or "advisor"
    else:
        assert tech is not None
        pin = (body.admin_pin or "").strip()
        if not pin or not techmod.verify_admin_pin(pin):
            raise HTTPException(403, "Admin PIN required to edit your punch times")
        if str(target.get("tech_id") or "") != str(tech.id):
            raise HTTPException(403, "You can only edit your own punches")
        edited_by = f"{tech.name} (admin PIN)"

    try:
        local = shift_off.patch_shift_local(
            store,
            int(shift_id),
            started_at=body.started_at,
            ended_at=body.ended_at,
            clear_end=bool(body.clear_end),
            day=body.day,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    remote = RemoteClient()
    server_id = local.get("server_id")
    if remote.enabled and server_id:
        try:
            out = remote.update_shift(
                int(server_id),
                started_at=body.started_at,
                ended_at=body.ended_at,
                clear_end=bool(body.clear_end),
                day=body.day,
                edited_by=edited_by,
            )
            shift = out.get("shift") if isinstance(out, dict) else None
            if isinstance(shift, dict):
                synced = shift_off.upsert_from_remote(store, shift)
                return {"ok": True, "shift": synced, "synced": True}
        except RuntimeError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception:
            return {"ok": True, "shift": local, "synced": False, "pending": True}
    return {"ok": True, "shift": local, "synced": False}


@app.delete("/shifts/{shift_id}")
def engine_delete_shift(shift_id: int) -> dict[str, Any]:
    from carro.core import shift_offline as shift_off
    from carro.storage.remote import RemoteClient

    if not advmod.current_advisor():
        raise HTTPException(401, "Only an advisor can delete punches")
    try:
        out = shift_off.delete_shift_local(store, int(shift_id))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    remote = RemoteClient()
    if remote.enabled and int(shift_id) > 0:
        try:
            return remote.delete_shift(int(shift_id))
        except RuntimeError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception:
            return {**out, "synced": False, "pending": True}
    return out

@app.get("/reports/weekly")
def engine_weekly_report(week_start: str = "") -> dict[str, Any]:
    from carro.core.weekly_reports import build_weekly_tech_report, parse_week_start

    start = parse_week_start(week_start or None)
    start_s = start.isoformat()
    by_id: dict[str, RepairOrder] = {o.id: o for o in store.list_orders()}
    remote = RemoteClient()
    shifts: list[dict[str, Any]] = []
    snapshot = None
    if remote.enabled:
        try:
            for raw in remote.list_ros():
                try:
                    order = RepairOrder.from_dict(raw)
                except Exception:
                    continue
                local = by_id.get(order.id)
                if local is None or (order.updated or "") >= (local.updated or ""):
                    by_id[order.id] = order
        except Exception:
            pass
        try:
            from carro.core.weekly_reports import week_end_saturday

            end_s = week_end_saturday(start).isoformat()
            shifts = list(
                remote.list_shifts(day_from=start_s, day_to=end_s, limit=2000).get(
                    "shifts"
                )
                or []
            )
        except Exception:
            shifts = []
        try:
            snapshot = remote.get_weekly_report_snapshot(start_s).get("snapshot")
        except Exception:
            snapshot = None
    live = build_weekly_tech_report(
        list(by_id.values()),
        shifts,
        week_start=start,
        include_live=True,
    )
    return {"live": live, "snapshot": snapshot, "week_start": start_s}


def _orders_and_shifts_for_week(week_start: str = "") -> tuple[list[RepairOrder], list[dict[str, Any]], str]:
    from carro.core.weekly_reports import parse_week_start, week_end_saturday

    start = parse_week_start(week_start or None)
    start_s = start.isoformat()
    by_id: dict[str, RepairOrder] = {o.id: o for o in store.list_orders()}
    remote = RemoteClient()
    shifts: list[dict[str, Any]] = []
    if remote.enabled:
        try:
            for raw in remote.list_ros():
                try:
                    order = RepairOrder.from_dict(raw)
                except Exception:
                    continue
                local = by_id.get(order.id)
                if local is None or (order.updated or "") >= (local.updated or ""):
                    by_id[order.id] = order
        except Exception:
            pass
        try:
            end_s = week_end_saturday(start).isoformat()
            shifts = list(
                remote.list_shifts(day_from=start_s, day_to=end_s, limit=2000).get(
                    "shifts"
                )
                or []
            )
        except Exception:
            shifts = []
    return list(by_id.values()), shifts, start_s


@app.get("/reports/efficiency")
def engine_efficiency_report(week_start: str = "") -> dict[str, Any]:
    from carro.core.weekly_reports import build_weekly_efficiency_report, parse_week_start

    orders, shifts, start_s = _orders_and_shifts_for_week(week_start)
    report = build_weekly_efficiency_report(
        orders,
        shifts,
        week_start=parse_week_start(week_start or None),
        include_live=True,
    )
    return {"report": report, "week_start": start_s}


@app.get("/reports/weekly/archive")
def engine_weekly_archive(limit: int = 52) -> dict[str, Any]:
    remote = RemoteClient()
    if not remote.enabled:
        return {"weeks": [], "server_required": True}
    try:
        return remote.list_weekly_report_archive(limit=limit)
    except Exception as exc:
        raise HTTPException(502, f"Archive unavailable: {exc}") from exc


@app.put("/reports/weekly/{week_start}")
def engine_save_weekly_report(week_start: str) -> dict[str, Any]:
    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Log in as an advisor to save weekly reports")
    remote = RemoteClient()
    if not remote.enabled:
        raise HTTPException(503, "Shop server_url required to archive weekly reports")
    from carro.core.weekly_reports import (
        build_weekly_efficiency_report,
        build_weekly_tech_report,
        parse_week_start,
    )

    orders, shifts, _start_s = _orders_and_shifts_for_week(week_start)
    start = parse_week_start(week_start or None)
    live = build_weekly_tech_report(
        orders, shifts, week_start=start, include_live=False
    )
    efficiency = build_weekly_efficiency_report(
        orders, shifts, week_start=start, include_live=False
    )
    payload = dict(live)
    payload["efficiency"] = efficiency
    try:
        return remote.save_weekly_report(
            live["week_start"],
            week_end=live["week_end"],
            payload=payload,
            created_by=advisor.name,
            created_by_id=advisor.id,
        )
    except Exception as exc:
        raise HTTPException(502, f"Could not save report: {exc}") from exc


@app.post("/technicians/{tech_id}/queue")
def set_technician_queue_route(tech_id: str, body: TechQueueBody) -> dict[str, Any]:
    """Advisor numbers a tech's today or next-day path by RO (car) order."""
    from carro.core.queue_lanes import set_tech_queue

    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Only an advisor can reorder technician queues")
    tid = (tech_id or "").strip()
    tname = (body.tech_name or "").strip()
    if not tid and not tname:
        raise HTTPException(400, "tech_id required")
    if tid:
        match = next((t for t in techmod.list_technicians() if t.id == tid), None)
        if match:
            tname = tname or match.name
    try:
        touched = set_tech_queue(
            store,
            tech_id=tid,
            tech_name=tname,
            lane=body.lane,
            ro_ids=list(body.ro_ids or []),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    for o in touched:
        store.save(o)
        _push_ro(o, actor=advisor.name, actor_id=advisor.id)
    return {
        "ok": True,
        "tech_id": tid,
        "tech_name": tname,
        "lane": body.lane,
        "ro_ids": [r for r in (body.ro_ids or []) if str(r).strip()],
        "updated": [o.id for o in touched],
    }


def _maybe_sync_rosters() -> None:
    """Refresh local tech/advisor rosters from the shop server (throttled)."""
    import time

    now = time.monotonic()
    last = getattr(_maybe_sync_rosters, "_at", 0.0)
    if now - last < 15:
        return
    _maybe_sync_rosters._at = now  # type: ignore[attr-defined]
    try:
        from carro.core.tech_ui import sync_roster_with_server
        from carro.storage.remote import RemoteClient

        if RemoteClient().enabled:
            sync_roster_with_server()
    except Exception:
        pass


@app.get("/technicians")
def list_technicians() -> dict[str, Any]:
    _maybe_sync_rosters()
    techs = [{"id": t.id, "name": t.name} for t in techmod.list_technicians()]
    return {"technicians": techs}


@app.post("/technicians")
def add_technician(body: AddTechBody) -> dict[str, str]:
    if techmod.admin_unlocked():
        pass
    elif advmod.current_advisor():
        # Advisor desk may add technicians (still need unique PINs)
        pass
    elif body.admin_pin and techmod.verify_admin_pin(body.admin_pin):
        pass
    else:
        raise HTTPException(403, "Admin unlock, advisor login, or correct admin PIN required")
    try:
        tech = techmod.add_technician(body.name, body.pin)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _push_technicians()
    return {"id": tech.id, "name": tech.name}


def _push_technicians() -> None:
    try:
        remote = RemoteClient()
        if remote.enabled:
            payload = techmod.roster_for_sync()
            payload["replace"] = True
            remote.put_technicians(payload)
    except Exception:
        pass


def _push_advisors() -> None:
    try:
        remote = RemoteClient()
        if remote.enabled:
            payload = advmod.roster_for_sync()
            payload["replace"] = True
            remote.put_advisors(payload)
    except Exception:
        pass


def _push_suppliers() -> None:
    try:
        from carro.core import suppliers as suppliersmod

        remote = RemoteClient()
        if remote.enabled:
            remote.put_suppliers(suppliersmod.roster_for_sync())
    except Exception:
        pass


def _push_part_supersessions() -> None:
    try:
        from carro.core import part_supersessions as ssmod

        remote = RemoteClient()
        if remote.enabled:
            remote.put_part_supersessions(ssmod.roster_for_sync())
    except Exception:
        pass


class SupplierBody(BaseModel):
    name: str = ""


@app.get("/suppliers")
def list_suppliers_route() -> dict[str, Any]:
    from carro.core import suppliers as suppliersmod

    roster = suppliersmod.load_roster()
    return {
        "suppliers": roster.get("suppliers") or [],
        "updated": roster.get("updated") or "",
        "count": len(roster.get("suppliers") or []),
    }


@app.post("/suppliers")
def add_supplier_route(body: SupplierBody) -> dict[str, Any]:
    from carro.core import suppliers as suppliersmod

    tech = techmod.current_technician()
    advisor = advmod.current_advisor()
    if not tech and not advisor:
        raise HTTPException(401, "Log in as a technician or advisor to manage suppliers")
    try:
        entry = suppliersmod.add_supplier(body.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _push_suppliers()
    return entry


@app.delete("/suppliers/{supplier_id}")
def delete_supplier_route(supplier_id: str) -> dict[str, Any]:
    from carro.core import suppliers as suppliersmod

    tech = techmod.current_technician()
    advisor = advmod.current_advisor()
    if not tech and not advisor:
        raise HTTPException(401, "Log in as a technician or advisor to manage suppliers")
    if not suppliersmod.remove_supplier(supplier_id):
        raise HTTPException(404, "Supplier not found")
    _push_suppliers()
    return {"ok": True, "id": supplier_id}


class PartSupersessionBody(BaseModel):
    old_number: str = ""
    new_number: str = ""
    manufacturer: str = ""
    note: str = ""


@app.get("/part-supersessions")
def list_part_supersessions_route() -> dict[str, Any]:
    from carro.core import part_supersessions as ssmod

    roster = ssmod.load_roster()
    return {
        "links": roster.get("links") or [],
        "updated": roster.get("updated") or "",
        "count": len(roster.get("links") or []),
    }


@app.post("/part-supersessions")
def add_part_supersession_route(body: PartSupersessionBody) -> dict[str, Any]:
    from carro.core import part_supersessions as ssmod

    tech = techmod.current_technician()
    advisor = advmod.current_advisor()
    if not tech and not advisor:
        raise HTTPException(401, "Log in as a technician or advisor to mark superseded parts")
    try:
        entry = ssmod.upsert_link(
            body.old_number,
            body.new_number,
            manufacturer=body.manufacturer or "",
            note=body.note or "",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _push_part_supersessions()
    return entry


@app.delete("/part-supersessions/{link_id}")
def delete_part_supersession_route(link_id: str) -> dict[str, Any]:
    from carro.core import part_supersessions as ssmod

    tech = techmod.current_technician()
    advisor = advmod.current_advisor()
    if not tech and not advisor:
        raise HTTPException(401, "Log in as a technician or advisor to manage superseded parts")
    if not ssmod.remove_link(link_id):
        raise HTTPException(404, "Supersession not found")
    _push_part_supersessions()
    return {"ok": True, "id": link_id}


class BugReportBody(BaseModel):
    title: str = ""
    description: str = ""
    severity: str = "medium"
    steps: str = ""
    client: str = ""


@app.post("/bug-reports")
def submit_bug_report_route(body: BugReportBody) -> dict[str, Any]:
    from carro.core import bug_reports as bugmod

    tech = techmod.current_technician()
    advisor = advmod.current_advisor()
    role = ""
    rid = ""
    rname = ""
    if advisor:
        role, rid, rname = "advisor", advisor.id, advisor.name
    elif tech:
        role, rid, rname = "technician", tech.id, tech.name
    client = (body.client or "").strip() or ("advisor" if advisor and not tech else "tech")
    try:
        report = bugmod.submit_report(
            title=body.title,
            description=body.description,
            severity=body.severity,
            steps=body.steps or "",
            client=client,
            reporter_role=role or "unknown",
            reporter_id=rid,
            reporter_name=rname,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "report": report}


@app.get("/bug-reports")
def list_bug_reports_route(limit: int = 50) -> dict[str, Any]:
    from carro.core import bug_reports as bugmod

    rows = bugmod.list_local(limit=limit)
    return {"reports": rows, "count": len(rows)}


@app.get("/session")
def session() -> dict[str, Any]:
    tech = techmod.current_technician()
    if not tech:
        return {"technician": None, "role": None}
    return {"technician": {"id": tech.id, "name": tech.name}, "role": "tech"}


@app.post("/session/login")
def login(body: LoginBody) -> dict[str, Any]:
    # Tech app only — reject if this PIN belongs to an advisor
    try:
        from carro.core.advisors import list_advisors
        from carro.core.technicians import verify_pin

        for adv in list_advisors():
            if verify_pin(body.pin, adv.pin_hash):
                raise HTTPException(401, "Advisor PINs cannot log into the technician app")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        tech = techmod.login_technician(body.tech_id, body.pin)
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc
    # Keep advisor session if present — same PC can run tech + advisor apps together.
    return {"technician": {"id": tech.id, "name": tech.name}, "role": "tech"}


@app.post("/session/logout")
def logout() -> dict[str, bool]:
    techmod.clear_session()
    techmod.lock_admin()
    return {"ok": True}


@app.post("/bootstrap/technician")
def bootstrap_technician(body: BootstrapBody) -> dict[str, Any]:
    """Create first technician when roster empty; optionally set global admin PIN."""
    if techmod.has_technicians():
        raise HTTPException(400, "Technicians already exist — use login")
    try:
        admin_pin = techmod.validate_pin(body.admin_pin)
        tech_pin = techmod.validate_pin(body.pin)
        if body.set_admin or not techmod.has_admin_pin():
            techmod.set_admin_pin(admin_pin)
        elif not techmod.verify_admin_pin(admin_pin):
            raise ValueError("Incorrect admin PIN")
        tech = techmod.add_technician(
            body.name, tech_pin, admin_pin_plain=admin_pin
        )
        techmod.unlock_admin(admin_pin)
        techmod.login_technician(tech.id, tech_pin)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _push_technicians()
    return {
        "technician": {"id": tech.id, "name": tech.name},
        "has_admin_pin": True,
        "role": "tech",
    }


@app.get("/advisors")
def list_advisors_route() -> dict[str, Any]:
    _maybe_sync_rosters()
    advisors = [
        {
            "id": a.id,
            "name": a.name,
            "working_privilege": bool(a.working_privilege),
        }
        for a in advmod.list_advisors()
    ]
    return {
        "advisors": advisors,
        "has_admin_pin": techmod.has_admin_pin(),
        "empty": not advisors,
    }


class WorkingPrivilegeBody(BaseModel):
    working_privilege: bool = False
    admin_pin: str = ""


@app.put("/advisors/{advisor_id}/working-privilege")
def set_working_privilege_route(advisor_id: str, body: WorkingPrivilegeBody) -> dict[str, Any]:
    """Toggle bay working privilege (job timers; not tech day clock)."""
    if advmod.current_advisor():
        pass
    elif techmod.admin_unlocked():
        pass
    elif body.admin_pin and techmod.verify_admin_pin(body.admin_pin):
        pass
    else:
        raise HTTPException(403, "Advisor login or admin PIN required")
    try:
        advisor = advmod.set_working_privilege(advisor_id, bool(body.working_privilege))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    _push_advisors()
    return {
        "id": advisor.id,
        "name": advisor.name,
        "working_privilege": bool(advisor.working_privilege),
    }


@app.post("/advisors")
def add_advisor_route(body: AddAdvisorBody) -> dict[str, str]:
    # Only while advisor session active, or admin unlock / admin PIN for bootstrap edge
    if advmod.current_advisor():
        pass
    elif techmod.admin_unlocked():
        pass
    elif body.admin_pin and techmod.verify_admin_pin(body.admin_pin):
        pass
    else:
        raise HTTPException(403, "Advisor login or admin PIN required")
    try:
        advisor = advmod.add_advisor(
            body.name,
            body.pin,
            admin_pin_plain=body.admin_pin,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _push_advisors()
    return {"id": advisor.id, "name": advisor.name}


@app.post("/bootstrap/advisor")
def bootstrap_advisor(body: BootstrapBody) -> dict[str, Any]:
    try:
        advisor = advmod.bootstrap_first_advisor(
            body.name,
            body.pin,
            admin_pin=body.admin_pin,
            set_admin=body.set_admin or not techmod.has_admin_pin(),
        )
        advmod.login_advisor(advisor.id, body.pin)
        techmod.clear_session()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _push_advisors()
    _push_technicians()  # admin pin may have been set on tech roster
    return {
        "advisor": {"id": advisor.id, "name": advisor.name},
        "has_admin_pin": True,
        "role": "advisor",
    }


@app.get("/advisor/session")
def advisor_session() -> dict[str, Any]:
    advisor = advmod.current_advisor()
    if not advisor:
        return {"advisor": None, "role": None, "has_admin_pin": techmod.has_admin_pin()}
    return {
        "advisor": {
            "id": advisor.id,
            "name": advisor.name,
            "working_privilege": bool(advisor.working_privilege),
        },
        "role": "advisor",
        "working_privilege": bool(advisor.working_privilege),
        "has_admin_pin": techmod.has_admin_pin(),
    }


@app.post("/advisor/session/login")
def advisor_login(body: AdvisorLoginBody) -> dict[str, Any]:
    # Reject technician PINs on advisor app
    try:
        if techmod.find_tech_by_pin(body.pin):
            raise HTTPException(401, "Technician PINs cannot log into the advisor app")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        advisor = advmod.login_advisor(body.advisor_id, body.pin)
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc
    # Keep technician session if present — messaging / bay work stay on the tech identity.
    return {
        "advisor": {
            "id": advisor.id,
            "name": advisor.name,
            "working_privilege": bool(advisor.working_privilege),
        },
        "role": "advisor",
        "working_privilege": bool(advisor.working_privilege),
    }


@app.post("/advisor/session/logout")
def advisor_logout() -> dict[str, bool]:
    advisor = advmod.current_advisor()
    if advisor:
        try:
            remote = RemoteClient()
            if remote.enabled:
                remote.clear_advisor_presence(advisor.id)
        except Exception:
            pass
    advmod.clear_session()
    techmod.lock_admin()
    return {"ok": True}


class AdvisorPresenceBody(BaseModel):
    client_host: str = ""


@app.post("/advisors/presence/heartbeat")
def advisor_presence_heartbeat(body: AdvisorPresenceBody | None = None) -> dict[str, Any]:
    body = body or AdvisorPresenceBody()
    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Advisor login required")
    remote = RemoteClient()
    if not remote.enabled:
        return {"ok": True, "synced": False, "reason": "no_server"}
    try:
        import platform

        remote.post_advisor_presence(
            advisor_id=advisor.id,
            name=advisor.name,
            client_host=(body.client_host or platform.node() or ""),
        )
        return {"ok": True, "synced": True}
    except Exception as exc:
        return {"ok": True, "synced": False, "reason": str(exc)[:200]}


@app.get("/advisors/presence")
def advisor_presence_list() -> dict[str, Any]:
    """Online advisors with At desk / Away (on a bay job)."""
    from carro.core.assignment import matches_tech

    remote = RemoteClient()
    online: list[dict[str, Any]] = []
    if remote.enabled:
        try:
            data = remote.list_advisor_presence(within_seconds=90)
            online = list(data.get("advisors") or [])
        except Exception:
            online = []

    # Local fallback: at least show current advisor
    me = advmod.current_advisor()
    if me and not any(str(r.get("advisor_id")) == me.id for r in online):
        online.append(
            {
                "advisor_id": me.id,
                "name": me.name,
                "last_seen": "",
                "client_host": "",
                "local_only": True,
            }
        )

    roster_by_id = {a.id: a for a in advmod.list_advisors()}
    orders = store.list_orders()
    enriched: list[dict[str, Any]] = []
    for row in online:
        aid = str(row.get("advisor_id") or "")
        name = str(row.get("name") or "")
        adv = roster_by_id.get(aid)
        on_job_ro = ""
        on_job_item = ""
        away = False
        if adv:
            for order in orders:
                if matches_tech(
                    order.current_tech_id or "",
                    order.current_tech_name or "",
                    me_id=adv.id,
                    me_name=adv.name,
                ):
                    away = True
                    on_job_ro = order.id
                    on_job_item = order.current_item_id or ""
                    break
        enriched.append(
            {
                "advisor_id": aid,
                "name": name or (adv.name if adv else aid),
                "last_seen": row.get("last_seen") or "",
                "working_privilege": bool(adv.working_privilege) if adv else False,
                "status": "away" if away else "at_desk",
                "on_job_ro": on_job_ro,
                "on_job_item": on_job_item,
                "is_me": bool(me and me.id == aid),
            }
        )
    return {"advisors": enriched, "count": len(enriched)}


class AdminUnlockBody(BaseModel):
    admin_pin: str = Field(alias="admin_pin")


class AdminPinOptionalBody(BaseModel):
    admin_pin: str = ""


class AdminChangePinBody(BaseModel):
    admin_pin: str = Field(alias="admin_pin")
    new_pin: str = Field(alias="new_pin")


class AdminTechPinBody(BaseModel):
    tech_id: str
    new_pin: str = Field(alias="new_pin")
    admin_pin: str | None = Field(default=None, alias="admin_pin")


class AdminTechRenameBody(BaseModel):
    tech_id: str
    name: str


class AdminAdvisorPinBody(BaseModel):
    advisor_id: str
    new_pin: str = Field(alias="new_pin")
    admin_pin: str | None = Field(default=None, alias="admin_pin")


class AdminAdvisorRenameBody(BaseModel):
    advisor_id: str
    name: str


class AdminTimeBody(BaseModel):
    """Correct forgotten/mistaken clocks — advisor session, admin unlock, or admin PIN."""

    action: Literal["set", "add", "clear"]
    minutes: int | None = None
    note: str = ""
    admin_pin: str = ""


def _require_admin() -> None:
    try:
        techmod.require_admin_session()
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


def _require_admin_pin_or_session(admin_pin: str | None = None) -> None:
    """Staff changes: unlocked admin session, or one-shot admin PIN."""
    pin = (admin_pin or "").strip()
    if pin:
        if not techmod.verify_admin_pin(pin):
            raise HTTPException(403, "Incorrect admin PIN")
        return
    _require_admin()


def _time_edit_actor(admin_pin: str = "") -> str:
    """Advisor may edit time without PIN; otherwise admin session or admin PIN."""
    advisor = advmod.current_advisor()
    if advisor:
        return advisor.name or advisor.id or "advisor"
    pin = (admin_pin or "").strip()
    if pin:
        if not techmod.verify_admin_pin(pin):
            raise HTTPException(403, "Incorrect admin PIN")
        return "admin"
    try:
        techmod.require_admin_session()
    except PermissionError as exc:
        raise HTTPException(
            403, "Advisor login, admin unlock, or correct admin PIN required"
        ) from exc
    return "admin"


@app.get("/admin/session")
def admin_session() -> dict[str, Any]:
    return {
        "active": techmod.admin_unlocked(),
        "has_admin_pin": techmod.has_admin_pin(),
    }


@app.post("/admin/unlock")
def admin_unlock(body: AdminUnlockBody) -> dict[str, Any]:
    try:
        techmod.unlock_admin(body.admin_pin)
    except ValueError as exc:
        raise HTTPException(403, str(exc)) from exc
    return {"ok": True, "active": True}


@app.post("/admin/lock")
def admin_lock() -> dict[str, bool]:
    techmod.lock_admin()
    return {"ok": True}


@app.post("/admin/change-pin")
def admin_change_pin(body: AdminChangePinBody) -> dict[str, bool]:
    if not techmod.verify_admin_pin(body.admin_pin):
        raise HTTPException(403, "Incorrect admin PIN")
    try:
        techmod.set_admin_pin(body.new_pin)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    techmod.unlock_admin(body.new_pin)
    _push_technicians()
    return {"ok": True}


@app.post("/admin/technicians/{tech_id}/reset-pin")
def admin_reset_tech_pin(tech_id: str, body: AdminTechPinBody) -> dict[str, bool]:
    _require_admin()
    try:
        techmod.update_technician_pin(tech_id, body.new_pin)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _push_technicians()
    return {"ok": True}


@app.post("/admin/technicians/{tech_id}/rename")
def admin_rename_tech(tech_id: str, body: AdminTechRenameBody) -> dict[str, bool]:
    _require_admin()
    try:
        techmod.rename_technician(tech_id, body.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _push_technicians()
    return {"ok": True}


@app.delete("/admin/technicians/{tech_id}")
def admin_remove_tech(
    tech_id: str, body: AdminPinOptionalBody | None = None
) -> dict[str, bool]:
    _require_admin_pin_or_session(body.admin_pin if body else None)
    try:
        techmod.remove_technician(tech_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _push_technicians()
    return {"ok": True}


@app.delete("/admin/advisors/{advisor_id}")
def admin_remove_advisor(
    advisor_id: str, body: AdminPinOptionalBody | None = None
) -> dict[str, bool]:
    _require_admin_pin_or_session(body.admin_pin if body else None)
    try:
        advmod.remove_advisor(advisor_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _push_advisors()
    return {"ok": True}


@app.post("/admin/advisors/{advisor_id}/reset-pin")
def admin_reset_advisor_pin(advisor_id: str, body: AdminAdvisorPinBody) -> dict[str, bool]:
    _require_admin()
    try:
        advmod.update_advisor_pin(advisor_id, body.new_pin)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _push_advisors()
    return {"ok": True}


@app.post("/admin/advisors/{advisor_id}/rename")
def admin_rename_advisor(advisor_id: str, body: AdminAdvisorRenameBody) -> dict[str, bool]:
    _require_admin()
    try:
        advmod.rename_advisor(advisor_id, body.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _push_advisors()
    return {"ok": True}


@app.post("/ros/{ro_id}/work-items/{item_id}/time/admin")
def admin_work_item_time(ro_id: str, item_id: str, body: AdminTimeBody) -> dict[str, Any]:
    """Edit item worked time (mistaken/forgotten clocks)."""
    actor = _time_edit_actor(body.admin_pin)
    from carro.core.work_items import (
        add_worked_minutes,
        admin_clear_time_log,
        admin_set_worked_minutes,
    )

    order = _require_order(ro_id)
    try:
        if body.action == "set":
            mins = int(body.minutes if body.minutes is not None else -1)
            if mins < 0:
                raise HTTPException(400, "minutes required for set")
            admin_set_worked_minutes(
                order,
                item_id,
                mins,
                note=body.note or "",
                actor=actor,
            )
        elif body.action == "add":
            mins = int(body.minutes or 0)
            if mins == 0:
                raise HTTPException(400, "minutes must be non-zero")
            if mins < 0:
                items = order.work_items or []
                cur = next(
                    (
                        int(it.get("worked_minutes") or 0)
                        for it in items
                        if isinstance(it, dict) and it.get("id") == item_id
                    ),
                    0,
                )
                admin_set_worked_minutes(
                    order,
                    item_id,
                    max(0, cur + mins),
                    note=body.note or f"{actor} adjust {mins}m",
                    actor=actor,
                )
            else:
                add_worked_minutes(
                    order,
                    item_id,
                    mins,
                    tech_id="",
                    tech_name=actor,
                    note=body.note or "time correction",
                    source="admin",
                )
        elif body.action == "clear":
            admin_clear_time_log(
                order,
                item_id,
                note=body.note or "",
                actor=actor,
            )
        else:
            raise HTTPException(400, f"Unknown action: {body.action}")
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.get("/ros")
def list_ros(q: str = "") -> dict[str, Any]:
    if q.strip():
        orders = store.search(q.strip())
    else:
        orders = store.list_orders(limit=50)
    return {"orders": [o.to_dict() for o in orders]}


@app.get("/ros/extended-search")
def extended_search(
    q: str = "",
    name: str = "",
    vin: str = "",
    plate: str = "",
    make: str = "",
    model: str = "",
    year: str = "",
    status: str = "",
) -> dict[str, Any]:
    """
    Search local cache + shop server archive (for billed-out history past local keep).
    Server-only hits are cached locally so the RO editor can open them.
    """
    if not any(
        s.strip() for s in (q, name, vin, plate, make, model, year, status)
    ):
        raise HTTPException(400, "Enter at least one search field")
    remote = RemoteClient()
    local_hits = store.search(
        q,
        make=make,
        model=model,
        year=year,
        name=name,
        vin=vin,
        status=status,
        plate=plate,
    )
    local_ids = {o.id for o in local_hits}
    sources: dict[str, str] = {o.id: "local" for o in local_hits}
    remote_only = 0
    if remote.enabled:
        try:
            raw = remote.search_ros(
                q,
                make=make,
                model=model,
                year=year,
                name=name,
                vin=vin,
                status=status,
                plate=plate,
            )
            for row in raw:
                order = RepairOrder.from_dict(row)
                if order.id in local_ids:
                    sources[order.id] = "both"
                    continue
                store.save(order, mark_pending_sync=False)
                local_hits.append(order)
                local_ids.add(order.id)
                sources[order.id] = "server"
                remote_only += 1
        except Exception as exc:
            raise HTTPException(502, f"Server search failed: {exc}") from exc
    return {
        "orders": [o.to_dict() for o in local_hits],
        "remote_enabled": remote.enabled,
        "remote_only": remote_only,
        "sources": sources,
    }


@app.get("/calendar")
def calendar_range(start: str = "", end: str = "") -> dict[str, Any]:
    """Week/month appointments + parts ordered/received overlay. Advisor desk."""
    from carro.core.appointments import calendar_payload

    _require_advisor_for_desk(detail="Log in as an advisor to open the calendar")
    return calendar_payload(store, start=start, end=end)


@app.post("/appointments")
def upsert_appointment_route(body: AppointmentBody) -> dict[str, Any]:
    from carro.core.appointments import upsert_appointment

    advisor = _require_advisor_for_desk(detail="Log in as an advisor to book appointments")
    try:
        appt = upsert_appointment(
            store,
            body.model_dump(),
            actor=advisor.name,
            actor_id=advisor.id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return appt


@app.post("/appointments/{appt_id}/archive")
def archive_appointment_route(appt_id: str, body: AppointmentArchiveBody) -> dict[str, Any]:
    from carro.core.appointments import archive_appointment

    _require_advisor_for_desk(detail="Log in as an advisor to archive appointments")
    try:
        return archive_appointment(store, appt_id, status=body.status)
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(code, msg) from e


@app.post("/appointments/{appt_id}/confirm")
def confirm_appointment_route(appt_id: str, body: AppointmentConfirmBody) -> dict[str, Any]:
    from carro.core.appointments import set_confirm_call

    advisor = _require_advisor_for_desk(detail="Log in as an advisor to confirm appointments")
    try:
        return set_confirm_call(
            store,
            appt_id,
            body.outcome,
            actor=advisor.name,
            actor_id=advisor.id,
        )
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(code, msg) from e


@app.post("/appointments/{appt_id}/restore")
def restore_appointment_route(appt_id: str) -> dict[str, Any]:
    from carro.core.appointments import restore_appointment

    _require_advisor_for_desk(detail="Log in as an advisor to restore appointments")
    try:
        return restore_appointment(store, appt_id)
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(code, msg) from e


@app.post("/appointments/{appt_id}/convert")
def convert_appointment_route(appt_id: str) -> dict[str, Any]:
    from carro.core.appointments import convert_appointment_to_ro

    advisor = _require_advisor_for_desk(detail="Log in as an advisor to make a work order")
    try:
        appt, order = convert_appointment_to_ro(
            store,
            appt_id,
            actor=advisor.name,
            actor_id=advisor.id,
        )
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(code, msg) from e
    _push_ro(order, actor=advisor.name, actor_id=advisor.id)
    return {"appointment": appt, "order": order.to_dict()}


@app.get("/service-plans/due")
def service_plans_due() -> dict[str, Any]:
    from carro.core.service_plans import due_call_list

    _require_advisor_for_desk(detail="Log in as an advisor to view service dues")
    return {"due_calls": due_call_list(store)}


@app.get("/service-plans")
def list_service_plans_route() -> dict[str, Any]:
    _require_advisor_for_desk(detail="Log in as an advisor to open service plans")
    return {"plans": store.list_service_plans()}


@app.post("/service-plans")
def upsert_service_plan_route(body: ServicePlanBody) -> dict[str, Any]:
    from carro.core.service_plans import upsert_plan

    advisor = _require_advisor_for_desk(detail="Log in as an advisor to edit service plans")
    payload = body.model_dump()
    if payload.get("lines") is None:
        payload.pop("lines", None)
    try:
        return upsert_plan(store, payload, actor=advisor.name, actor_id=advisor.id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/service-plans/{plan_id}")
def get_service_plan_route(plan_id: str) -> dict[str, Any]:
    _require_advisor_for_desk(detail="Log in as an advisor to open service plans")
    plan = store.get_service_plan(plan_id)
    if not plan:
        raise HTTPException(404, f"Service plan not found: {plan_id}")
    return plan


@app.delete("/service-plans/{plan_id}")
def delete_service_plan_route(plan_id: str) -> dict[str, Any]:
    _require_advisor_for_desk(detail="Log in as an advisor to edit service plans")
    if not store.delete_service_plan(plan_id):
        raise HTTPException(404, f"Service plan not found: {plan_id}")
    return {"ok": True, "id": plan_id}


@app.post("/service-plans/{plan_id}/lines")
def upsert_service_plan_line_route(plan_id: str, body: ServicePlanLineBody) -> dict[str, Any]:
    from carro.core.service_plans import upsert_line

    _require_advisor_for_desk(detail="Log in as an advisor to edit service plans")
    try:
        return upsert_line(store, plan_id, body.model_dump(), delete=body.delete)
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(code, msg) from e


@app.post("/service-plans/{plan_id}/lines/{line_id}/call")
def service_plan_line_call_route(
    plan_id: str, line_id: str, body: ServicePlanCallBody
) -> dict[str, Any]:
    from carro.core.service_plans import set_line_call

    advisor = _require_advisor_for_desk(detail="Log in as an advisor to log service-plan calls")
    try:
        return set_line_call(
            store,
            plan_id,
            line_id,
            body.outcome,
            actor=advisor.name,
            actor_id=advisor.id,
        )
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(code, msg) from e


@app.post("/ros")
def create_ro(body: CreateRoBody | None = None) -> dict[str, Any]:
    order = store.create()
    tech = techmod.current_technician()
    if tech:
        order.technician_id = tech.id
        order.technician_name = tech.name
        store.save(order)
    # Prefer the calling app's role when both sessions exist on a shared engine.
    prefer = (body.prefer_actor if body else "advisor") or "advisor"
    who, who_id = _actor_from(tech, advmod.current_advisor(), prefer=prefer)
    _push_ro(order, actor=who, actor_id=who_id)
    return order.to_dict()


@app.get("/ros/{ro_id}")
def get_ro(ro_id: str) -> dict[str, Any]:
    return _require_order(ro_id).to_dict()


@app.put("/ros/{ro_id}")
def put_ro(ro_id: str, body: dict[str, Any]) -> dict[str, Any]:
    from carro_server.ro_merge import merge_repair_order

    body = dict(body)
    body["id"] = ro_id
    incoming = RepairOrder.from_dict(body)
    # Stamp tech if empty
    tech = techmod.current_technician()
    advisor = advmod.current_advisor()
    if tech and not incoming.technician_id:
        incoming.technician_id = tech.id
        incoming.technician_name = tech.name
    current = store.get(ro_id)
    if current is not None:
        who, _who_id = _actor_from(tech, advisor)
        merged = merge_repair_order(
            server=current.to_dict(),
            incoming=incoming.to_dict(),
            base_updated=str(body.get("updated") or ""),
            actor=who,
        )
        order = RepairOrder.from_dict(merged)
    else:
        order = incoming
    store.save(order)
    _push_ro(order)
    return (store.get(order.id) or order).to_dict()


class WorkItemBody(BaseModel):
    id: str | None = None
    concern: str | None = None
    notes: str | None = None
    private_notes: str | None = None
    item_type: str | None = None
    status: str | None = None
    priority: int | None = None
    # Advisor desk: assign on create (empty string = unassigned)
    assign_to_id: str | None = None
    assign_to_name: str | None = None
    service_plan_enroll: str | None = None
    service_plan_id: str | None = None
    service_plan_line_id: str | None = None


class WorkItemMergeBody(BaseModel):
    target_id: str
    source_ids: list[str] = []
    reason: str = ""


class FoundIssueComposeBody(BaseModel):
    item_id: str | None = None


class FoundIssueCreateBody(BaseModel):
    description: str
    notes: str = ""
    source_work_item_id: str | None = None
    finish_compose: bool = True
    # draft (default) = save for later batch send; pending = notify advisor immediately
    status: str = "draft"


class FoundIssueUpdateBody(BaseModel):
    """Edit a draft found issue before send-to-advisor."""

    description: str | None = None
    notes: str | None = None


class FoundIssueSubmitBody(BaseModel):
    """Promote draft found issues to pending. Empty ids = all drafts on the RO."""

    ids: list[str] = []


class FoundIssueApproveBody(BaseModel):
    item_type: str = "repair"
    assign_to_id: str = ""
    assign_to_name: str = ""


class FoundIssueDeclineBody(BaseModel):
    reason: str = "customer_declined"


class PartBody(BaseModel):
    description: str = ""
    part_number: str = ""
    oem_part_number: str = ""
    manufacturer: str | None = None
    brand: str = ""
    supplier: str = ""
    superseded_by: str = ""
    supersedes: str = ""


class PartPatchBody(BaseModel):
    description: str | None = None
    part_number: str | None = None
    oem_part_number: str | None = None
    manufacturer: str | None = None
    brand: str | None = None
    supplier: str | None = None
    superseded_by: str | None = None
    supersedes: str | None = None
    status: str | None = None
    wrong_note: str = ""


class WorkItemTimeBody(BaseModel):
    """Shop-only efficiency time on a work item (not billed hours)."""

    action: Literal["add", "start", "stop", "checkpoint"]
    minutes: int | None = None
    note: str = ""


class AssignRoBody(BaseModel):
    assigned_to_id: str = ""
    assigned_to_name: str = ""
    status: str | None = None
    item_id: str | None = None
    due_eod: bool | None = None


class CurrentTaskBody(BaseModel):
    """Claim current bay work on a specific work item (item_id required when active)."""

    active: bool = True
    item_id: str | None = None
    override: bool = False


class QueueActionBody(BaseModel):
    """Queue/current actions. Item actions require item_id (work item, not RO)."""

    action: Literal[
        "add",
        "remove",
        "complete",
        "complete_item",
        "billed_out",
        "canceled",
        "no_call_no_show",
        "reopen",
        "waiting_parts",
        "request_parts",
        "item_waiting_parts",
        "waiting_customer",
        "request_approval",
        "item_waiting_customer",
        "item_release_wait",
        "item_return_to_requester",
        "complete_with",
    ]
    item_id: str | None = None
    with_item_id: str | None = None
    also_item_ids: list[str] | None = None
    also_complete_timed: bool = False


class RoFlagsBody(BaseModel):
    waiter: bool | None = None
    urgent: bool | None = None


class WorkItemQueueBody(BaseModel):
    """Advisor sets queue lane (daily / next_day / long_term)."""

    lane: Literal["daily", "next_day", "long_term"]
    approve_request: bool = False


class WorkItemCarTurnBody(BaseModel):
    turn: int


class NextDayRequestBody(BaseModel):
    note: str = ""


class NextDayRequestDecisionBody(BaseModel):
    approve: bool = True


class TechQueueBody(BaseModel):
    """Advisor restacks a tech's today or next-day cars (RO groups)."""

    lane: Literal["daily", "next_day"] = "daily"
    ro_ids: list[str] = []
    tech_name: str = ""


@app.get("/assigned")
def assigned_board() -> dict[str, Any]:
    """Assigned Work board: mine, other techs, unassigned (local + server when configured)."""
    from carro.core.assignment import build_assigned_board
    from carro.core.queue_lanes import rollover_all_orders

    tech = techmod.current_technician()
    by_id: dict[str, RepairOrder] = {o.id: o for o in store.list_orders()}
    remote = RemoteClient()
    source = "local"
    if remote.enabled:
        try:
            for raw in remote.list_ros():
                try:
                    order = RepairOrder.from_dict(raw)
                except Exception:
                    continue
                local = by_id.get(order.id)
                if local is None or (order.updated or "") >= (local.updated or ""):
                    by_id[order.id] = order
            source = "local+server"
        except Exception:
            source = "local"
    # Local midnight: next_day → today (do not auto-park unfinished daily).
    local_ids = {o.id for o in store.list_orders()}
    changed = rollover_all_orders(
        [o for o in by_id.values() if o.id in local_ids]
    )
    if changed:
        from carro.core.queue_lanes import rebalance_after_rollover

        rolled = {o.id: o for o in changed}
        for order in rebalance_after_rollover(store, changed):
            rolled[order.id] = order
        changed = list(rolled.values())
    for order in changed:
        store.save(order)
        _push_ro(order)
        by_id[order.id] = order
    board = build_assigned_board(
        list(by_id.values()),
        tech_id=tech.id if tech else "",
        tech_name=tech.name if tech else "",
    )
    # Privileged advisors see "mine" for items assigned to them
    advisor = advmod.current_advisor()
    if advisor and advmod.has_working_privilege(advisor) and not tech:
        board = build_assigned_board(
            list(by_id.values()),
            tech_id=advisor.id,
            tech_name=advisor.name,
        )
        board["worker_role"] = "advisor"
    board["source"] = source
    # Deliver any next-day plans that became due at 8:00 local.
    try:
        _flush_day_plan_next_day()
    except Exception:
        pass
    return board


class DayPlanSendBody(BaseModel):
    """Empty tech_ids = send to all techs with a dirty day/next-day path."""

    tech_ids: list[str] = []


class DayPlanStageBody(BaseModel):
    ro_id: str
    item_id: str
    tech_id: str
    tech_name: str = ""
    lane: str = "daily"
    concern: str = ""
    vehicle: str = ""
    customer: str = ""


class DayPlanUnstageBody(BaseModel):
    ro_id: str
    item_id: str


def _board_orders_for_day_plan() -> list[RepairOrder]:
    by_id: dict[str, RepairOrder] = {o.id: o for o in store.list_orders()}
    remote = RemoteClient()
    if remote.enabled:
        try:
            for raw in remote.list_ros():
                try:
                    order = RepairOrder.from_dict(raw)
                except Exception:
                    continue
                local = by_id.get(order.id)
                if local is None or (order.updated or "") >= (local.updated or ""):
                    by_id[order.id] = order
        except Exception:
            pass
    return list(by_id.values())


def _flush_day_plan_next_day() -> list[dict[str, Any]]:
    from carro.core.day_plans import flush_due_next_day_sends

    return flush_due_next_day_sends(notify=_notify_tech_message)


@app.get("/day-plan")
def get_day_plan() -> dict[str, Any]:
    """Advisor day plan: dirty tech paths + pending next-day sends (8am)."""
    from carro.core.assignment import build_assigned_board
    from carro.core.day_plans import build_day_plan_view

    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Log in as an advisor to view the day plan")
    try:
        _flush_day_plan_next_day()
    except Exception:
        pass
    board = build_assigned_board(_board_orders_for_day_plan())
    return build_day_plan_view(board)


@app.post("/day-plan/stage")
def stage_day_plan_route(body: DayPlanStageBody) -> dict[str, Any]:
    """Queue intent for a tech Today/Next day without assigning yet."""
    from carro.core.assignment import build_assigned_board
    from carro.core.day_plans import build_day_plan_view, stage_item

    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Log in as an advisor to stage the day plan")
    try:
        entry = stage_item(
            ro_id=body.ro_id,
            item_id=body.item_id,
            tech_id=body.tech_id,
            tech_name=body.tech_name,
            lane=body.lane,
            concern=body.concern,
            vehicle=body.vehicle,
            customer=body.customer,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    board = build_assigned_board(_board_orders_for_day_plan())
    return {"ok": True, "staged": entry, "view": build_day_plan_view(board)}


@app.post("/day-plan/unstage")
def unstage_day_plan_route(body: DayPlanUnstageBody) -> dict[str, Any]:
    """Clear staging for one work item."""
    from carro.core.assignment import build_assigned_board
    from carro.core.day_plans import build_day_plan_view, unstage_item

    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Log in as an advisor to unstage the day plan")
    try:
        removed = unstage_item(ro_id=body.ro_id, item_id=body.item_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    board = build_assigned_board(_board_orders_for_day_plan())
    return {"ok": True, "removed": removed, "view": build_day_plan_view(board)}


@app.post("/day-plan/send")
def send_day_plan_route(body: DayPlanSendBody) -> dict[str, Any]:
    """Apply staged plans, then send Today's now / queue Next-day until 08:00 local."""
    from carro.core.assignment import build_assigned_board
    from carro.core.day_plans import send_day_plans

    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Log in as an advisor to send the day plan")

    def _board() -> dict[str, Any]:
        return build_assigned_board(_board_orders_for_day_plan())

    board = _board()
    result = send_day_plans(
        board,
        tech_ids=list(body.tech_ids or []),
        notify=_notify_tech_message,
        advisor_id=advisor.id,
        advisor_name=advisor.name,
        store=store,
        board_builder=_board,
    )
    return {"ok": True, **result}


@app.post("/ros/{ro_id}/assign")
def assign_ro_route(ro_id: str, body: AssignRoBody) -> dict[str, Any]:
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.assignment import assign_ro, assign_work_item

    order = _require_order(ro_id)
    advisor = advmod.current_advisor()
    item_id = (getattr(body, "item_id", None) or "").strip()
    if item_id:
        if not advisor and not techmod.current_technician():
            raise HTTPException(401, "Login required")
        # Advisor may assign any item; tech path uses queue actions instead
        if not advisor:
            raise HTTPException(403, "Only an advisor can reassign work items from this endpoint")
        if not assign_work_item(
            order,
            item_id,
            tech_id=body.assigned_to_id,
            tech_name=body.assigned_to_name,
            due_eod=body.due_eod,
            store=store,
        ):
            raise HTTPException(404, "Work item not found")
        detail = f"{body.assigned_to_name or ''} ({body.assigned_to_id or ''})".strip()
        if body.due_eod:
            detail = f"{detail} · due EOD".strip(" ·")
        append_advisor_action(
            order,
            action="assigned_to_tech",
            advisor_id=advisor.id,
            advisor_name=advisor.name,
            work_item_id=item_id,
            detail=detail,
        )
    else:
        assign_ro(
            order,
            tech_id=body.assigned_to_id,
            tech_name=body.assigned_to_name,
            set_status_assigned=True,
        )
        if advisor:
            append_advisor_action(
                order,
                action="assigned_ro_to_tech",
                advisor_id=advisor.id,
                advisor_name=advisor.name,
                detail=f"{body.assigned_to_name or ''} ({body.assigned_to_id or ''})".strip(),
            )
    if body.status and body.status in (
        "open",
        "assigned",
        "in_progress",
        "waiting_parts",
        "waiting_customer",
        "done",
        "billed_out",
    ):
        from carro.core.models import now_iso

        if body.status == "done":
            from carro.core.assignment import rollup_ro_status_from_items

            # Ready-to-bill only when every active work item is done/declined
            rollup_ro_status_from_items(order)
            if (order.status or "").strip().lower() != "done":
                raise HTTPException(
                    400,
                    "RO is not ready to bill — finish or decline remaining work items first",
                )
        else:
            order.status = body.status
            if body.status == "in_progress" and not (order.started_at or "").strip():
                order.started_at = now_iso()
            if body.status == "billed_out":
                if not (order.billed_out_at or "").strip():
                    order.billed_out_at = now_iso()
                if not (order.done_at or "").strip():
                    order.done_at = now_iso()
                order.waiting_since = ""
                if advisor:
                    append_advisor_action(
                        order,
                        action="billed_out",
                        advisor_id=advisor.id,
                        advisor_name=advisor.name,
                    )
            if body.status in ("waiting_parts", "waiting_customer"):
                order.waiting_since = now_iso()
            if body.status in ("open", "assigned", "in_progress"):
                order.waiting_since = ""
    store.save(order)
    who = advisor.name if advisor else ""
    who_id = advisor.id if advisor else ""
    _push_ro(order, actor=who, actor_id=who_id)
    # Tech notify for desk assigns is batched via Day plan (POST /day-plan/send).
    return order.to_dict()


@app.post("/ros/{ro_id}/current")
def set_current_task_route(ro_id: str, body: CurrentTaskBody) -> dict[str, Any]:
    """Claim or release current work on a work item (timer + Assigned 'working now')."""
    from carro.core.assignment import (
        clear_current_task,
        clear_tech_current_elsewhere,
        matches_tech,
        set_current_task,
    )

    tech = techmod.current_technician()
    advisor = advmod.current_advisor()
    worker_id = ""
    worker_name = ""
    if tech:
        worker_id, worker_name = tech.id, tech.name
    elif advisor and advmod.has_working_privilege(advisor):
        worker_id, worker_name = advisor.id, advisor.name
    else:
        raise HTTPException(
            401,
            "Log in as a technician, or as an advisor with working privilege, to set current work",
        )
    order = _require_order(ro_id)

    if body.active:
        for other in clear_tech_current_elsewhere(
            store.list_orders(),
            tech_id=worker_id,
            tech_name=worker_name,
            except_id=ro_id,
        ):
            store.save(other)
            _push_ro(other)
        try:
            set_current_task(
                order,
                tech_id=worker_id,
                tech_name=worker_name,
                item_id=(body.item_id or "").strip(),
                also_assign=True,
                override=bool(body.override),
                store=store,
            )
        except ValueError as e:
            from carro.core.car_turn import CarTurnBlocked

            if isinstance(e, CarTurnBlocked) or "has the car first" in str(e):
                raise HTTPException(403, str(e)) from e
            raise HTTPException(400, str(e)) from e
        if advisor and not tech:
            from carro.core.advisor_actions import append_advisor_action

            append_advisor_action(
                order,
                action="started_work",
                advisor_id=advisor.id,
                advisor_name=advisor.name,
                work_item_id=(body.item_id or "").strip(),
            )
    else:
        from carro.core.assignment import release_tech_current

        if not release_tech_current(
            order,
            tech_id=worker_id,
            tech_name=worker_name,
            item_id=(body.item_id or "").strip(),
        ) and not matches_tech(
            order.current_tech_id,
            order.current_tech_name,
            me_id=worker_id,
            me_name=worker_name,
        ):
            raise HTTPException(403, "This is not your current work")
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/queue")
def queue_action_route(
    ro_id: str,
    body: QueueActionBody,
    as_role: str | None = None,
    x_carro_as_role: str | None = Header(default=None, alias="X-Carro-As-Role"),
) -> dict[str, Any]:
    """
    Planned work queue for the logged-in tech:
    - add / remove
    - complete → advisor ready-to-bill queue
    - reopen → undo done / billed out back onto the floor
    - billed_out → final close (advisor after accounting)
    """
    from carro.core.assignment import (
        add_to_my_queue,
        archive_ro,
        bill_out_ro,
        complete_ro,
        complete_work_item,
        release_wait_item,
        remove_from_my_queue,
        reopen_ro,
        request_customer_approval,
        request_parts,
        set_work_item_waiting,
    )

    tech = techmod.current_technician()
    advisor = advmod.current_advisor()
    if body.action == "billed_out":
        advisor = _require_advisor_for_desk(
            as_role=as_role,
            x_carro_as_role=x_carro_as_role,
            detail="Only an advisor can mark billed out",
        )
    elif body.action in ("canceled", "no_call_no_show", "reopen"):
        if not tech and not advisor:
            raise HTTPException(401, "Login required to archive or reopen")
    elif body.action in ("item_release_wait", "item_return_to_requester"):
        if not advisor and not tech:
            raise HTTPException(401, "Login required to release waiting work")
    elif body.action in ("add", "remove", "complete_item", "complete", "complete_with"):
        if tech:
            pass
        elif advisor and advmod.has_working_privilege(advisor):
            pass
        else:
            raise HTTPException(
                401,
                "Log in as a technician, or as an advisor with working privilege",
            )
    elif not tech:
        raise HTTPException(401, "Log in as a technician to manage your queue")
    order = _require_order(ro_id)

    item_id = (body.item_id or "").strip()
    actor_id = (tech.id if tech else (advisor.id if advisor else "")) or ""
    actor_name = (tech.name if tech else (advisor.name if advisor else "")) or ""

    if body.action == "add":
        try:
            add_to_my_queue(
                order,
                tech_id=actor_id,
                tech_name=actor_name,
                item_id=item_id,
                store=store,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    elif body.action == "remove":
        if not remove_from_my_queue(
            order,
            tech_id=actor_id,
            tech_name=actor_name,
            item_id=item_id,
            store=store,
        ):
            raise HTTPException(403, "This work item is not on your queue")
    elif body.action == "complete_item":
        extras = [str(x).strip() for x in (body.also_item_ids or []) if str(x).strip()]
        timed = item_id or (order.current_item_id or "")
        try:
            if extras:
                from carro.core.assignment import complete_items_with

                complete_items_with(
                    order,
                    timed_id=timed,
                    companion_ids=extras,
                    also_complete_timed=True,
                    tech_id=actor_id,
                    tech_name=actor_name,
                    store=store,
                )
            else:
                complete_work_item(
                    order,
                    timed,
                    tech_id=actor_id,
                    tech_name=actor_name,
                    store=store,
                )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    elif body.action == "complete_with":
        from carro.core.assignment import complete_items_with

        timed = (body.with_item_id or "").strip()
        comps = [item_id] if item_id else []
        extra = [str(x).strip() for x in (body.also_item_ids or []) if str(x).strip()]
        for cid in extra:
            if cid not in comps:
                comps.append(cid)
        try:
            complete_items_with(
                order,
                timed_id=timed,
                companion_ids=comps,
                also_complete_timed=bool(body.also_complete_timed),
                tech_id=actor_id,
                tech_name=actor_name,
                store=store,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    elif body.action == "complete":
        # Prefer item when item_id / current item present
        wid = item_id or (order.current_item_id or "").strip()
        if wid:
            try:
                complete_work_item(
                    order,
                    wid,
                    tech_id=actor_id,
                    tech_name=actor_name,
                    store=store,
                )
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
        else:
            complete_ro(order, tech_id=actor_id, tech_name=actor_name)
    elif body.action == "reopen":
        try:
            reopen_ro(order, tech_id=actor_id, tech_name=actor_name)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if advisor and not tech:
            from carro.core.advisor_actions import append_advisor_action

            append_advisor_action(
                order,
                action="reopened",
                advisor_id=advisor.id,
                advisor_name=advisor.name,
            )
    elif body.action == "billed_out":
        bill_out_ro(order, tech_id=advisor.id, tech_name=advisor.name)
        from carro.core.advisor_actions import append_advisor_action

        append_advisor_action(
            order,
            action="billed_out",
            advisor_id=advisor.id,
            advisor_name=advisor.name,
        )
    elif body.action in ("canceled", "no_call_no_show"):
        if not advisor:
            raise HTTPException(401, "Only an advisor can cancel or mark no-call/no-show")
        try:
            archive_ro(
                order,
                body.action,
                tech_id=actor_id,
                tech_name=actor_name,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        from carro.core.advisor_actions import append_advisor_action

        append_advisor_action(
            order,
            action=body.action,
            advisor_id=advisor.id,
            advisor_name=advisor.name,
        )
    elif body.action in ("item_release_wait", "item_return_to_requester"):
        try:
            info = release_wait_item(
                order,
                item_id or (order.current_item_id or ""),
                return_to_requester=body.action == "item_return_to_requester",
                reason=(
                    "return_to_requester"
                    if body.action == "item_return_to_requester"
                    else "released_unassigned"
                ),
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if advisor:
            from carro.core.advisor_actions import append_advisor_action

            detail = (
                f"Returned to {info.get('assigned_to_name') or info.get('assigned_to_id') or 'requester'}"
                if body.action == "item_return_to_requester"
                else "Released to Unassigned"
            )
            append_advisor_action(
                order,
                action=(
                    "returned_to_requester"
                    if body.action == "item_return_to_requester"
                    else "released_wait_unassigned"
                ),
                advisor_id=advisor.id,
                advisor_name=advisor.name,
                work_item_id=info.get("item_id") or item_id,
                detail=detail,
            )
    elif body.action in ("item_waiting_customer",):
        try:
            set_work_item_waiting(
                order,
                item_id or (order.current_item_id or ""),
                kind="waiting_customer",
                tech_id=tech.id,
                tech_name=tech.name,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    elif body.action in ("item_waiting_parts",):
        try:
            set_work_item_waiting(
                order,
                item_id or (order.current_item_id or ""),
                kind="waiting_parts",
                tech_id=tech.id,
                tech_name=tech.name,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    elif body.action == "request_approval" or body.action == "waiting_customer":
        request_customer_approval(
            order, tech_id=tech.id, tech_name=tech.name, item_id=item_id
        )
    elif body.action == "request_parts" or body.action == "waiting_parts":
        request_parts(
            order, tech_id=tech.id, tech_name=tech.name, item_id=item_id
        )
    else:
        raise HTTPException(400, f"Unknown action: {body.action}")

    store.save(order)
    who, who_id = _actor_from(tech, advisor, prefer="tech")
    if body.action in ("billed_out", "canceled", "no_call_no_show") and advisor:
        who, who_id = advisor.name, advisor.id
    elif body.action == "reopen" and advisor and not tech:
        who, who_id = advisor.name, advisor.id
    elif body.action in ("item_release_wait", "item_return_to_requester") and advisor:
        who, who_id = advisor.name, advisor.id
    _push_ro(order, actor=who, actor_id=who_id)
    return order.to_dict()


@app.post("/ros/{ro_id}/flags")
def ro_flags_route(ro_id: str, body: RoFlagsBody) -> dict[str, Any]:
    """Advisor sets waiter / urgent floor flags on the RO."""
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.queue_lanes import set_ro_flags

    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Log in as an advisor to set floor flags")
    order = _require_order(ro_id)
    if body.waiter is None and body.urgent is None:
        raise HTTPException(400, "Provide waiter and/or urgent")
    set_ro_flags(order, waiter=body.waiter, urgent=body.urgent)
    bits = []
    if body.waiter is not None:
        bits.append(f"waiter={'on' if body.waiter else 'off'}")
    if body.urgent is not None:
        bits.append(f"urgent={'on' if body.urgent else 'off'}")
    append_advisor_action(
        order,
        action="ro_flags",
        advisor_id=advisor.id,
        advisor_name=advisor.name,
        detail=", ".join(bits),
    )
    store.save(order)
    _push_ro(order, actor=advisor.name, actor_id=advisor.id)
    return order.to_dict()


@app.post("/ros/{ro_id}/work-items/{item_id}/car-turn")
def work_item_car_turn_route(
    ro_id: str, item_id: str, body: WorkItemCarTurnBody
) -> dict[str, Any]:
    """Advisor sets 1st / 2nd / Nth car turn on a split RO."""
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.car_turn import set_car_turn

    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Only an advisor can set car turn")
    order = _require_order(ro_id)
    try:
        set_car_turn(order, item_id, body.turn)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    append_advisor_action(
        order,
        action="car_turn",
        advisor_id=advisor.id,
        advisor_name=advisor.name,
        work_item_id=item_id,
        detail=f"turn {body.turn}",
    )
    store.save(order)
    _push_ro(order, actor=advisor.name, actor_id=advisor.id)
    return order.to_dict()


@app.post("/ros/{ro_id}/work-items/{item_id}/queue")
def work_item_queue_lane_route(
    ro_id: str, item_id: str, body: WorkItemQueueBody
) -> dict[str, Any]:
    """Advisor moves a work item between daily / next_day / long_term."""
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.queue_lanes import move_ro_group_lane

    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Only an advisor can set queue lanes")
    order = _require_order(ro_id)
    req_by_id = ""
    req_by_name = ""
    was_pending_next_day = False
    if body.lane == "next_day" or body.approve_request:
        from carro.core.work_items import ensure_work_items_on_order

        for w in ensure_work_items_on_order(order):
            if w.id != item_id:
                continue
            req = w.next_day_request if isinstance(w.next_day_request, dict) else {}
            if str(req.get("status") or "").strip().lower() == "pending":
                was_pending_next_day = True
                req_by_id = str(req.get("by_id") or "").strip()
                req_by_name = str(req.get("by") or "").strip()
                if not req_by_id:
                    req_by_id = (w.assigned_to_id or "").strip()
                    req_by_name = req_by_name or (w.assigned_to_name or "").strip()
            break
    try:
        touched = move_ro_group_lane(
            store,
            order,
            item_id,
            body.lane,
            approve_request=body.approve_request or body.lane == "next_day",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    append_advisor_action(
        order,
        action="queue_lane",
        advisor_id=advisor.id,
        advisor_name=advisor.name,
        work_item_id=item_id,
        detail=body.lane,
    )
    for o in touched:
        store.save(o)
        _push_ro(o, actor=advisor.name, actor_id=advisor.id)
    if was_pending_next_day and body.lane == "next_day" and req_by_id:
        _notify_tech_message(
            to_id=req_by_id,
            to_name=req_by_name,
            body=f"Next-day request approved · {order.id} / {item_id}",
            from_id=advisor.id,
            from_name=advisor.name,
            from_role="advisor",
            ro_id=order.id,
            work_item_id=item_id,
        )
    return order.to_dict()


@app.post("/ros/{ro_id}/work-items/{item_id}/queue/request-next-day")
def work_item_request_next_day_route(
    ro_id: str, item_id: str, body: NextDayRequestBody | None = None
) -> dict[str, Any]:
    """Tech asks advisor to push this job to the next-day pool."""
    from carro.core.queue_lanes import request_next_day

    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician to request next day")
    order = _require_order(ro_id)
    note = (body.note if body else "") or ""
    try:
        request_next_day(
            order,
            item_id,
            tech_id=tech.id,
            tech_name=tech.name,
            note=note,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order, actor=tech.name, actor_id=tech.id)
    return order.to_dict()


@app.post("/ros/{ro_id}/work-items/{item_id}/queue/request-decision")
def work_item_next_day_decision_route(
    ro_id: str, item_id: str, body: NextDayRequestDecisionBody
) -> dict[str, Any]:
    """Advisor approves (arms next_day) or declines a tech next-day request."""
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.queue_lanes import decline_next_day_request, move_ro_group_lane
    from carro.core.work_items import ensure_work_items_on_order

    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Only an advisor can decide next-day requests")
    order = _require_order(ro_id)
    req_by_id = ""
    req_by_name = ""
    for w in ensure_work_items_on_order(order):
        if w.id == item_id:
            req = w.next_day_request if isinstance(w.next_day_request, dict) else {}
            req_by_id = str(req.get("by_id") or "").strip()
            req_by_name = str(req.get("by") or "").strip()
            if not req_by_id:
                req_by_id = (w.assigned_to_id or "").strip()
                req_by_name = req_by_name or (w.assigned_to_name or "").strip()
            break
    try:
        if body.approve:
            touched = move_ro_group_lane(
                store, order, item_id, "next_day", approve_request=True
            )
        else:
            decline_next_day_request(order, item_id)
            touched = [order]
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    append_advisor_action(
        order,
        action="next_day_request_approved" if body.approve else "next_day_request_declined",
        advisor_id=advisor.id,
        advisor_name=advisor.name,
        work_item_id=item_id,
        detail="due EOD" if not body.approve else "next_day",
    )
    for o in touched:
        store.save(o)
        _push_ro(o, actor=advisor.name, actor_id=advisor.id)
    if req_by_id:
        if body.approve:
            _notify_tech_message(
                to_id=req_by_id,
                to_name=req_by_name,
                body=f"Next-day request approved · {order.id} / {item_id}",
                from_id=advisor.id,
                from_name=advisor.name,
                from_role="advisor",
                ro_id=order.id,
                work_item_id=item_id,
            )
        else:
            _notify_tech_message(
                to_id=req_by_id,
                to_name=req_by_name,
                body=f"Next-day request declined — needs done by end of day · {order.id} / {item_id}",
                from_id=advisor.id,
                from_name=advisor.name,
                from_role="advisor",
                ro_id=order.id,
                work_item_id=item_id,
            )
    return order.to_dict()


@app.post("/ros/{ro_id}/work-items/{item_id}/queue/request-read")
def work_item_next_day_request_read_route(ro_id: str, item_id: str) -> dict[str, Any]:
    """Advisor marks a next-day request notification as read."""
    from carro.core.queue_lanes import mark_next_day_request_read

    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Only an advisor can mark queue requests read")
    order = _require_order(ro_id)
    try:
        mark_next_day_request_read(order, item_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/work-items")
def upsert_work_item_route(ro_id: str, body: WorkItemBody) -> dict[str, Any]:
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.work_items import upsert_work_item

    order = _require_order(ro_id)
    tech = techmod.current_technician()
    advisor = advmod.current_advisor()
    if not tech and not advisor:
        raise HTTPException(401, "Log in as a technician or advisor to edit work items")
    was_done = (order.status or "").strip().lower() == "done"
    # New items from an advisor desk: attribute to advisor even if a tech is also logged in.
    creating = not body.id
    if advisor and (creating or body.assign_to_id is not None or body.assign_to_name is not None or not tech):
        actor, actor_id, role = advisor.name, advisor.id, "advisor"
        allow_manual = True
    elif tech:
        actor, actor_id, role = tech.name, tech.id, "tech"
        allow_manual = False
    else:
        actor, actor_id, role = advisor.name, advisor.id, "advisor"  # type: ignore[union-attr]
        allow_manual = True
    try:
        item = upsert_work_item(
            order,
            item_id=body.id,
            concern=body.concern,
            notes=body.notes,
            private_notes=body.private_notes,
            item_type=body.item_type,
            status=body.status,
            priority=body.priority,
            actor=actor,
            actor_id=actor_id,
            actor_role=role,
            assign_to_id=body.assign_to_id,
            assign_to_name=body.assign_to_name,
            allow_manual_assign=allow_manual,
            require_item_type=creating,
            service_plan_enroll=body.service_plan_enroll,
            service_plan_id=body.service_plan_id,
            service_plan_line_id=body.service_plan_line_id,
        )
        enroll_flag = str(body.service_plan_enroll or getattr(item, "service_plan_enroll", "") or "").strip().lower()
        if enroll_flag in ("yes", "true", "1") and not (item.service_plan_id or "").strip():
            from carro.core.service_plans import enroll_inspection_plan
            from carro.core.work_items import ensure_work_items_on_order, work_items_to_dicts

            enrolled = enroll_inspection_plan(
                store,
                order,
                item.item_type,
                enroll=True,
                actor=actor,
                actor_id=actor_id,
            )
            if enrolled:
                item.service_plan_id = enrolled["plan"]["id"]
                item.service_plan_line_id = enrolled["line"]["id"]
                item.service_plan_enroll = "yes"
                items = ensure_work_items_on_order(order)
                for w in items:
                    if w.id == item.id:
                        w.service_plan_id = item.service_plan_id
                        w.service_plan_line_id = item.service_plan_line_id
                        w.service_plan_enroll = "yes"
                order.work_items = work_items_to_dicts(items)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if advisor and (was_done or creating):
        append_advisor_action(
            order,
            action="more_work_requested" if was_done else "work_item_added",
            advisor_id=advisor.id,
            advisor_name=advisor.name,
            work_item_id=getattr(item, "id", "") or "",
            detail=(body.concern or "")[:120],
        )
    store.save(order)
    _push_ro(order, actor=actor, actor_id=actor_id)
    return order.to_dict()


@app.post("/ros/{ro_id}/found-issues/compose")
def found_issue_compose_begin(ro_id: str, body: FoundIssueComposeBody) -> dict[str, Any]:
    from carro.core.found_issues import begin_found_issue_compose

    order = _require_order(ro_id)
    worker_id, worker_name = _bay_worker()
    try:
        begin_found_issue_compose(
            order,
            tech_id=worker_id,
            tech_name=worker_name,
            item_id=body.item_id or "",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/found-issues/compose/cancel")
def found_issue_compose_cancel(ro_id: str, body: FoundIssueComposeBody) -> dict[str, Any]:
    from carro.core.found_issues import cancel_found_issue_compose

    order = _require_order(ro_id)
    worker_id, worker_name = _bay_worker()
    try:
        cancel_found_issue_compose(
            order,
            tech_id=worker_id,
            tech_name=worker_name,
            item_id=body.item_id or "",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/found-issues")
def found_issue_create(ro_id: str, body: FoundIssueCreateBody) -> dict[str, Any]:
    from carro.core.found_issues import create_found_issue

    order = _require_order(ro_id)
    worker_id, worker_name = _bay_worker()
    try:
        fi = create_found_issue(
            order,
            description=body.description,
            notes=body.notes,
            tech_id=worker_id,
            tech_name=worker_name,
            source_work_item_id=body.source_work_item_id or "",
            finish_compose=body.finish_compose,
            status=body.status or "draft",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order, actor=worker_name, actor_id=worker_id)
    out = order.to_dict()
    # Ephemeral — for clients that attach photos right after create
    out["created_found_issue_id"] = fi.id
    return out


@app.patch("/ros/{ro_id}/found-issues/{fi_id}")
def found_issue_update(ro_id: str, fi_id: str, body: FoundIssueUpdateBody) -> dict[str, Any]:
    """Edit a draft found issue (description / notes) before sending to the desk."""
    from carro.core.found_issues import update_found_issue

    order = _require_order(ro_id)
    worker_id, worker_name = _bay_worker()
    if body.description is None and body.notes is None:
        raise HTTPException(400, "Provide description and/or notes to update")
    try:
        update_found_issue(
            order,
            fi_id,
            description=body.description,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order, actor=worker_name, actor_id=worker_id)
    return order.to_dict()


@app.post("/ros/{ro_id}/found-issues/submit")
def found_issue_submit(ro_id: str, body: FoundIssueSubmitBody) -> dict[str, Any]:
    """Promote draft found issues to pending so the advisor desk is notified."""
    from carro.core.found_issues import submit_found_issues

    order = _require_order(ro_id)
    worker_id, worker_name = _bay_worker()
    try:
        promoted = submit_found_issues(order, body.ids or None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order, actor=worker_name, actor_id=worker_id)
    out = order.to_dict()
    out["submitted_found_issue_ids"] = [fi.id for fi in promoted]
    out["submitted_count"] = len(promoted)
    return out


@app.post("/ros/{ro_id}/found-issues/{fi_id}/approve")
def found_issue_approve(
    ro_id: str,
    fi_id: str,
    body: FoundIssueApproveBody,
    as_role: str | None = None,
    x_carro_as_role: str | None = Header(default=None, alias="X-Carro-As-Role"),
) -> dict[str, Any]:
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.found_issues import approve_found_issue

    order = _require_order(ro_id)
    advisor = _require_advisor_for_desk(
        as_role=as_role,
        x_carro_as_role=x_carro_as_role,
        detail="Log in as an advisor to approve found issues",
    )
    try:
        assign_id = (body.assign_to_id or "").strip()
        assign_name = (body.assign_to_name or "").strip()
        if assign_id and not assign_name:
            for t in techmod.list_technicians():
                if t.id == assign_id:
                    assign_name = t.name
                    break
        approve_found_issue(
            order,
            fi_id,
            item_type=body.item_type or "repair",
            actor=advisor.name,
            actor_id=advisor.id,
            actor_role="advisor",
            assign_to_id=assign_id,
            assign_to_name=assign_name,
        )
        append_advisor_action(
            order,
            action="found_issue_approved",
            advisor_id=advisor.id,
            advisor_name=advisor.name,
            found_issue_id=fi_id,
            detail=body.item_type or "repair",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order, actor=advisor.name, actor_id=advisor.id)
    if assign_id:
        from carro.core.found_issues import ensure_found_issues_on_order

        wi_id = ""
        for fi in ensure_found_issues_on_order(order):
            if fi.id == fi_id:
                wi_id = (fi.work_item_id or "").strip()
                break
        _notify_tech_message(
            to_id=assign_id,
            to_name=assign_name,
            body=f"Approved found issue assigned to you · {order.id}"
            + (f" / {wi_id}" if wi_id else f" / {fi_id}"),
            from_id=advisor.id,
            from_name=advisor.name,
            from_role="advisor",
            ro_id=order.id,
            work_item_id=wi_id or fi_id,
        )
    return order.to_dict()


@app.post("/ros/{ro_id}/found-issues/{fi_id}/unapprove")
def found_issue_unapprove(
    ro_id: str,
    fi_id: str,
    as_role: str | None = None,
    x_carro_as_role: str | None = Header(default=None, alias="X-Carro-As-Role"),
) -> dict[str, Any]:
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.found_issues import unapprove_found_issue

    order = _require_order(ro_id)
    advisor = _require_advisor_for_desk(
        as_role=as_role,
        x_carro_as_role=x_carro_as_role,
        detail="Log in as an advisor to undo found-issue approval",
    )
    try:
        unapprove_found_issue(
            order,
            fi_id,
            actor=advisor.name,
            actor_id=advisor.id,
        )
        append_advisor_action(
            order,
            action="found_issue_unapproved",
            advisor_id=advisor.id,
            advisor_name=advisor.name,
            found_issue_id=fi_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order, actor=advisor.name, actor_id=advisor.id)
    return order.to_dict()


@app.post("/ros/{ro_id}/found-issues/{fi_id}/decline")
def found_issue_decline(
    ro_id: str,
    fi_id: str,
    body: FoundIssueDeclineBody,
    as_role: str | None = None,
    x_carro_as_role: str | None = Header(default=None, alias="X-Carro-As-Role"),
) -> dict[str, Any]:
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.found_issues import decline_found_issue

    order = _require_order(ro_id)
    advisor = _require_advisor_for_desk(
        as_role=as_role,
        x_carro_as_role=x_carro_as_role,
        detail="Log in as an advisor to decline found issues",
    )
    try:
        decline_found_issue(
            order,
            fi_id,
            reason=body.reason or "customer_declined",
            actor=advisor.name,
            actor_id=advisor.id,
        )
        append_advisor_action(
            order,
            action="found_issue_declined",
            advisor_id=advisor.id,
            advisor_name=advisor.name,
            found_issue_id=fi_id,
            detail=body.reason or "customer_declined",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order, actor=advisor.name, actor_id=advisor.id)
    return order.to_dict()


@app.get("/parts")
def parts_sheet(
    status: str = "",
    manufacturer: str = "",
    part_number: str = "",
    ro_id: str = "",
    q: str = "",
    include_received: bool = False,
    source: str = "auto",
) -> dict[str, Any]:
    """
    Parts sheet / archive search.
    source=auto: prefer server index when configured, else local ROs.
    source=local|server: force.
    """
    from carro.core.work_items import collect_parts_sheet

    prefer = (source or "auto").strip().lower()
    remote = RemoteClient()
    if prefer in ("auto", "server") and remote.enabled:
        try:
            remote_hit = remote.search_parts(
                part_number=part_number,
                manufacturer=manufacturer,
                status=status,
                ro_id=ro_id,
                q=q,
                include_received=include_received,
            )
            rows = list(remote_hit.get("parts") or [])
            # Merge local open lines not yet pushed (best-effort)
            if prefer == "auto":
                local_rows = collect_parts_sheet(
                    store.list_orders(),
                    status=status,
                    manufacturer=manufacturer,
                    part_number=part_number,
                    ro_id=ro_id,
                    q=q,
                    include_received=include_received,
                )
                seen = {
                    (r.get("ro_id"), r.get("work_item_id"), r.get("part_id")) for r in rows
                }
                for lr in local_rows:
                    key = (lr.get("ro_id"), lr.get("work_item_id"), lr.get("part_id"))
                    if key not in seen:
                        rows.append(lr)
            return {
                "parts": rows,
                "count": len(rows),
                "source": "server" if prefer == "server" else "server+local",
            }
        except Exception:
            if prefer == "server":
                raise
    rows = collect_parts_sheet(
        store.list_orders(),
        status=status,
        manufacturer=manufacturer,
        part_number=part_number,
        ro_id=ro_id,
        q=q,
        include_received=include_received,
    )
    return {"parts": rows, "count": len(rows), "source": "local"}


@app.get("/parts/usage")
def parts_usage_route(
    year: int | None = None,
    month: int | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    remote = RemoteClient()
    if not remote.enabled:
        raise HTTPException(400, "Configure shop server URL to view archive parts usage")
    try:
        return remote.parts_usage(year=year, month=month, limit=limit)
    except Exception as exc:
        raise HTTPException(502, f"Server parts usage failed: {exc}") from exc


def _annotate_part_suggestions(payload: dict[str, Any], q: str = "") -> dict[str, Any]:
    from carro.core import part_supersessions as ssmod

    suggestions = [ssmod.annotate_suggestion(s) for s in (payload.get("suggestions") or [])]
    qn = ssmod.normalize_pn(q)
    if qn:
        hit = ssmod.lookup(qn)
        if hit:
            current = str(hit.get("current_number") or hit.get("new_number") or "")
            old = str(hit.get("old_number") or "")
            already = {
                ssmod.normalize_pn(s.get("part_number"))
                for s in suggestions
            }
            if current and current not in already:
                suggestions.insert(
                    0,
                    {
                        "part_number": current,
                        "manufacturer": hit.get("manufacturer") or "",
                        "brand": "",
                        "description": f"Current number (replaces {old})",
                        "use_count": 0,
                        "superseded_by": "",
                        "supersedes": old,
                    },
                )
            for s in suggestions:
                if ssmod.normalize_pn(s.get("part_number")) == old and current:
                    s["superseded_by"] = current
    payload["suggestions"] = suggestions
    payload["count"] = len(suggestions)
    return payload


@app.get("/parts/suggest")
def parts_suggest_route(q: str = "", limit: int = 25) -> dict[str, Any]:
    """Catalog suggestions for add-part lookup (server archive when available)."""
    remote = RemoteClient()
    if remote.enabled:
        try:
            return _annotate_part_suggestions(remote.parts_suggest(q=q, limit=limit), q)
        except Exception:
            pass
    # Local fallback: distinct from local sheet
    from carro.core.work_items import collect_parts_sheet

    rows = collect_parts_sheet(store.list_orders(), include_received=True)
    qn = (q or "").strip().lower()
    buckets: dict[str, dict[str, Any]] = {}
    for r in rows:
        pn = (r.get("part_number") or "").strip().upper()
        mfr = (r.get("manufacturer") or "").strip().upper()
        brand = (r.get("brand") or "").strip().upper()
        desc = (r.get("description") or "").strip()
        if qn and qn not in f"{desc} {pn} {mfr} {brand} {r.get('superseded_by') or ''} {r.get('supersedes') or ''}".lower():
            continue
        key = f"{pn}|{mfr}|{brand}|{desc.upper()}"
        cur = buckets.get(key) or {
            "part_number": pn,
            "manufacturer": mfr,
            "brand": brand,
            "description": desc,
            "use_count": 0,
        }
        cur["use_count"] = int(cur["use_count"] or 0) + 1
        buckets[key] = cur
    suggestions = sorted(
        buckets.values(), key=lambda x: (-int(x["use_count"]), x.get("description") or "")
    )[: max(1, min(int(limit), 100))]
    return _annotate_part_suggestions(
        {"suggestions": suggestions, "count": len(suggestions), "source": "local"},
        q,
    )


@app.get("/notifications/idle")
def idle_notifications(
    assignee_id: str = "",
    desk: str = "",
) -> dict[str, Any]:
    """Work items / parts with no activity for idle_nudge_hours (default 24).

    Optional filters:
    - assignee_id: only rows assigned to that person (tech scope)
    - desk=1: unassigned work or waiting-parts / part idle (advisor desk scope)
    """
    from carro.core.idle_nudge import collect_idle_nudges, filter_idle_nudges

    cfg = load_config()
    hours = resolve_idle_nudge_hours(cfg)
    rows = collect_idle_nudges(store.list_orders(), idle_hours=hours)
    desk_flag = str(desk or "").strip().lower() in {"1", "true", "yes", "on"}
    rows = filter_idle_nudges(rows, assignee_id=assignee_id, desk=desk_flag)
    return {
        "idle": rows,
        "count": len(rows),
        "idle_nudge_hours": hours,
        "enabled": hours > 0,
    }


@app.post("/ros/{ro_id}/work-items/{item_id}/parts")
def add_part_route(ro_id: str, item_id: str, body: PartBody) -> dict[str, Any]:
    from carro.core.work_items import add_part

    order = _require_order(ro_id)
    tech = techmod.current_technician()
    advisor = advmod.current_advisor()
    if not tech and not advisor:
        raise HTTPException(401, "Log in as a technician or advisor to edit parts")
    try:
        add_part(
            order,
            item_id,
            description=body.description,
            part_number=body.part_number,
            oem_part_number=body.oem_part_number or "",
            manufacturer=body.manufacturer,
            brand=body.brand or "",
            supplier=body.supplier or "",
            superseded_by=body.superseded_by or "",
            supersedes=body.supersedes or "",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order)
    _push_part_supersessions()
    return order.to_dict()


@app.patch("/ros/{ro_id}/work-items/{item_id}/parts/{part_id}")
def patch_part_route(
    ro_id: str, item_id: str, part_id: str, body: PartPatchBody
) -> dict[str, Any]:
    from carro.core.work_items import set_part_status, update_part

    order = _require_order(ro_id)
    tech = techmod.current_technician()
    advisor = advmod.current_advisor()
    if not tech and not advisor:
        raise HTTPException(401, "Log in as a technician or advisor to edit parts")
    actor_name = tech.name if tech else advisor.name  # type: ignore[union-attr]
    actor_id = tech.id if tech else advisor.id  # type: ignore[union-attr]
    try:
        if (
            body.description is not None
            or body.part_number is not None
            or body.oem_part_number is not None
            or body.manufacturer is not None
            or body.brand is not None
            or body.supplier is not None
            or body.superseded_by is not None
            or body.supersedes is not None
        ):
            update_part(
                order,
                item_id,
                part_id,
                description=body.description,
                part_number=body.part_number,
                oem_part_number=body.oem_part_number,
                manufacturer=body.manufacturer,
                brand=body.brand,
                supplier=body.supplier,
                superseded_by=body.superseded_by,
                supersedes=body.supersedes,
            )
        if body.status is not None:
            set_part_status(
                order,
                item_id,
                part_id,
                body.status,
                wrong_note=body.wrong_note or "",
                actor=actor_name,
                actor_id=actor_id,
            )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order)
    _push_part_supersessions()
    return order.to_dict()


@app.delete("/ros/{ro_id}/work-items/{item_id}/parts/{part_id}")
def delete_part_route(ro_id: str, item_id: str, part_id: str) -> dict[str, Any]:
    from carro.core.work_items import remove_part

    order = _require_order(ro_id)
    tech = techmod.current_technician()
    advisor = advmod.current_advisor()
    if not tech and not advisor:
        raise HTTPException(401, "Log in as a technician or advisor to edit parts")
    if not remove_part(order, item_id, part_id):
        raise HTTPException(404, "Part not found")
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/work-items/{item_id}/time")
def work_item_time_route(ro_id: str, item_id: str, body: WorkItemTimeBody) -> dict[str, Any]:
    from carro.core.assignment import (
        clear_current_task,
        clear_tech_current_elsewhere,
        matches_tech,
        set_current_task,
    )
    from carro.core.work_items import add_worked_minutes, checkpoint_work_timer, stop_work_timer

    order = _require_order(ro_id)
    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician to log time")
    try:
        if body.action == "add":
            mins = int(body.minutes or 0)
            if mins <= 0:
                raise HTTPException(400, "minutes must be > 0")
            add_worked_minutes(
                order,
                item_id,
                mins,
                tech_id=tech.id,
                tech_name=tech.name,
                note=body.note or "",
            )
        elif body.action == "start":
            for other in clear_tech_current_elsewhere(
                store.list_orders(),
                tech_id=tech.id,
                tech_name=tech.name,
                except_id=ro_id,
            ):
                store.save(other)
                _push_ro(other)
            set_current_task(
                order,
                tech_id=tech.id,
                tech_name=tech.name,
                item_id=item_id,
                also_assign=True,
                override=bool(getattr(body, "override", False)),
                store=store,
            )
        elif body.action == "stop":
            from carro.core.assignment import release_tech_current

            if not release_tech_current(
                order, tech_id=tech.id, tech_name=tech.name, item_id=item_id
            ):
                stop_work_timer(order, item_id)
                from carro.core.assignment import sync_ro_current_from_timers

                sync_ro_current_from_timers(order)
        elif body.action == "checkpoint":
            checkpoint_work_timer(
                order,
                item_id,
                tech_id=tech.id,
                tech_name=tech.name,
            )
        else:
            raise HTTPException(400, f"Unknown action: {body.action}")
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/work-items/merge")
def merge_work_items_route(ro_id: str, body: WorkItemMergeBody) -> dict[str, Any]:
    """Absorb source work items into target (related complaints → one job).

    Declared before ``/work-items/{item_id}`` so ``merge`` is not captured as an id.
    """
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.work_items import merge_work_items

    order = _require_order(ro_id)
    actor_id, actor_name = _merge_actor()
    try:
        target = merge_work_items(
            order,
            target_id=body.target_id,
            source_ids=list(body.source_ids or []),
            reason=body.reason or "",
        )
        sources = [
            str(x).strip()
            for x in (body.source_ids or [])
            if str(x).strip() and str(x).strip() != target.id
        ]
        reason_s = (body.reason or "").strip()
        append_advisor_action(
            order,
            action="item_merged",
            advisor_id=actor_id,
            advisor_name=actor_name,
            work_item_id=target.id,
            detail=",".join(sources),
            note=f"{', '.join(sources)} → {target.id}"
            + (f" · {reason_s}" if reason_s else ""),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order)
    out = order.to_dict()
    out["merged_into"] = target.id
    out["merged_sources"] = sources
    return out


@app.post("/ros/{ro_id}/work-items/{item_id}/unmerge")
def unmerge_work_items_route(ro_id: str, item_id: str) -> dict[str, Any]:
    """Undo last merge on a survivor that still has merge_snapshot."""
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.work_items import unmerge_work_items

    order = _require_order(ro_id)
    actor_id, actor_name = _merge_actor()
    try:
        restored = unmerge_work_items(order, item_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    append_advisor_action(
        order,
        action="item_unmerged",
        advisor_id=actor_id,
        advisor_name=actor_name,
        work_item_id=item_id,
        detail=",".join(w.id for w in restored),
        note=f"Restored {', '.join(w.id for w in restored)} from {item_id}",
    )
    store.save(order)
    _push_ro(order)
    out = order.to_dict()
    out["unmerged_sources"] = [w.id for w in restored]
    return out


@app.delete("/ros/{ro_id}/work-items/{item_id}")
def delete_work_item_route(ro_id: str, item_id: str) -> dict[str, Any]:
    from carro.core.work_items import remove_work_item

    order = _require_order(ro_id)
    if not remove_work_item(order, item_id):
        raise HTTPException(404, f"Work item not found: {item_id}")
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.delete("/ros/{ro_id}")
def delete_ro(ro_id: str) -> dict[str, Any]:
    from carro.config import photos_dir

    order = _require_order(ro_id)
    # Advisors may delete any RO. Techs may only discard a blank new RO
    # (no work items) so they don't wipe live jobs by accident.
    advisor = advmod.current_advisor()
    if not advisor:
        items = order.work_items if isinstance(order.work_items, list) else []
        if items:
            raise HTTPException(
                403,
                "Only an advisor can delete an RO that has work items — "
                "remove items individually instead",
            )
    remote = RemoteClient()
    # Queue remote delete if server is down so it is not resurrected later.
    if not store.delete(ro_id, queue_remote=remote.enabled):
        raise HTTPException(500, "Local delete failed")
    photo_dir = photos_dir() / ro_id
    if photo_dir.is_dir():
        shutil.rmtree(photo_dir, ignore_errors=True)
    if remote.enabled:
        try:
            remote.delete_ro(ro_id)
            store.clear_pending_delete(ro_id)
        except Exception:
            # Local gone; pending_deletes keeps the remote wipe for next sync.
            pass
    return {"ok": True, "id": ro_id}


@app.post("/ros/{ro_id}/pdf")
def pdf_ro(
    ro_id: str,
    include_photos: bool = True,
    open_viewer: bool = False,
) -> dict[str, Any]:
    """Customer PDF. Set include_photos=false for ink-saving / B&W (no job photos)."""
    from carro.core.pdf_open import open_pdf_viewer

    order = _require_order(ro_id)
    path = export_pdf(order, include_photos=include_photos)
    viewer = open_pdf_viewer(path) if open_viewer else None
    return {
        "path": str(path),
        "include_photos": include_photos,
        "opened": bool(viewer),
        "viewer": viewer,
        "view_url": f"/ros/{ro_id}/pdf/file?include_photos={'true' if include_photos else 'false'}",
    }


@app.post("/ros/{ro_id}/pdf/open")
def pdf_open_ro(ro_id: str, include_photos: bool = True) -> dict[str, Any]:
    """Open (or create) the customer PDF in the system viewer."""
    from carro.config import DATA_DIR
    from carro.core.pdf_open import open_pdf_viewer

    order = _require_order(ro_id)
    suffix = "" if include_photos else "-lite"
    path = DATA_DIR / "pdf" / f"{ro_id}{suffix}.pdf"
    if not path.is_file():
        path = export_pdf(order, include_photos=include_photos)
    viewer = open_pdf_viewer(path)
    return {
        "path": str(path),
        "include_photos": include_photos,
        "opened": bool(viewer),
        "viewer": viewer,
        "view_url": f"/ros/{ro_id}/pdf/file?include_photos={'true' if include_photos else 'false'}",
    }


@app.get("/ros/{ro_id}/pdf/file")
def pdf_file_ro(ro_id: str, include_photos: bool = True) -> FileResponse:
    """Serve the PDF for in-browser / webview viewing."""
    from carro.config import DATA_DIR

    order = _require_order(ro_id)
    suffix = "" if include_photos else "-lite"
    path = DATA_DIR / "pdf" / f"{ro_id}{suffix}.pdf"
    if not path.is_file():
        path = export_pdf(order, include_photos=include_photos)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
        content_disposition_type="inline",
    )


@app.post("/ros/{ro_id}/pull-obd")
def pull_obd_ro(ro_id: str, body: PullObdBody | None = None) -> dict[str, Any]:
    """
    Same handoff as CLI F2 / ``carro pull-obd`` — last_vehicle + Saved Codes.

    If the RO already has a VIN and the scan VIN differs, returns 409 unless
    ``force`` is true. On forced mismatch, keeps RO VIN/year/make and only
    applies ``obd_snapshot`` (plus empty year/make gaps).
    """
    import re

    body = body or PullObdBody()
    order = _require_order(ro_id)
    raw = pull_vehicle_fields(prefer_vin=order.vin or None)
    if not raw:
        raise HTTPException(404, "Nothing found from obdscan / Saved Codes")

    vin_re = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

    def norm_vin(v: object) -> str:
        s = str(v or "").strip().upper()
        return s if vin_re.fullmatch(s) else ""

    ro_vin = norm_vin(order.vin)
    pulled_vin = norm_vin(raw.get("vin"))
    mismatch = bool(ro_vin and pulled_vin and ro_vin != pulled_vin)

    preview = {
        "vin": str(raw.get("vin") or ""),
        "year": str(raw.get("year") or ""),
        "make": str(raw.get("make") or ""),
        "obd_snapshot": str(raw.get("obd_snapshot") or "")[:2000],
    }

    if mismatch and not body.force:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "OBD VIN does not match this RO",
                "mismatch": True,
                "ro_vin": ro_vin,
                "pulled_vin": pulled_vin,
                "pulled": preview,
            },
        )

    if mismatch and body.force:
        # Keep car identity; only attach codes (and fill empty year/make).
        snap = str(raw.get("obd_snapshot") or "").strip()
        if snap:
            order.obd_snapshot = snap
        if not str(order.year or "").strip() and preview.get("year"):
            order.year = preview["year"]
        if not str(order.make or "").strip() and preview.get("make"):
            order.make = preview["make"]
    else:
        mapped = {
            "vin": preview["vin"],
            "year": preview["year"],
            "make": preview["make"],
            "obd_snapshot": str(raw.get("obd_snapshot") or ""),
        }
        for key, val in mapped.items():
            if val:
                setattr(order, key, val)

    store.save(order)
    _push_ro(order)
    out = order.to_dict()
    if mismatch and body.force:
        out["obd_vin_mismatch_forced"] = True
        out["pulled_vin"] = pulled_vin
    return out


@app.get("/ros/{ro_id}/photos")
def list_photos(ro_id: str) -> dict[str, Any]:
    order = _require_order(ro_id)
    return {"photos": list(order.photos or [])}


@app.post("/ros/{ro_id}/photos")
async def upload_photos(
    ro_id: str,
    files: list[UploadFile] = File(...),
    tag: str = Form("other"),
    notes: str = Form(""),
    found_issue_id: str = Form(""),
) -> dict[str, Any]:
    """Attach uploaded image files to an RO (same as CLI ``carro photo add``).

    Optional found_issue_id also links the photos onto that found-issue request.
    """
    order = _require_order(ro_id)
    if not files:
        raise HTTPException(400, "No files uploaded")
    fi_id = (found_issue_id or "").strip()
    if fi_id:
        from carro.core.found_issues import ensure_found_issues_on_order

        if not any(fi.id == fi_id for fi in ensure_found_issues_on_order(order)):
            raise HTTPException(404, f"Found issue not found: {fi_id}")
    tmp_dir = Path(tempfile.mkdtemp(prefix="carro-photo-"))
    paths: list[Path] = []
    try:
        for uf in files:
            name = Path(uf.filename or "photo.jpg").name
            dest = tmp_dir / f"{len(paths)}_{name}"
            data = await uf.read()
            if not data:
                continue
            dest.write_bytes(data)
            paths.append(dest)
        if not paths:
            raise HTTPException(400, "Empty upload")
        use_tag = (tag or "other").strip() or "other"
        if fi_id and use_tag == "other":
            use_tag = "found_issue"
        order = attach_photos(
            store,
            order,
            paths,
            tag=use_tag,
            notes=(notes or "").strip(),
            found_issue_id=fi_id,
        )
        _push_ro(order)
        return order.to_dict()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.post("/ros/{ro_id}/photos/ingest")
def ingest_inbox_photos(ro_id: str, body: IngestPhotosBody | None = None) -> dict[str, Any]:
    """Attach images from the configured inbox directory (CLI ``photo ingest``)."""
    order = _require_order(ro_id)
    body = body or IngestPhotosBody()
    cfg = load_config()
    provider = LocalPhotoIngress(cfg)
    provider.start(ro_id, body.tag)
    found = provider.ingest_inbox()
    if not found:
        raise HTTPException(404, "No images in inbox")
    order = attach_photos(
        store,
        order,
        found,
        tag=(body.tag or "other").strip() or "other",
        notes=(body.notes or "").strip(),
    )
    for p in found:
        try:
            p.unlink()
        except OSError:
            pass
    _maybe_push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/photos/phone")
def start_phone_upload(ro_id: str, body: PhoneUploadBody | None = None) -> dict[str, Any]:
    """Create a Tailscale phone / Shortcut upload session (needs server_url)."""
    order = _require_order(ro_id)
    body = body or PhoneUploadBody()
    remote = RemoteClient()
    if not remote.enabled:
        raise HTTPException(
            400,
            "Configure server_url first (Settings → Server URL).",
        )
    try:
        remote.upsert_ro(order)
    except Exception as exc:
        raise HTTPException(502, f"Could not sync RO to server: {exc}") from exc
    mode = body.mode or "phone"
    ttl = 3600 if mode == "phone" else 7 * 24 * 3600
    kind = "web" if mode == "phone" else "shortcut"
    try:
        sess = remote.create_upload_session(
            ro_id, tag=body.tag or "intake", ttl_sec=ttl, kind=kind
        )
    except Exception as exc:
        raise HTTPException(502, f"Upload session failed: {exc}") from exc
    path = sess.get("path") or f"/u/{sess['token']}"
    url = f"{remote.base.rstrip('/')}{path}"
    help_url = f"{remote.base.rstrip('/')}{sess.get('shortcut_path') or path + '/shortcut'}"
    return {
        "token": sess.get("token"),
        "url": url,
        "help_url": help_url,
        "tag": body.tag or "intake",
        "mode": mode,
        "ttl_sec": ttl,
    }


@app.post("/ros/{ro_id}/photos/refresh")
def refresh_photos_from_server(ro_id: str) -> dict[str, Any]:
    """Pull photo metadata + files after a phone/Shortcut upload."""
    order = _require_order(ro_id)
    remote = RemoteClient()
    if not remote.enabled:
        raise HTTPException(400, "No server_url configured")
    try:
        remote_data = remote.get_ro(ro_id)
        updated = RepairOrder.from_dict(remote_data)
        seen = {p.get("id") for p in order.photos}
        for p in updated.photos:
            if p.get("id") not in seen:
                order.photos.append(p)
        if len(updated.photos) > len(order.photos):
            order.photos = list(updated.photos)
        store.save(order, mark_pending_sync=False)
        paths = ensure_local_photos(order)
    except Exception as exc:
        raise HTTPException(502, f"Refresh failed: {exc}") from exc
    return {
        **order.to_dict(),
        "_local_files": len(paths),
    }


@app.get("/ros/{ro_id}/photos/file/{relpath:path}")
def get_photo_file(ro_id: str, relpath: str) -> FileResponse:
    """Serve a local photo file for the GUI preview."""
    from carro.config import photos_dir

    order = _require_order(ro_id)
    name = Path(relpath).name
    path = photos_dir() / ro_id / name
    if not path.is_file():
        ensure_local_photos(order)
    if not path.is_file():
        raise HTTPException(404, "Photo file not found")
    return FileResponse(path)


@app.get("/history")
def get_history(
    vin: str = "",
    name: str = "",
    exclude_id: str | None = None,
    unique_cars: bool = False,
) -> dict[str, Any]:
    """VIN-first vehicle history (local + server when configured). Offline → local only.

    unique_cars=true collapses many ROs for the same vehicle down to the latest
    visit — used when prefilling a new RO or appointment.
    """
    if not (vin or "").strip() and not (name or "").strip():
        raise HTTPException(400, "Provide vin and/or name")
    result = vehicle_history(
        store,
        vin=vin,
        name=name,
        exclude_id=exclude_id or None,
        unique_cars=unique_cars,
    )
    remote = RemoteClient()
    return {
        "orders": [o.to_dict() for o in result.orders],
        "matched_by": result.matched_by,
        "vin_query": result.vin_query,
        "name_query": result.name_query,
        "remote_enabled": bool(remote.enabled),
        "remote_ok": result.remote_ok,
        "note": result.note,
    }


@app.post("/history/pack")
def history_pack(body: HistoryPackBody) -> dict[str, Any]:
    """Write a text or PDF history pack (same as CLI history flow)."""
    from carro.core.history_pack import (
        estimate_pack_pages,
        write_pdf_pack,
        write_text_pack,
    )

    result = vehicle_history(
        store,
        vin=body.vin,
        name=body.name,
        exclude_id=body.exclude_id or None,
    )
    if not result.orders:
        raise HTTPException(404, "No prior repair history for that query")
    if body.kind == "text":
        path = write_text_pack(
            result.orders, vin=result.vin_query, name=result.name_query
        )
        return {"path": str(path), "kind": "text", "count": len(result.orders)}
    include_photos = body.kind == "pdf"
    pages = estimate_pack_pages(result.orders, include_photos=include_photos)
    path = write_pdf_pack(
        result.orders,
        vin=result.vin_query,
        name=result.name_query,
        include_photos=include_photos,
    )
    return {
        "path": str(path),
        "kind": body.kind,
        "count": len(result.orders),
        "estimated_pages": round(pages, 1),
    }


@app.post("/history/new-from")
def history_new_from(body: HistoryNewFromBody) -> dict[str, Any]:
    """Create a new RO copying customer + vehicle fields from a prior job.

    Offline-safe: uses local cache first. If the prior is only on the shop server
    and the server is unreachable, returns 503 with a clear message (Blank RO
    still works). Push to server is best-effort via try_push_ro.
    """
    prior_id = (body.prior_id or "").strip()
    if not prior_id:
        raise HTTPException(400, "prior_id required")
    prior = store.get(prior_id)
    offline_note = ""
    if not prior:
        remote = RemoteClient()
        if remote.enabled:
            try:
                from carro.core.history import _HISTORY_REMOTE_TIMEOUT

                raw = remote.get_ro(prior_id, timeout=_HISTORY_REMOTE_TIMEOUT)
                prior = RepairOrder.from_dict(raw)
                # Cache so the next road-test gap can still use this prior
                store.save(prior, mark_pending_sync=False)
                prior = store.get(prior_id) or prior
            except Exception:
                raise HTTPException(
                    503,
                    "That prior job isn't on this laptop and the shop server is "
                    "unreachable (Wi-Fi gap). Use a match already on this bay, "
                    "Blank RO, or sync when you're back online.",
                ) from None
        else:
            raise HTTPException(404, "Prior RO not found")
    fields = customer_vehicle_fields_from(prior)
    order = store.create(**fields)
    tech = techmod.current_technician()
    if tech:
        order.technician_id = tech.id
        order.technician_name = tech.name
        store.save(order)
    who, who_id = _actor_from(
        tech, advmod.current_advisor(), prefer=body.prefer_actor or "advisor"
    )
    push = _push_ro(order, actor=who, actor_id=who_id)
    out = order.to_dict()
    if isinstance(push, dict) and push.get("ok") is False:
        offline_note = (
            "Created on this bay — shop server unreachable; will sync when online."
        )
    if offline_note:
        out["_note"] = offline_note
    return out


class OpenFileBody(BaseModel):
    path: str


@app.post("/files/open")
def open_local_file(body: OpenFileBody) -> dict[str, Any]:
    """Open a PDF under the Car-RO data dir in the system viewer (GUI View PDF)."""
    from carro.config import DATA_DIR
    from carro.core.pdf_open import open_pdf_viewer

    path = Path(body.path).expanduser().resolve()
    root = DATA_DIR.resolve()
    if path != root and root not in path.parents:
        raise HTTPException(403, "Path not under Car-RO data directory")
    if not path.is_file():
        raise HTTPException(404, "File not found")
    viewer = open_pdf_viewer(path)
    return {"path": str(path), "opened": bool(viewer), "viewer": viewer}


@app.post("/sync")
def sync() -> dict[str, Any]:
    """Push local ROs to the shop server. Local data is always kept if the server is down."""
    try:
        result = perform_sync(store)
    except Exception as exc:
        pending = store.sync_status()
        raise HTTPException(
            502,
            f"Sync failed (local data kept; {pending.get('pending_total', 0)} pending): {exc}",
        ) from exc
    out = dict(result)
    out["autosync"] = autosync_status()
    out["pending"] = result.get("pending") or store.sync_status()
    return out


@app.get("/sync/status")
def sync_status_route() -> dict[str, Any]:
    """How many local edits are waiting to reach the shop server."""
    from carro.core.connectivity import server_connectivity

    conn = server_connectivity()
    pending = store.sync_status()
    return {
        "ok": True,
        "autosync": autosync_status(),
        "pending": pending,
        "server_configured": bool(conn.get("configured")),
        "server_reachable": bool(conn.get("reachable")),
        "offline": bool(conn.get("offline")),
        "connectivity_error": conn.get("error"),
    }


def _config_public(cfg: dict | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    photos = cfg.get("photos") or {}
    ro_keep = resolve_local_keep(cfg)
    photo_keep = resolve_local_photo_keep(cfg)
    billed_keep = resolve_local_billed_keep(cfg)
    info = disk_info()
    logo_label, _ok = logo_status(cfg)
    return {
        "config_file": str(CONFIG_FILE),
        "shop_name": cfg.get("shop_name") or "",
        "server_url": cfg.get("server_url") or "",
        "token_set": bool(cfg.get("token")),
        "theme": cfg.get("gui_theme") or "",
        "textual_theme": cfg.get("textual_theme") or "ansi-dark",
        "logo_path": cfg.get("logo_path") or "",
        "logo_status": logo_label,
        "local_keep": cfg.get("local_keep", "auto"),
        "local_keep_resolved": ro_keep,
        "local_keep_display": format_keep_setting(cfg.get("local_keep"), ro_keep),
        "local_photo_keep": cfg.get("local_photo_keep", "auto"),
        "local_photo_keep_resolved": photo_keep,
        "local_photo_keep_display": format_keep_setting(
            cfg.get("local_photo_keep"), photo_keep
        ),
        "local_billed_keep": billed_keep,
        "local_parts_received_keep_hours": resolve_local_parts_received_keep_hours(cfg),
        "idle_nudge_hours": resolve_idle_nudge_hours(cfg),
        "photos_dir": str(photos.get("dir") or ""),
        "photos_inbox_dir": str(photos.get("inbox_dir") or ""),
        "photos_provider": str(photos.get("provider") or "local"),
        "autosync_minutes": int(cfg.get("autosync_minutes") or 0),
        "pa_inspection_types": resolve_pa_inspection_types(cfg),
        "autosync": autosync_status(),
        "sync_pending": store.sync_status(),
        "disk": {
            "path": info["path"],
            "free_gb": round(info["free_gb"], 1),
            "total_gb": round(info["total_gb"], 1),
        },
        "recommend": {
            "local_keep": recommend_local_keep(),
            "local_photo_keep": recommend_local_photo_keep(
                ro_keep=recommend_local_keep()
            ),
        },
        "keep_presets": [
            {"label": a, "value": b if b is not None else "custom", "detail": c}
            for a, b, c in keep_presets()
        ],
        "photo_keep_presets": [
            {"label": a, "value": b if b is not None else "custom", "detail": c}
            for a, b, c in photo_keep_presets(ro_keep=ro_keep)
        ],
    }


@app.get("/config")
def get_config() -> dict[str, Any]:
    return _config_public()


@app.put("/config")
def put_config(body: ConfigBody) -> dict[str, Any]:
    cfg = load_config()
    if body.shop_name is not None:
        cfg["shop_name"] = body.shop_name
    if body.server_url is not None:
        cfg["server_url"] = body.server_url.rstrip("/")
    if body.clear_token:
        cfg["token"] = ""
    elif body.token is not None and body.token.strip():
        cfg["token"] = body.token.strip()
    if body.theme is not None:
        cfg["gui_theme"] = body.theme
    if body.textual_theme is not None:
        cfg["textual_theme"] = body.textual_theme.strip() or "ansi-dark"
    if body.logo_path is not None:
        cfg["logo_path"] = body.logo_path.strip()
    if body.local_keep is not None:
        cfg["local_keep"] = _parse_keep(body.local_keep)
    if body.local_photo_keep is not None:
        cfg["local_photo_keep"] = _parse_keep(body.local_photo_keep, allow_match=True)
    if body.local_billed_keep is not None:
        if body.local_billed_keep < 0:
            raise HTTPException(400, "local_billed_keep must be >= 0")
        cfg["local_billed_keep"] = int(body.local_billed_keep)
    if body.local_parts_received_keep_hours is not None:
        if body.local_parts_received_keep_hours < 0:
            raise HTTPException(400, "local_parts_received_keep_hours must be >= 0")
        cfg["local_parts_received_keep_hours"] = float(
            body.local_parts_received_keep_hours
        )
    if body.idle_nudge_hours is not None:
        if body.idle_nudge_hours < 0:
            raise HTTPException(400, "idle_nudge_hours must be >= 0 (0 = off)")
        cfg["idle_nudge_hours"] = float(body.idle_nudge_hours)
    if body.autosync_minutes is not None:
        if body.autosync_minutes < 0:
            raise HTTPException(400, "autosync_minutes must be >= 0 (0 = off)")
        cfg["autosync_minutes"] = int(body.autosync_minutes)
    if body.pa_inspection_types is not None:
        cfg["pa_inspection_types"] = bool(body.pa_inspection_types)
    photos = cfg.setdefault("photos", {})
    if body.photos_dir is not None:
        photos["dir"] = str(Path(body.photos_dir).expanduser()) if body.photos_dir else ""
    if body.photos_inbox_dir is not None:
        photos["inbox_dir"] = (
            str(Path(body.photos_inbox_dir).expanduser()) if body.photos_inbox_dir else ""
        )
    if body.photos_provider is not None:
        photos["provider"] = body.photos_provider.strip() or "local"
    save_config(cfg)
    ensure_dirs(cfg)
    if body.shop_name is not None or body.logo_path is not None:
        from carro.core import shop_branding as brandmod
        from carro.core.models import now_iso

        brandmod.save_meta({"updated": now_iso(), "source": "local"})
        try:
            brandmod.push_to_server()
        except Exception:
            pass
    return {"ok": True, **_config_public(cfg)}


@app.post("/config/logo")
async def upload_shop_logo(file: UploadFile = File(...)) -> dict[str, Any]:
    """Install a shop logo for PDF headers (copies into ~/.config/carro/)."""
    name = Path(file.filename or "logo.png").name
    suffix = Path(name).suffix.lower() or ".png"
    tmp_dir = Path(tempfile.mkdtemp(prefix="carro-logo-"))
    tmp = tmp_dir / f"upload{suffix}"
    try:
        data = await file.read()
        if not data:
            raise HTTPException(400, "Empty file")
        tmp.write_bytes(data)
        dest = install_logo(tmp)
    except HTTPException:
        raise
    except (OSError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    try:
        from carro.core import shop_branding as brandmod
        from carro.core.models import now_iso

        brandmod.save_meta({"updated": now_iso(), "source": "local"})
        brandmod.push_to_server()
    except Exception:
        pass
    return {"ok": True, "logo_path": str(dest), **_config_public()}


@app.delete("/config/logo")
def delete_shop_logo() -> dict[str, Any]:
    """Clear the shop PDF logo (shop name only on exports)."""
    clear_logo()
    try:
        from carro.core import shop_branding as brandmod
        from carro.core.models import now_iso

        brandmod.save_meta({"updated": now_iso(), "source": "local"})
        brandmod.push_to_server()
    except Exception:
        pass
    return {"ok": True, **_config_public()}


@app.get("/config/logo/file")
def shop_logo_file() -> FileResponse:
    """Serve the current shop logo for Config preview."""
    _label, path = logo_status()
    if not path or not path.is_file():
        raise HTTPException(404, "No shop logo configured")
    return FileResponse(path)


@app.post("/config/generate-token")
def generate_token() -> dict[str, Any]:
    cfg = load_config()
    token = secrets.token_urlsafe(24)
    cfg["token"] = token
    save_config(cfg)
    return {"ok": True, "token": token, **_config_public(cfg)}


@app.post("/config/apply-disk-recommendation")
def apply_disk_recommendation() -> dict[str, Any]:
    cfg = load_config()
    cfg["local_keep"] = "auto"
    cfg["local_photo_keep"] = "auto"
    save_config(cfg)
    ensure_dirs(cfg)
    return {"ok": True, **_config_public(cfg)}


def _parse_keep(value: str | int, *, allow_match: bool = False) -> str | int:
    if isinstance(value, int):
        if value < 0:
            raise HTTPException(400, "Keep count must be >= 0")
        return value
    raw = str(value).strip().lower()
    if raw in {"auto", "dynamic", ""}:
        return "auto"
    if allow_match and raw == "match":
        return "match"
    try:
        n = int(raw)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid keep value: {value}") from exc
    if n < 0:
        raise HTTPException(400, "Keep count must be >= 0")
    return n


def _maybe_push_ro(order: RepairOrder) -> dict[str, Any]:
    return _push_ro(order)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "carro_engine.main:app",
        host="127.0.0.1",
        port=int(__import__("os").environ.get("CARRO_ENGINE_PORT", "8788")),
        reload=False,
    )


if __name__ == "__main__":
    main()
