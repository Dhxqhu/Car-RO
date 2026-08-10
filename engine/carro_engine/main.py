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
    resolve_local_keep,
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
    admin_pin: str = Field(alias="admin_pin")

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
    if not techmod.verify_admin_pin(body.admin_pin):
        raise HTTPException(403, "Incorrect admin PIN")
    try:
        tech = techmod.add_technician(body.name, body.pin)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    # Best-effort push
    try:
        remote = RemoteClient()
        if remote.enabled:
            remote.put_technicians(techmod.roster_for_sync())
    except Exception:
        pass
    return {"id": tech.id, "name": tech.name}


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
    return {"ok": True}


@app.get("/ros")
def list_ros(q: str = "") -> dict[str, Any]:
    if q.strip():
        orders = store.search(q.strip())
    else:
        orders = store.list_orders(limit=50)
    return {"orders": [o.to_dict() for o in orders]}


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
    status: str | None = None
    priority: int | None = None


class AssignRoBody(BaseModel):
    assigned_to_id: str = ""
    assigned_to_name: str = ""
    status: str | None = None


class CurrentTaskBody(BaseModel):
    """Set active=true to claim this RO as the logged-in tech's current bay task."""

    active: bool = True


class QueueActionBody(BaseModel):
    """Planned queue + completion / waiting / billed-out for the logged-in tech."""

    action: Literal[
        "add",
        "remove",
        "complete",
        "billed_out",
        "waiting_parts",
        "waiting_customer",
    ]


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
    """Claim or release this RO as the logged-in tech's current task (visible on Assigned)."""
    from carro.core.assignment import (
        clear_current_task,
        clear_tech_current_elsewhere,
        matches_tech,
        set_current_task,
    )

    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician to set current task")
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
        set_current_task(order, tech_id=tech.id, tech_name=tech.name, also_assign=True)
    else:
        if matches_tech(
            order.current_tech_id,
            order.current_tech_name,
            me_id=tech.id,
            me_name=tech.name,
        ):
            clear_current_task(order)
        else:
            raise HTTPException(403, "This RO is not your current task")
    store.save(order)
    _push_ro(order)
    return order.to_dict()


@app.post("/ros/{ro_id}/queue")
def queue_action_route(ro_id: str, body: QueueActionBody) -> dict[str, Any]:
    """
    Planned work queue for the logged-in tech:
    - add / remove / complete (work finished)
    - billed_out (car left)
    - waiting_parts / waiting_customer (parked)
    """
    from carro.core.assignment import (
        add_to_my_queue,
        bill_out_ro,
        complete_ro,
        remove_from_my_queue,
        set_waiting,
    )

    tech = techmod.current_technician()
    if not tech:
        raise HTTPException(401, "Log in as a technician to manage your queue")
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")

    if body.action == "add":
        add_to_my_queue(order, tech_id=tech.id, tech_name=tech.name)
    elif body.action == "remove":
        if not remove_from_my_queue(order, tech_id=tech.id, tech_name=tech.name):
            raise HTTPException(403, "This RO is not on your queue")
    elif body.action == "complete":
        complete_ro(order, tech_id=tech.id, tech_name=tech.name)
    elif body.action == "billed_out":
        bill_out_ro(order, tech_id=tech.id, tech_name=tech.name)
    elif body.action in ("waiting_parts", "waiting_customer"):
        set_waiting(
            order,
            kind=body.action,
            tech_id=tech.id,
            tech_name=tech.name,
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
    upsert_work_item(
        order,
        item_id=body.id,
        concern=body.concern,
        notes=body.notes,
        status=body.status,
        priority=body.priority,
        actor=tech.name,
        actor_id=tech.id,
        actor_role="tech",
    )
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
