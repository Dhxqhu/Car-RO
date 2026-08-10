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
from obd_engine.doip_routes import router as doip_router  # noqa: E402
from obd_engine.main import router as obd_router  # noqa: E402

store = LocalStore()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    start_autosync(store)
    try:
        yield
    finally:
        stop_autosync()


app = FastAPI(title="carro-engine", version="0.1.0", lifespan=_lifespan)
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


class AddTechBody(BaseModel):
    name: str
    pin: str
    admin_pin: str | None = Field(default=None, alias="admin_pin")

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
    return {"ok": True, "shop_name": cfg.get("shop_name") or ""}


def _push_ro(order: RepairOrder) -> None:
    """Upsert to shop server, stamping the logged-in tech as actor (not notified of self)."""
    remote = RemoteClient()
    if not remote.enabled:
        return
    tech = techmod.current_technician()
    try:
        remote.upsert_ro(
            order,
            actor=(tech.name if tech else order.technician_name) or "",
            actor_id=(tech.id if tech else order.technician_id) or "",
        )
    except Exception:
        pass


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


@app.get("/technicians")
def list_technicians() -> dict[str, Any]:
    techs = [{"id": t.id, "name": t.name} for t in techmod.list_technicians()]
    return {"technicians": techs}


@app.post("/technicians")
def add_technician(body: AddTechBody) -> dict[str, str]:
    if techmod.admin_unlocked():
        pass
    elif body.admin_pin and techmod.verify_admin_pin(body.admin_pin):
        pass
    else:
        raise HTTPException(403, "Admin unlock or correct admin PIN required")
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


@app.get("/session")
def session() -> dict[str, Any]:
    tech = techmod.current_technician()
    if not tech:
        return {"technician": None}
    return {"technician": {"id": tech.id, "name": tech.name}}


@app.post("/session/login")
def login(body: LoginBody) -> dict[str, Any]:
    try:
        tech = techmod.login_technician(body.tech_id, body.pin)
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc
    return {"technician": {"id": tech.id, "name": tech.name}}


@app.post("/session/logout")
def logout() -> dict[str, bool]:
    techmod.clear_session()
    techmod.lock_admin()
    return {"ok": True}


class AdminUnlockBody(BaseModel):
    admin_pin: str = Field(alias="admin_pin")


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


class AdminTimeBody(BaseModel):
    """Correct forgotten/mistaken clocks — requires admin session."""

    action: Literal["set", "add", "clear"]
    minutes: int | None = None
    note: str = ""


def _require_admin() -> None:
    try:
        techmod.require_admin_session()
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


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
def admin_remove_tech(tech_id: str) -> dict[str, bool]:
    _require_admin()
    try:
        techmod.remove_technician(tech_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _push_technicians()
    return {"ok": True}


@app.post("/ros/{ro_id}/work-items/{item_id}/time/admin")
def admin_work_item_time(ro_id: str, item_id: str, body: AdminTimeBody) -> dict[str, Any]:
    """Edit item worked time (mistaken/forgotten clocks). Admin session required."""
    _require_admin()
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
                actor="admin",
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
                    note=body.note or f"admin adjust {mins}m",
                    actor="admin",
                )
            else:
                add_worked_minutes(
                    order,
                    item_id,
                    mins,
                    tech_id="",
                    tech_name="admin",
                    note=body.note or "admin correction",
                    source="admin",
                )
        elif body.action == "clear":
            admin_clear_time_log(
                order,
                item_id,
                note=body.note or "",
                actor="admin",
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
                store.save(order)
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
                store.save(order)
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


class PartPatchBody(BaseModel):
    description: str | None = None
    part_number: str | None = None
    manufacturer: str | None = None
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


@app.get("/assigned")
def assigned_board() -> dict[str, Any]:
    """Assigned Work board: mine, other techs, unassigned (local + server when configured)."""
    from carro.core.assignment import build_assigned_board

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
    board = build_assigned_board(
        list(by_id.values()),
        tech_id=tech.id if tech else "",
        tech_name=tech.name if tech else "",
    )
    board["source"] = source
    return board


@app.post("/ros/{ro_id}/assign")
def assign_ro_route(ro_id: str, body: AssignRoBody) -> dict[str, Any]:
    from carro.core.assignment import assign_ro

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    assign_ro(
        order,
        tech_id=body.assigned_to_id,
        tech_name=body.assigned_to_name,
        set_status_assigned=True,
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
        create_found_issue(
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
    return order.to_dict()


@app.post("/ros/{ro_id}/found-issues/{fi_id}/approve")
def found_issue_approve(
    ro_id: str, fi_id: str, body: FoundIssueApproveBody
) -> dict[str, Any]:
    from carro.core.found_issues import approve_found_issue

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician")
    try:
        approve_found_issue(
            order,
            fi_id,
            item_type=body.item_type or "repair",
            actor=tech.name,
            actor_id=tech.id,
            actor_role="advisor",
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
    from carro.core.found_issues import decline_found_issue

    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician")
    try:
        decline_found_issue(
            order,
            fi_id,
            reason=body.reason or "customer_declined",
            actor=tech.name,
            actor_id=tech.id,
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
    include_received: bool = False,
) -> dict[str, Any]:
    """Shop parts order sheet compiled from local ROs."""
    from carro.core.work_items import collect_parts_sheet

    rows = collect_parts_sheet(
        store.list_orders(),
        status=status,
        manufacturer=manufacturer,
        part_number=part_number,
        ro_id=ro_id,
        include_received=include_received,
    )
    return {"parts": rows, "count": len(rows)}


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
        ):
            update_part(
                order,
                item_id,
                part_id,
                description=body.description,
                part_number=body.part_number,
                manufacturer=body.manufacturer,
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
    if not store.delete(ro_id):
        raise HTTPException(500, "Local delete failed")
    photo_dir = photos_dir() / ro_id
    if photo_dir.is_dir():
        shutil.rmtree(photo_dir, ignore_errors=True)
    remote = RemoteClient()
    if remote.enabled:
        try:
            remote.delete_ro(ro_id)
        except Exception:
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
) -> dict[str, Any]:
    """Attach uploaded image files to an RO (same as CLI ``carro photo add``)."""
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    if not files:
        raise HTTPException(400, "No files uploaded")
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
        order = attach_photos(
            store,
            order,
            paths,
            tag=(tag or "other").strip() or "other",
            notes=(notes or "").strip(),
        )
        _maybe_push_ro(order)
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
        store.save(order)
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
    remote = RemoteClient()
    if not remote.enabled:
        return {"ok": True, "message": "No server_url configured — local only."}
    try:
        remote.health()
    except Exception as exc:
        raise HTTPException(502, f"Server unreachable: {exc}") from exc
    try:
        result = perform_sync(store)
    except Exception as exc:
        raise HTTPException(502, f"Sync failed: {exc}") from exc
    return {
        "ok": True,
        "message": result.get("message") or "Synced",
        "pushed": result.get("pushed"),
        "roster": result.get("roster"),
        "autosync": autosync_status(),
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


def _maybe_push_ro(order: RepairOrder) -> None:
    remote = RemoteClient()
    if not remote.enabled:
        return
    try:
        remote.upsert_ro(order)
    except Exception:
        pass


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
