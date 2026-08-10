"""Thin FastAPI wrapper around carro core for the desktop GUI."""

from __future__ import annotations

import secrets
import shutil
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
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
    save_config,
)
from carro.core import technicians as techmod  # noqa: E402
from carro.core import advisors as advmod  # noqa: E402
from carro.core.db import LocalStore  # noqa: E402
from carro.core.history import vehicle_fields_from, vehicle_history  # noqa: E402
from carro.core.logo_setup import logo_status  # noqa: E402
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
    start_autosync(store)
    try:
        yield
    finally:
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


class PhoneUploadBody(BaseModel):
    tag: str = "intake"
    mode: Literal["phone", "shortcut"] = "phone"


class IngestPhotosBody(BaseModel):
    tag: str = "intake"
    notes: str = ""


@app.get("/health")
def health() -> dict[str, Any]:
    cfg = load_config()
    return {"ok": True, "shop_name": cfg.get("shop_name") or "", **version_payload()}


@app.get("/version")
def version_info() -> dict[str, Any]:
    return {"ok": True, **version_payload()}


def _push_ro(order: RepairOrder) -> dict[str, Any]:
    """
    Upsert to shop server after local save. Failures leave the RO marked for retry —
    local SQLite data is never discarded.
    """
    from carro.core.sync_ops import try_push_ro

    tech = techmod.current_technician()
    adv = None
    try:
        from carro.core import advisors as advmod

        adv = advmod.current_advisor()
    except Exception:
        pass
    actor = ""
    actor_id = ""
    if adv:
        actor, actor_id = adv.name, adv.id
    elif tech:
        actor, actor_id = tech.name, tech.id
    return try_push_ro(
        store,
        order,
        actor=actor or order.technician_name or "",
        actor_id=actor_id or order.technician_id or "",
    )


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


def _messaging_actor() -> tuple[str, str, str]:
    """Return (id, name, role) for the logged-in tech or advisor."""
    advisor = advmod.current_advisor()
    if advisor:
        return advisor.id, advisor.name, "advisor"
    tech = techmod.current_technician()
    if tech:
        return tech.id, tech.name, "technician"
    raise HTTPException(401, "Log in as a technician or advisor to use messages")


def _require_remote_for_messages() -> RemoteClient:
    remote = RemoteClient()
    if not remote.enabled:
        raise HTTPException(
            400,
            "Shop messaging needs a server_url — messages are shared across bay PCs.",
        )
    return remote


@app.get("/messages/people")
def message_people() -> dict[str, Any]:
    """Combined roster for the compose picker (specific person only)."""
    techs = [
        {"id": t.id, "name": t.name, "role": "technician"}
        for t in techmod.list_technicians()
    ]
    advisors = [
        {"id": a.id, "name": a.name, "role": "advisor"}
        for a in advmod.list_advisors()
    ]
    me_id, _, _ = _messaging_actor()
    people = [p for p in techs + advisors if p["id"] != me_id]
    people.sort(key=lambda p: (p["role"], p["name"].lower()))
    return {"people": people, "server_required": True}


@app.get("/messages")
def get_messages(unread: bool = False, limit: int = 100) -> dict[str, Any]:
    remote = _require_remote_for_messages()
    me_id, _, _ = _messaging_actor()
    try:
        return remote.list_messages(for_id=me_id, unread=unread, limit=limit)
    except Exception as exc:
        raise HTTPException(
            502,
            f"Messages unavailable on server ({exc}). Update carro-server for shop messaging.",
        ) from exc


@app.get("/messages/sent")
def get_sent_messages(limit: int = 100) -> dict[str, Any]:
    remote = _require_remote_for_messages()
    me_id, _, _ = _messaging_actor()
    try:
        return remote.list_sent_messages(from_id=me_id, limit=limit)
    except Exception as exc:
        raise HTTPException(502, f"Messages unavailable on server ({exc})") from exc


@app.post("/messages")
def post_message(body: ShopMessageBody) -> dict[str, Any]:
    remote = _require_remote_for_messages()
    from_id, from_name, from_role = _messaging_actor()
    payload = {
        "body": body.body,
        "from_id": from_id,
        "from_name": from_name,
        "from_role": from_role,
        "to_id": body.to_id.strip(),
        "to_name": (body.to_name or "").strip(),
        "to_role": body.to_role,
        "ro_id": (body.ro_id or "").strip(),
        "work_item_id": (body.work_item_id or "").strip(),
        "reply_to": body.reply_to,
    }
    try:
        return remote.send_message(payload)
    except Exception as exc:
        raise HTTPException(502, f"Could not send message: {exc}") from exc


@app.post("/messages/{message_id}/read")
def post_message_read(message_id: int, body: MessageReadBody | None = None) -> dict[str, Any]:
    remote = _require_remote_for_messages()
    me_id, _, _ = _messaging_actor()
    for_id = (body.for_id if body else "") or me_id
    if for_id != me_id:
        raise HTTPException(403, "Can only mark your own inbox messages as read")
    try:
        return remote.mark_message_read(message_id, for_id=me_id)
    except Exception as exc:
        raise HTTPException(502, f"Could not mark read: {exc}") from exc


@app.post("/messages/{message_id}/renotify")
def post_message_renotify(message_id: int) -> dict[str, Any]:
    remote = _require_remote_for_messages()
    me_id, _, _ = _messaging_actor()
    try:
        return remote.renotify_message(message_id, from_id=me_id)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Could not renotify: {exc}") from exc


def _require_remote_for_shifts() -> RemoteClient:
    remote = RemoteClient()
    if not remote.enabled:
        raise HTTPException(
            503,
            "Day start/end needs shop server_url (presence is shared across bay PCs).",
        )
    return remote


@app.get("/shifts/active")
def engine_shifts_active() -> dict[str, Any]:
    remote = _require_remote_for_shifts()
    try:
        return remote.list_active_shifts()
    except Exception as exc:
        raise HTTPException(502, f"Shifts unavailable: {exc}") from exc


@app.get("/shifts/mine")
def engine_shift_mine() -> dict[str, Any]:
    remote = _require_remote_for_shifts()
    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician")
    try:
        return remote.get_open_shift(tech.id)
    except Exception as exc:
        raise HTTPException(502, f"Shifts unavailable: {exc}") from exc


@app.post("/shifts/start")
def engine_shift_start(body: ShiftStartBody | None = None) -> dict[str, Any]:
    remote = _require_remote_for_shifts()
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
        return remote.start_shift(
            tech_id=tech_id,
            tech_name=tech_name,
            started_at=started_at,
            day=day,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Could not day-start: {exc}") from exc


@app.post("/shifts/end")
def engine_shift_end(body: ShiftEndBody | None = None) -> dict[str, Any]:
    remote = _require_remote_for_shifts()
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
        return remote.end_shift(
            tech_id=tech_id, shift_id=shift_id, ended_at=ended_at
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Could not day-end: {exc}") from exc


@app.get("/shifts")
def engine_list_shifts(
    tech_id: str = "",
    day_from: str = "",
    day_to: str = "",
    limit: int = 200,
) -> dict[str, Any]:
    remote = _require_remote_for_shifts()
    if not advmod.current_advisor() and not techmod.current_technician():
        raise HTTPException(401, "Login required")
    try:
        return remote.list_shifts(
            tech_id=tech_id, day_from=day_from, day_to=day_to, limit=limit
        )
    except Exception as exc:
        raise HTTPException(502, f"Shifts unavailable: {exc}") from exc


@app.patch("/shifts/{shift_id}")
def engine_patch_shift(
    shift_id: int, body: ShiftPatchBody | None = None
) -> dict[str, Any]:
    remote = _require_remote_for_shifts()
    body = body or ShiftPatchBody()
    advisor = advmod.current_advisor()
    tech = techmod.current_technician()
    if not advisor and not tech:
        raise HTTPException(401, "Log in as a technician or advisor")

    # Resolve the punch so techs can only edit their own
    try:
        listed = remote.list_shifts(limit=2000).get("shifts") or []
    except Exception as exc:
        raise HTTPException(502, f"Shifts unavailable: {exc}") from exc
    target = next(
        (s for s in listed if int(s.get("id") or 0) == int(shift_id)),
        None,
    )
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
        return remote.update_shift(
            shift_id,
            started_at=body.started_at,
            ended_at=body.ended_at,
            clear_end=body.clear_end,
            day=body.day,
            edited_by=edited_by,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Could not edit shift: {exc}") from exc


@app.delete("/shifts/{shift_id}")
def engine_delete_shift(shift_id: int) -> dict[str, Any]:
    remote = _require_remote_for_shifts()
    if not advmod.current_advisor():
        raise HTTPException(401, "Only an advisor can delete punches")
    try:
        return remote.delete_shift(shift_id)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Could not delete shift: {exc}") from exc


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
    data = engine_weekly_report(week_start)
    live = data["live"]
    try:
        return remote.save_weekly_report(
            live["week_start"],
            week_end=live["week_end"],
            payload=live,
            created_by=advisor.name,
            created_by_id=advisor.id,
        )
    except Exception as exc:
        raise HTTPException(502, f"Could not save report: {exc}") from exc


@app.get("/technicians")
def list_technicians() -> dict[str, Any]:
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
            remote.put_technicians(techmod.roster_for_sync())
    except Exception:
        pass


def _push_advisors() -> None:
    try:
        remote = RemoteClient()
        if remote.enabled:
            remote.put_advisors(advmod.roster_for_sync())
    except Exception:
        pass


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
    advmod.clear_session()
    return {"technician": {"id": tech.id, "name": tech.name}, "role": "tech"}


@app.post("/session/logout")
def logout() -> dict[str, bool]:
    techmod.clear_session()
    advmod.clear_session()
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
    advisors = [{"id": a.id, "name": a.name} for a in advmod.list_advisors()]
    return {
        "advisors": advisors,
        "has_admin_pin": techmod.has_admin_pin(),
        "empty": not advisors,
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
        "advisor": {"id": advisor.id, "name": advisor.name},
        "role": "advisor",
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
    techmod.clear_session()
    return {
        "advisor": {"id": advisor.id, "name": advisor.name},
        "role": "advisor",
    }


@app.post("/advisor/session/logout")
def advisor_logout() -> dict[str, bool]:
    advmod.clear_session()
    techmod.lock_admin()
    return {"ok": True}


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

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
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


@app.post("/ros")
def create_ro() -> dict[str, Any]:
    order = store.create()
    tech = techmod.current_technician()
    if tech:
        order.technician_id = tech.id
        order.technician_name = tech.name
        store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.get("/ros/{ro_id}")
def get_ro(ro_id: str) -> dict[str, Any]:
    order = store.get(ro_id)
    if not order:
        remote = RemoteClient()
        if remote.enabled:
            try:
                raw = remote.get_ro(ro_id)
                order = RepairOrder.from_dict(raw)
                # Cache from server — do not mark dirty for re-push.
                store.save(order, mark_pending_sync=False)
            except Exception:
                order = None
        if not order:
            raise HTTPException(404, "RO not found")
    return order.to_dict()


@app.put("/ros/{ro_id}")
def put_ro(ro_id: str, body: dict[str, Any]) -> dict[str, Any]:
    body = dict(body)
    body["id"] = ro_id
    order = RepairOrder.from_dict(body)
    # Stamp tech if empty
    tech = techmod.current_technician()
    if tech and not order.technician_id:
        order.technician_id = tech.id
        order.technician_name = tech.name
    store.save(order)
    _push_ro(order)
    return order.to_dict()


class WorkItemBody(BaseModel):
    id: str | None = None
    concern: str | None = None
    notes: str | None = None
    private_notes: str | None = None
    item_type: str | None = None
    status: str | None = None
    priority: int | None = None


class FoundIssueComposeBody(BaseModel):
    item_id: str | None = None


class FoundIssueCreateBody(BaseModel):
    description: str
    notes: str = ""
    source_work_item_id: str | None = None
    finish_compose: bool = True


class FoundIssueApproveBody(BaseModel):
    item_type: str = "repair"


class FoundIssueDeclineBody(BaseModel):
    reason: str = "customer_declined"


class PartBody(BaseModel):
    description: str = ""
    part_number: str = ""
    manufacturer: str | None = None
    brand: str = ""


class PartPatchBody(BaseModel):
    description: str | None = None
    part_number: str | None = None
    manufacturer: str | None = None
    brand: str | None = None
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


class CurrentTaskBody(BaseModel):
    """Claim current bay work on a specific work item (item_id required when active)."""

    active: bool = True
    item_id: str | None = None


class QueueActionBody(BaseModel):
    """Queue/current actions. Item actions require item_id (work item, not RO)."""

    action: Literal[
        "add",
        "remove",
        "complete",
        "complete_item",
        "billed_out",
        "reopen",
        "waiting_parts",
        "request_parts",
        "item_waiting_parts",
        "waiting_customer",
        "request_approval",
        "item_waiting_customer",
    ]
    item_id: str | None = None


class RoFlagsBody(BaseModel):
    waiter: bool | None = None
    urgent: bool | None = None


class WorkItemQueueBody(BaseModel):
    """Advisor sets queue lane (daily / next_day / long_term)."""

    lane: Literal["daily", "next_day", "long_term"]
    approve_request: bool = False


class NextDayRequestBody(BaseModel):
    note: str = ""


class NextDayRequestDecisionBody(BaseModel):
    approve: bool = True


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
    # Midnight lane rollover on local copies we can save
    local_ids = {o.id for o in store.list_orders()}
    changed = rollover_all_orders(
        [o for o in by_id.values() if o.id in local_ids]
    )
    for order in changed:
        store.save(order)
        _push_ro(order)
        by_id[order.id] = order
    board = build_assigned_board(
        list(by_id.values()),
        tech_id=tech.id if tech else "",
        tech_name=tech.name if tech else "",
    )
    board["source"] = source
    return board


@app.post("/ros/{ro_id}/assign")
def assign_ro_route(ro_id: str, body: AssignRoBody) -> dict[str, Any]:
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.assignment import assign_ro, assign_work_item

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
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
        ):
            raise HTTPException(404, "Work item not found")
        append_advisor_action(
            order,
            action="assigned_to_tech",
            advisor_id=advisor.id,
            advisor_name=advisor.name,
            work_item_id=item_id,
            detail=f"{body.assigned_to_name or ''} ({body.assigned_to_id or ''})".strip(),
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

        order.status = body.status
        if body.status == "in_progress" and not (order.started_at or "").strip():
            order.started_at = now_iso()
        if body.status == "done":
            if not (order.done_at or "").strip():
                order.done_at = now_iso()
            order.waiting_since = ""
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
    _push_ro(order)
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
    if not tech:
        raise HTTPException(401, "Log in as a technician to set current work")
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")

    if body.active:
        for other in clear_tech_current_elsewhere(
            store.list_orders(),
            tech_id=tech.id,
            tech_name=tech.name,
            except_id=ro_id,
        ):
            store.save(other)
            _push_ro(other)
        try:
            set_current_task(
                order,
                tech_id=tech.id,
                tech_name=tech.name,
                item_id=(body.item_id or "").strip(),
                also_assign=True,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    else:
        if matches_tech(
            order.current_tech_id,
            order.current_tech_name,
            me_id=tech.id,
            me_name=tech.name,
        ):
            clear_current_task(order)
        else:
            raise HTTPException(403, "This is not your current work")
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/queue")
def queue_action_route(ro_id: str, body: QueueActionBody) -> dict[str, Any]:
    """
    Planned work queue for the logged-in tech:
    - add / remove
    - complete → advisor ready-to-bill queue
    - reopen → undo done / billed out back onto the floor
    - billed_out → final close (advisor after accounting)
    """
    from carro.core.assignment import (
        add_to_my_queue,
        bill_out_ro,
        complete_ro,
        complete_work_item,
        remove_from_my_queue,
        reopen_ro,
        request_customer_approval,
        request_parts,
        set_work_item_waiting,
    )

    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician to manage your queue")
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")

    item_id = (body.item_id or "").strip()

    if body.action == "add":
        try:
            add_to_my_queue(
                order,
                tech_id=tech.id,
                tech_name=tech.name,
                item_id=item_id,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    elif body.action == "remove":
        if not remove_from_my_queue(
            order,
            tech_id=tech.id,
            tech_name=tech.name,
            item_id=item_id,
        ):
            raise HTTPException(403, "This work item is not on your queue")
    elif body.action == "complete_item":
        try:
            complete_work_item(
                order,
                item_id or (order.current_item_id or ""),
                tech_id=tech.id,
                tech_name=tech.name,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    elif body.action == "complete":
        # Prefer item when item_id / current item present
        wid = item_id or (order.current_item_id or "").strip()
        if wid:
            try:
                complete_work_item(
                    order, wid, tech_id=tech.id, tech_name=tech.name
                )
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
        else:
            complete_ro(order, tech_id=tech.id, tech_name=tech.name)
    elif body.action == "reopen":
        try:
            reopen_ro(order, tech_id=tech.id, tech_name=tech.name)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    elif body.action == "billed_out":
        bill_out_ro(order, tech_id=tech.id, tech_name=tech.name)
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
    _push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/flags")
def ro_flags_route(ro_id: str, body: RoFlagsBody) -> dict[str, Any]:
    """Advisor sets waiter / urgent floor flags on the RO."""
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.queue_lanes import set_ro_flags

    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Log in as an advisor to set floor flags")
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
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
    _push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/work-items/{item_id}/queue")
def work_item_queue_lane_route(
    ro_id: str, item_id: str, body: WorkItemQueueBody
) -> dict[str, Any]:
    """Advisor moves a work item between daily / next_day / long_term."""
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.queue_lanes import advisor_set_queue_lane

    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Only an advisor can set queue lanes")
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    try:
        advisor_set_queue_lane(
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
    store.save(order)
    _push_ro(order)
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
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
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
    _push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/work-items/{item_id}/queue/request-decision")
def work_item_next_day_decision_route(
    ro_id: str, item_id: str, body: NextDayRequestDecisionBody
) -> dict[str, Any]:
    """Advisor approves (arms next_day) or declines a tech next-day request."""
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.queue_lanes import advisor_set_queue_lane, decline_next_day_request

    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Only an advisor can decide next-day requests")
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    try:
        if body.approve:
            advisor_set_queue_lane(
                order, item_id, "next_day", approve_request=True
            )
        else:
            decline_next_day_request(order, item_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    append_advisor_action(
        order,
        action="next_day_request_approved" if body.approve else "next_day_request_declined",
        advisor_id=advisor.id,
        advisor_name=advisor.name,
        work_item_id=item_id,
    )
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/work-items/{item_id}/queue/request-read")
def work_item_next_day_request_read_route(ro_id: str, item_id: str) -> dict[str, Any]:
    """Advisor marks a next-day request notification as read."""
    from carro.core.queue_lanes import mark_next_day_request_read

    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Only an advisor can mark queue requests read")
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    try:
        mark_next_day_request_read(order, item_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/work-items")
def upsert_work_item_route(ro_id: str, body: WorkItemBody) -> dict[str, Any]:
    from carro.core.work_items import upsert_work_item

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician to edit work items")
    try:
        upsert_work_item(
            order,
            item_id=body.id,
            concern=body.concern,
            notes=body.notes,
            private_notes=body.private_notes,
            item_type=body.item_type,
            status=body.status,
            priority=body.priority,
            actor=tech.name,
            actor_id=tech.id,
            actor_role="tech",
            require_item_type=not body.id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/found-issues/compose")
def found_issue_compose_begin(ro_id: str, body: FoundIssueComposeBody) -> dict[str, Any]:
    from carro.core.found_issues import begin_found_issue_compose

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician")
    try:
        begin_found_issue_compose(
            order,
            tech_id=tech.id,
            tech_name=tech.name,
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

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician")
    try:
        cancel_found_issue_compose(
            order,
            tech_id=tech.id,
            tech_name=tech.name,
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

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician")
    try:
        fi = create_found_issue(
            order,
            description=body.description,
            notes=body.notes,
            tech_id=tech.id,
            tech_name=tech.name,
            source_work_item_id=body.source_work_item_id or "",
            finish_compose=body.finish_compose,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order)
    out = order.to_dict()
    # Ephemeral — for clients that attach photos right after create
    out["created_found_issue_id"] = fi.id
    return out


@app.post("/ros/{ro_id}/found-issues/{fi_id}/approve")
def found_issue_approve(
    ro_id: str, fi_id: str, body: FoundIssueApproveBody
) -> dict[str, Any]:
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.found_issues import approve_found_issue

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Log in as an advisor to approve found issues")
    try:
        approve_found_issue(
            order,
            fi_id,
            item_type=body.item_type or "repair",
            actor=advisor.name,
            actor_id=advisor.id,
            actor_role="advisor",
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
    _push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/found-issues/{fi_id}/decline")
def found_issue_decline(
    ro_id: str, fi_id: str, body: FoundIssueDeclineBody
) -> dict[str, Any]:
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.found_issues import decline_found_issue

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    advisor = advmod.current_advisor()
    if not advisor:
        raise HTTPException(401, "Log in as an advisor to decline found issues")
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
    _push_ro(order)
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


@app.get("/parts/suggest")
def parts_suggest_route(q: str = "", limit: int = 25) -> dict[str, Any]:
    """Catalog suggestions for add-part lookup (server archive when available)."""
    remote = RemoteClient()
    if remote.enabled:
        try:
            return remote.parts_suggest(q=q, limit=limit)
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
        if qn and qn not in f"{desc} {pn} {mfr} {brand}".lower():
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
    return {"suggestions": suggestions, "count": len(suggestions), "source": "local"}


@app.get("/notifications/idle")
def idle_notifications() -> dict[str, Any]:
    """Work items / parts with no activity for idle_nudge_hours (default 24)."""
    from carro.core.idle_nudge import collect_idle_nudges

    cfg = load_config()
    hours = resolve_idle_nudge_hours(cfg)
    rows = collect_idle_nudges(store.list_orders(), idle_hours=hours)
    return {
        "idle": rows,
        "count": len(rows),
        "idle_nudge_hours": hours,
        "enabled": hours > 0,
    }


@app.post("/ros/{ro_id}/work-items/{item_id}/parts")
def add_part_route(ro_id: str, item_id: str, body: PartBody) -> dict[str, Any]:
    from carro.core.work_items import add_part

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician to edit parts")
    try:
        add_part(
            order,
            item_id,
            description=body.description,
            part_number=body.part_number,
            manufacturer=body.manufacturer,
            brand=body.brand or "",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.patch("/ros/{ro_id}/work-items/{item_id}/parts/{part_id}")
def patch_part_route(
    ro_id: str, item_id: str, part_id: str, body: PartPatchBody
) -> dict[str, Any]:
    from carro.core.work_items import set_part_status, update_part

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician to edit parts")
    try:
        if (
            body.description is not None
            or body.part_number is not None
            or body.manufacturer is not None
            or body.brand is not None
        ):
            update_part(
                order,
                item_id,
                part_id,
                description=body.description,
                part_number=body.part_number,
                manufacturer=body.manufacturer,
                brand=body.brand,
            )
        if body.status is not None:
            set_part_status(
                order,
                item_id,
                part_id,
                body.status,
                wrong_note=body.wrong_note or "",
                actor=tech.name,
                actor_id=tech.id,
            )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.delete("/ros/{ro_id}/work-items/{item_id}/parts/{part_id}")
def delete_part_route(ro_id: str, item_id: str, part_id: str) -> dict[str, Any]:
    from carro.core.work_items import remove_part

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician to edit parts")
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

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
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
            )
        elif body.action == "stop":
            stop_work_timer(order, item_id)
            if (order.current_item_id or "") == item_id and matches_tech(
                order.current_tech_id,
                order.current_tech_name,
                me_id=tech.id,
                me_name=tech.name,
            ):
                # clear_current would double-stop; already stopped this item
                order.current_tech_id = ""
                order.current_tech_name = ""
                order.current_since = ""
                order.current_item_id = ""
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


@app.delete("/ros/{ro_id}/work-items/{item_id}")
def delete_work_item_route(ro_id: str, item_id: str) -> dict[str, Any]:
    from carro.core.work_items import remove_work_item

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    if not remove_work_item(order, item_id):
        raise HTTPException(404, f"Work item not found: {item_id}")
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.delete("/ros/{ro_id}")
def delete_ro(ro_id: str) -> dict[str, Any]:
    from carro.config import photos_dir

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
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

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
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

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
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

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
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
def pull_obd_ro(ro_id: str) -> dict[str, Any]:
    """Same handoff as CLI F2 / ``carro pull-obd`` — last_vehicle + Saved Codes."""
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    raw = pull_vehicle_fields(prefer_vin=order.vin or None)
    if not raw:
        raise HTTPException(404, "Nothing found from obdscan / Saved Codes")
    mapped = {
        "vin": raw.get("vin", ""),
        "year": raw.get("year", ""),
        "make": raw.get("make", ""),
        "obd_snapshot": raw.get("obd_snapshot", ""),
    }
    for key, val in mapped.items():
        if val:
            setattr(order, key, val)
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.get("/ros/{ro_id}/photos")
def list_photos(ro_id: str) -> dict[str, Any]:
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
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
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
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
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
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
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
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
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
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

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
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
) -> dict[str, Any]:
    """VIN-first vehicle history (local + server when configured)."""
    if not (vin or "").strip() and not (name or "").strip():
        raise HTTPException(400, "Provide vin and/or name")
    result = vehicle_history(
        store,
        vin=vin,
        name=name,
        exclude_id=exclude_id or None,
    )
    remote = RemoteClient()
    return {
        "orders": [o.to_dict() for o in result.orders],
        "matched_by": result.matched_by,
        "vin_query": result.vin_query,
        "name_query": result.name_query,
        "remote_enabled": bool(remote.enabled),
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
    """Create a new RO copying vehicle fields from a prior job."""
    prior = store.get(body.prior_id)
    if not prior:
        raise HTTPException(404, "Prior RO not found")
    fields = vehicle_fields_from(prior)
    order = store.create(**fields)
    tech = techmod.current_technician()
    if tech:
        order.technician_id = tech.id
        order.technician_name = tech.name
        store.save(order)
    _push_ro(order)
    return order.to_dict()


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
    return {
        "ok": True,
        "autosync": autosync_status(),
        "pending": store.sync_status(),
        "server_configured": RemoteClient().enabled,
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
    return {"ok": True, **_config_public(cfg)}


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
