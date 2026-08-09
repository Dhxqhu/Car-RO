"""Thin FastAPI wrapper around carro core for the desktop GUI."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Allow running from repo without install
_ROOT = Path(__file__).resolve().parents[2]
_CLI = _ROOT / "cli"
_SERVER = _ROOT / "server"
for p in (_CLI, _SERVER):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from carro.config import load_config, save_config  # noqa: E402
from carro.core import technicians as techmod  # noqa: E402
from carro.core.db import LocalStore  # noqa: E402
from carro.core.models import RepairOrder  # noqa: E402
from carro.core.pdf import export_pdf  # noqa: E402
from carro.obd.provider import pull_vehicle_fields  # noqa: E402
from carro.storage.remote import RemoteClient  # noqa: E402
from obd_engine.main import router as obd_router  # noqa: E402

app = FastAPI(title="carro-engine", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(obd_router)

store = LocalStore()


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
    theme: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    cfg = load_config()
    return {"ok": True, "shop_name": cfg.get("shop_name") or ""}


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
    remote = RemoteClient()
    if remote.enabled:
        try:
            remote.upsert_ro(order)
        except Exception:
            pass
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
def pdf_ro(ro_id: str) -> dict[str, str]:
    order = store.get(ro_id)
    if not order:
        raise HTTPException(404, "RO not found")
    path = export_pdf(order)
    return {"path": str(path)}


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


@app.post("/sync")
def sync() -> dict[str, Any]:
    remote = RemoteClient()
    if not remote.enabled:
        return {"ok": True, "message": "No server_url configured — local only."}
    try:
        remote.health()
    except Exception as exc:
        raise HTTPException(502, f"Server unreachable: {exc}") from exc
    # Roster sync
    try:
        from carro.core.tech_ui import sync_roster_with_server

        roster_status = sync_roster_with_server()
    except Exception:
        roster_status = "skipped"
    n = 0
    for order in store.list_orders():
        remote.upsert_ro(order)
        n += 1
    store.prune()
    return {
        "ok": True,
        "message": f"Pushed {n} RO(s); technician roster: {roster_status}",
    }


@app.get("/config")
def get_config() -> dict[str, Any]:
    cfg = load_config()
    return {
        "shop_name": cfg.get("shop_name") or "",
        "server_url": cfg.get("server_url") or "",
        "token_set": bool(cfg.get("token")),
        "theme": cfg.get("gui_theme") or "",
    }


@app.put("/config")
def put_config(body: ConfigBody) -> dict[str, bool]:
    cfg = load_config()
    if body.shop_name is not None:
        cfg["shop_name"] = body.shop_name
    if body.server_url is not None:
        cfg["server_url"] = body.server_url.rstrip("/")
    if body.token is not None and body.token.strip():
        cfg["token"] = body.token.strip()
    if body.theme is not None:
        cfg["gui_theme"] = body.theme
    save_config(cfg)
    return {"ok": True}


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
