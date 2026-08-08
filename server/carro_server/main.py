"""carro-server: remote repair-order + multi-volume photo storage."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from carro_server.upload_tokens import SHORTCUT_PAGE, UPLOAD_PAGE, UploadTokenStore
from carro_server.volumes import VolumeManager

TOKEN = os.environ.get("CARRO_TOKEN", "").strip()
VOLUMES = VolumeManager()
UPLOADS = UploadTokenStore(VOLUMES.root / "upload_sessions.json")


def _db() -> sqlite3.Connection:
    path = VOLUMES.db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS repair_orders (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            updated TEXT NOT NULL
        )
        """
    )
    return conn


def require_auth(authorization: str | None = Header(default=None)) -> None:
    if not TOKEN:
        return  # open mode for first-time lab use; set CARRO_TOKEN in production
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    if authorization.removeprefix("Bearer ").strip() != TOKEN:
        raise HTTPException(403, "Invalid token")


app = FastAPI(title="carro-server", version="0.1.0")


def _technicians_path() -> Path:
    return VOLUMES.root / "technicians.json"


def _load_technicians() -> dict:
    path = _technicians_path()
    if not path.is_file():
        return {
            "version": 1,
            "updated": "",
            "admin_pin_hash": "",
            "technicians": [],
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "version": 1,
            "updated": "",
            "admin_pin_hash": "",
            "technicians": [],
        }
    if not isinstance(raw, dict):
        return {
            "version": 1,
            "updated": "",
            "admin_pin_hash": "",
            "technicians": [],
        }
    techs = raw.get("technicians")
    if not isinstance(techs, list):
        techs = []
    return {
        "version": 1,
        "updated": str(raw.get("updated") or ""),
        "admin_pin_hash": str(raw.get("admin_pin_hash") or ""),
        "technicians": [t for t in techs if isinstance(t, dict)],
    }


@app.get("/health")
def health(_: None = Depends(require_auth)):
    vols = {
        name: {"path": meta.get("path"), "role": meta.get("role")}
        for name, meta in VOLUMES.list_volumes().items()
    }
    return {
        "ok": True,
        "default_volume": VOLUMES.default_name,
        "volumes": vols,
    }


@app.get("/technicians")
def get_technicians(_: None = Depends(require_auth)):
    return _load_technicians()


@app.put("/technicians")
def put_technicians(body: dict, _: None = Depends(require_auth)):
    if not isinstance(body, dict):
        raise HTTPException(400, "JSON object required")
    techs = body.get("technicians")
    if techs is not None and not isinstance(techs, list):
        raise HTTPException(400, "technicians must be a list")
    payload = {
        "version": 1,
        "updated": str(body.get("updated") or ""),
        "admin_pin_hash": str(body.get("admin_pin_hash") or ""),
        "technicians": [t for t in (techs or []) if isinstance(t, dict)],
    }
    if not payload["updated"]:
        from datetime import datetime

        payload["updated"] = datetime.now().isoformat(timespec="seconds")
    path = _technicians_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, **payload}


@app.get("/volumes")
def list_volumes(_: None = Depends(require_auth)):
    return {"default": VOLUMES.default_name, "volumes": VOLUMES.list_volumes()}


@app.post("/volumes")
def add_volume(body: dict, _: None = Depends(require_auth)):
    name = str(body.get("name") or "").strip()
    path = str(body.get("path") or "").strip()
    if not name or not path:
        raise HTTPException(400, "name and path required")
    VOLUMES.add_volume(name, path, make_default=bool(body.get("make_default")))
    return {"ok": True, "default": VOLUMES.default_name, "volumes": VOLUMES.list_volumes()}


@app.get("/ros")
def list_ros(
    q: str = "",
    make: str = "",
    model: str = "",
    year: str = "",
    name: str = "",
    vin: str = "",
    status: str = "",
    plate: str = "",
    _: None = Depends(require_auth),
):
    with _db() as conn:
        rows = conn.execute(
            "SELECT data FROM repair_orders ORDER BY updated DESC"
        ).fetchall()
    orders = [json.loads(r["data"]) for r in rows]
    return _filter_ros(
        orders,
        q=q,
        make=make,
        model=model,
        year=year,
        name=name,
        vin=vin,
        status=status,
        plate=plate,
    )


def _filter_ros(
    orders: list[dict],
    *,
    q: str = "",
    make: str = "",
    model: str = "",
    year: str = "",
    name: str = "",
    vin: str = "",
    status: str = "",
    plate: str = "",
) -> list[dict]:
    q = q.strip().lower()
    make, model, year = make.lower(), model.lower(), year.lower()
    name, vin, status, plate = name.lower(), vin.lower(), status.lower(), plate.lower()
    hits = []
    for o in orders:
        blob = " ".join(
            str(o.get(k) or "")
            for k in (
                "id",
                "first_name",
                "last_name",
                "year",
                "make",
                "model",
                "vin",
                "plate",
                "phone",
                "status",
                "complaint",
                "tech_notes",
            )
        ).lower()
        if q and q not in blob:
            continue
        if make and make not in str(o.get("make") or "").lower():
            continue
        if model and model not in str(o.get("model") or "").lower():
            continue
        if year and year not in str(o.get("year") or "").lower():
            continue
        if vin and vin not in str(o.get("vin") or "").lower():
            continue
        if plate and plate not in str(o.get("plate") or "").lower():
            continue
        if status and status != str(o.get("status") or "").lower():
            continue
        if name:
            cust = f"{o.get('first_name', '')} {o.get('last_name', '')}".lower()
            if name not in cust:
                continue
        hits.append(o)
    return hits


@app.get("/ros/{ro_id}")
def get_ro(ro_id: str, _: None = Depends(require_auth)):
    with _db() as conn:
        row = conn.execute(
            "SELECT data FROM repair_orders WHERE id = ?", (ro_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "RO not found")
    return json.loads(row["data"])


@app.put("/ros/{ro_id}")
def put_ro(ro_id: str, body: dict, _: None = Depends(require_auth)):
    body = dict(body)
    body["id"] = ro_id
    updated = str(body.get("updated") or "")
    payload = json.dumps(body)
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO repair_orders (id, data, updated)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated = excluded.updated
            """,
            (ro_id, payload, updated or body.get("created") or ""),
        )
    return body


@app.post("/ros/{ro_id}/photos")
async def upload_photo(
    ro_id: str,
    file: UploadFile = File(...),
    tag: str = Form("other"),
    notes: str = Form(""),
    volume: str | None = Form(None),
    _: None = Depends(require_auth),
):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    try:
        return _save_photo_bytes(
            ro_id,
            file.filename or "photo.bin",
            data,
            tag or "other",
            volume,
            notes=notes or "",
        )
    except KeyError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/ros/{ro_id}/photos/{photo_relpath}")
def download_photo(
    ro_id: str,
    photo_relpath: str,
    volume: str | None = None,
    _: None = Depends(require_auth),
):
    vol = volume or VOLUMES.default_name
    path = VOLUMES.photos_dir(ro_id, vol) / Path(photo_relpath).name
    if not path.is_file():
        # search other volumes
        for name in VOLUMES.list_volumes():
            alt = VOLUMES.photos_dir(ro_id, name) / Path(photo_relpath).name
            if alt.is_file():
                path = alt
                break
    if not path.is_file():
        raise HTTPException(404, "Photo not found")
    return FileResponse(path)


def _save_photo_bytes(
    ro_id: str,
    filename: str,
    data: bytes,
    tag: str,
    volume: str | None = None,
    notes: str = "",
) -> dict:
    vol = volume or VOLUMES.default_name
    dest_dir = VOLUMES.photos_dir(ro_id, vol)
    photo_id = uuid.uuid4().hex[:12]
    safe_name = Path(filename or "photo.bin").name
    dest_name = f"{photo_id}_{safe_name}"
    dest = dest_dir / dest_name
    dest.write_bytes(data)
    meta = {
        "id": photo_id,
        "filename": safe_name,
        "tag": tag,
        "notes": (notes or "").strip(),
        "volume": vol,
        "relpath": dest_name,
    }
    with _db() as conn:
        row = conn.execute(
            "SELECT data FROM repair_orders WHERE id = ?", (ro_id,)
        ).fetchone()
        if row:
            order = json.loads(row["data"])
            photos = list(order.get("photos") or [])
            photos.append(meta)
            order["photos"] = photos
            conn.execute(
                "UPDATE repair_orders SET data = ? WHERE id = ?",
                (json.dumps(order), ro_id),
            )
        else:
            # Create a stub RO so phone uploads are not lost
            stub = {
                "id": ro_id,
                "photos": [meta],
                "status": "open",
                "updated": "",
                "created": "",
            }
            conn.execute(
                "INSERT INTO repair_orders (id, data, updated) VALUES (?, ?, ?)",
                (ro_id, json.dumps(stub), ""),
            )
    return meta


@app.post("/upload-sessions")
def create_upload_session(body: dict, _: None = Depends(require_auth)):
    ro_id = str(body.get("ro_id") or "").strip()
    if not ro_id:
        raise HTTPException(400, "ro_id required")
    tag = str(body.get("tag") or "intake").strip() or "intake"
    kind = str(body.get("kind") or "web").strip() or "web"
    default_ttl = 7 * 24 * 3600 if kind == "shortcut" else 3600
    ttl = int(body.get("ttl_sec") or default_ttl)
    sess = UPLOADS.create(ro_id, tag=tag, ttl_sec=ttl, kind=kind)
    return {
        "token": sess.token,
        "ro_id": sess.ro_id,
        "tag": sess.tag,
        "kind": sess.kind,
        "expires": sess.expires,
        "path": f"/u/{sess.token}",
        "shortcut_path": f"/u/{sess.token}/shortcut",
    }


@app.get("/u/{token}", response_class=HTMLResponse)
def upload_page(token: str):
    import time as _time

    sess = UPLOADS.get(token)
    if not sess:
        raise HTTPException(410, "Upload link expired or invalid")
    ttl_min = max(1, int((sess.expires - _time.time()) / 60))
    html = (
        UPLOAD_PAGE.replace("__RO_ID__", sess.ro_id)
        .replace("__TAG__", sess.tag)
        .replace("__TTL__", str(ttl_min))
        .replace("__TOKEN__", token)
    )
    return HTMLResponse(html)


@app.get("/u/{token}/shortcut", response_class=HTMLResponse)
def shortcut_help(token: str, request: Request):
    import time as _time

    sess = UPLOADS.get(token)
    if not sess:
        raise HTTPException(410, "Upload link expired or invalid")
    upload_url = str(request.base_url).rstrip("/") + f"/u/{token}"
    ttl_label = _ttl_label(sess.expires - _time.time())
    html = (
        SHORTCUT_PAGE.replace("__RO_ID__", sess.ro_id)
        .replace("__TAG__", sess.tag)
        .replace("__TTL__", ttl_label)
        .replace("__TOKEN__", token)
        .replace("__UPLOAD_URL__", upload_url)
    )
    return HTMLResponse(html)


def _ttl_label(seconds: float) -> str:
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {mins}m"
    return f"{max(1, mins)} min"


@app.post("/u/{token}")
async def upload_via_token(
    token: str,
    file: UploadFile = File(...),
    tag: str = Form(""),
    notes: str = Form(""),
):
    sess = UPLOADS.get(token)
    if not sess:
        raise HTTPException(410, "Upload link expired or invalid")
    use_tag = (tag or sess.tag or "intake").strip()
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    meta = _save_photo_bytes(
        sess.ro_id,
        file.filename or "photo.jpg",
        data,
        use_tag,
        notes=notes or "",
    )
    UPLOADS.bump(token)
    return {"ok": True, "photo": meta, "uploads": UPLOADS.get(token).uploads if UPLOADS.get(token) else 0}


@app.get("/u/{token}/status")
def upload_status(token: str):
    sess = UPLOADS.get(token)
    if not sess:
        raise HTTPException(410, "Upload link expired or invalid")
    return {
        "ro_id": sess.ro_id,
        "tag": sess.tag,
        "uploads": sess.uploads,
        "expires": sess.expires,
    }
