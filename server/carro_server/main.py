"""carro-server: remote repair-order + multi-volume photo storage."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from carro_server.volumes import VolumeManager

TOKEN = os.environ.get("CARRO_TOKEN", "").strip()
VOLUMES = VolumeManager()


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
def list_ros(_: None = Depends(require_auth)):
    with _db() as conn:
        rows = conn.execute(
            "SELECT data FROM repair_orders ORDER BY updated DESC"
        ).fetchall()
    return [json.loads(r["data"]) for r in rows]


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
    volume: str | None = Form(None),
    _: None = Depends(require_auth),
):
    vol = volume or VOLUMES.default_name
    try:
        dest_dir = VOLUMES.photos_dir(ro_id, vol)
    except KeyError as exc:
        raise HTTPException(400, str(exc)) from exc
    photo_id = uuid.uuid4().hex[:12]
    safe_name = Path(file.filename or "photo.bin").name
    dest_name = f"{photo_id}_{safe_name}"
    dest = dest_dir / dest_name
    data = await file.read()
    dest.write_bytes(data)

    # Merge into RO record if present
    meta = {
        "id": photo_id,
        "filename": safe_name,
        "tag": tag,
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
    return meta


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
