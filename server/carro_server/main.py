"""carro-server: remote repair-order + multi-volume photo storage."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import uuid
from pathlib import Path

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from carro_server.events import append_event, diff_ro_events, ensure_events_table, list_events
from carro_server.ro_merge import merge_repair_order
from carro_server.version import APP_VERSION, version_payload
from carro_server.indexes import (
    backfill_projections,
    delete_ro_projections,
    distinct_part_suggestions,
    ensure_index_tables,
    load_ros_by_ids,
    maybe_backfill_if_empty,
    parts_usage_by_month,
    search_parts,
    search_ro_ids,
    sync_ro_projections,
)
from carro_server.messages import (
    ensure_messages_table,
    list_inbox,
    list_sent,
    mark_delivered,
    mark_read,
    renotify,
    send_message,
    unread_count,
)
from carro_server.shifts import (
    delete_shift,
    end_shift,
    ensure_shifts_table,
    get_open_shift,
    get_shift,
    list_active,
    list_shifts,
    start_shift,
    update_shift,
)
from carro_server import advisor_presence as adv_presence
from carro_server.weekly_reports import (
    ensure_weekly_reports_table,
    get_report as get_weekly_report,
    list_reports as list_weekly_reports,
    upsert_report as upsert_weekly_report,
)
from carro_server.pin import verify_pin
from carro_server.sessions import (
    COOKIE_NAME,
    Principal,
    clear_failures,
    create_session,
    get_session,
    login_allowed,
    record_failure,
    revoke_session,
)
from carro_server import push as webpush
from carro_server.upload_tokens import SHORTCUT_PAGE, UPLOAD_PAGE, UploadTokenStore
from carro_server.volumes import VolumeManager

TOKEN = os.environ.get("CARRO_TOKEN", "").strip()
VOLUMES = VolumeManager()
UPLOADS = UploadTokenStore(VOLUMES.root / "upload_sessions.json")
SESSIONS_PATH = VOLUMES.root / "app_sessions.json"


def _db() -> sqlite3.Connection:
    """Open shop DB and apply additive schema ensures (CREATE IF NOT EXISTS / ADD COLUMN).

    Migrations must stay non-destructive in-place. Destructive changes need a major
    VERSION bump and an explicit backup step in docs/UPDATING.md.
    """
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
    ensure_events_table(conn)
    ensure_index_tables(conn)
    ensure_messages_table(conn)
    ensure_shifts_table(conn)
    adv_presence.ensure_advisor_presence_table(conn)
    ensure_weekly_reports_table(conn)
    maybe_backfill_if_empty(conn)
    return conn


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        return ""
    return authorization.removeprefix("Bearer ").strip()


def principal_from(
    authorization: str | None = None,
    session_cookie: str | None = None,
) -> Principal:
    """Shop token (bay PCs) or PIN session (phone PWA). Open lab if CARRO_TOKEN unset."""
    if not TOKEN:
        return Principal(kind="shop", name="shop")
    raw = _bearer(authorization) or (session_cookie or "").strip()
    if not raw:
        raise HTTPException(401, "Missing bearer token")
    if TOKEN and len(raw) == len(TOKEN) and secrets.compare_digest(raw, TOKEN):
        return Principal(kind="shop", name="shop", token=raw)
    sess = get_session(SESSIONS_PATH, raw)
    if sess:
        return sess
    raise HTTPException(403, "Invalid token")


def require_auth(
    authorization: str | None = Header(default=None),
    carro_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> Principal:
    return principal_from(authorization, carro_session)


def require_shop(principal: Principal = Depends(require_auth)) -> Principal:
    if principal.kind != "shop":
        raise HTTPException(403, "Shop token required")
    return principal


app = FastAPI(title="carro-server", version=APP_VERSION)


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


def _pwa_dir() -> Path | None:
    here = Path(__file__).resolve()
    for candidate in (
        here.parents[1] / "pwa",  # ~/carro-server/pwa
        here.parents[2] / "mobile" / "dist",  # monorepo checkout
    ):
        if (candidate / "index.html").is_file():
            return candidate
    return None


@app.get("/health")
def health():
    """Liveness + volume summary (no auth — used by install checks / monitoring)."""
    vols = VOLUMES.volume_stats()
    pwa = _pwa_dir()
    return {
        "ok": True,
        "default_volume": VOLUMES.default_name,
        "meta_dir": str(VOLUMES.root),
        "volumes": vols,
        "pwa": bool(pwa),
        **version_payload(),
    }


@app.get("/version")
def version_info():
    """Release identity (no auth)."""
    return {"ok": True, **version_payload()}


def _public_people() -> list[dict]:
    people: list[dict] = []
    for t in _load_technicians().get("technicians") or []:
        if not isinstance(t, dict):
            continue
        pid = str(t.get("id") or "").strip()
        name = str(t.get("name") or "").strip()
        if pid and name:
            people.append({"id": pid, "name": name, "role": "technician"})
    for a in _load_advisors().get("advisors") or []:
        if not isinstance(a, dict):
            continue
        pid = str(a.get("id") or "").strip()
        name = str(a.get("name") or "").strip()
        if pid and name:
            people.append(
                {
                    "id": pid,
                    "name": name,
                    "role": "advisor",
                    "working_privilege": bool(a.get("working_privilege")),
                }
            )
    people.sort(key=lambda p: (p["role"], p["name"].lower()))
    return people


def _pin_hash_for(person: dict) -> str:
    pid = person.get("id") or ""
    role = person.get("role")
    if role == "technician":
        for t in _load_technicians().get("technicians") or []:
            if isinstance(t, dict) and str(t.get("id") or "") == pid:
                return str(t.get("pin_hash") or "")
    if role == "advisor":
        for a in _load_advisors().get("advisors") or []:
            if isinstance(a, dict) and str(a.get("id") or "") == pid:
                return str(a.get("pin_hash") or "")
    return ""


@app.get("/people")
def list_people():
    """Names + ids for the phone login picker. No PIN hashes."""
    people = _public_people()
    return {"people": people, "empty": not people}


def _set_session_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=14 * 24 * 3600,
        path="/",
        secure=request.url.scheme == "https",
    )


@app.post("/session/login")
def session_login(body: dict, request: Request, response: Response):
    """PIN login for the phone PWA. Does not use the shop API token."""
    if not isinstance(body, dict):
        raise HTTPException(400, "JSON object required")
    pin = str(body.get("pin") or "").strip()
    person_id = str(body.get("id") or "").strip()
    fail_key = f"{request.client.host if request.client else '?'}:{person_id or pin[:1]}"
    if not login_allowed(fail_key):
        raise HTTPException(429, "Too many PIN attempts — wait a few minutes")
    people = _public_people()
    if not people:
        raise HTTPException(
            400,
            "No staff on the shop server yet — sync a bay PC first",
        )
    try:
        candidates = [p for p in people if not person_id or p["id"] == person_id]
        matched: dict | None = None
        for person in candidates:
            if verify_pin(pin, _pin_hash_for(person)):
                matched = person
                break
        if not matched:
            record_failure(fail_key)
            raise HTTPException(401, "Incorrect PIN")
    except ValueError:
        record_failure(fail_key)
        raise HTTPException(401, "Incorrect PIN") from None
    clear_failures(fail_key)
    token, _row = create_session(
        SESSIONS_PATH,
        kind=str(matched["role"]),
        person_id=str(matched["id"]),
        name=str(matched["name"]),
    )
    _set_session_cookie(request, response, token)
    principal = Principal(
        kind=str(matched["role"]),
        id=str(matched["id"]),
        name=str(matched["name"]),
        token=token,
    )
    out = principal.to_public()
    out["token"] = token
    return out


@app.get("/session")
def session_whoami(principal: Principal = Depends(require_auth)):
    if principal.kind == "shop":
        return {"ok": True, "kind": "shop", "role": "shop", "id": "", "name": "shop"}
    return principal.to_public()


@app.post("/session/logout")
def session_logout(
    response: Response,
    authorization: str | None = Header(default=None),
    carro_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
):
    raw = _bearer(authorization) or (carro_session or "").strip()
    if raw and not (TOKEN and len(raw) == len(TOKEN) and secrets.compare_digest(raw, TOKEN)):
        revoke_session(SESSIONS_PATH, raw)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/push/vapid")
def push_vapid(principal: Principal = Depends(require_auth)):
    keys = webpush.load_or_create_vapid(VOLUMES.root)
    return {
        "ok": True,
        "public_key": keys["public_key"],
        "subscribed": bool(principal.id)
        and webpush.has_subscription(VOLUMES.root, principal.id),
    }


@app.post("/push/subscribe")
def push_subscribe(body: dict, principal: Principal = Depends(require_auth)):
    if principal.kind not in ("technician", "advisor") or not principal.id:
        raise HTTPException(403, "Sign in with a staff PIN to enable notifications")
    if not isinstance(body, dict):
        raise HTTPException(400, "JSON object required")
    keys = body.get("keys") if isinstance(body.get("keys"), dict) else {}
    try:
        row = webpush.upsert_subscription(
            VOLUMES.root,
            person_id=principal.id,
            person_name=principal.name,
            role=principal.kind,
            endpoint=str(body.get("endpoint") or ""),
            keys={
                "p256dh": str(keys.get("p256dh") or ""),
                "auth": str(keys.get("auth") or ""),
            },
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "endpoint": row["endpoint"]}


@app.post("/push/unsubscribe")
def push_unsubscribe(body: dict | None = None, principal: Principal = Depends(require_auth)):
    if principal.kind not in ("technician", "advisor") or not principal.id:
        raise HTTPException(403, "Staff session required")
    body = body if isinstance(body, dict) else {}
    removed = webpush.remove_subscription(
        VOLUMES.root,
        person_id=principal.id,
        endpoint=str(body.get("endpoint") or ""),
    )
    return {"ok": True, "removed": removed}


@app.get("/technicians")
def get_technicians(_: Principal = Depends(require_shop)):
    return _load_technicians()


@app.put("/technicians")
def put_technicians(body: dict, _: Principal = Depends(require_shop)):
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


def _advisors_path() -> Path:
    return VOLUMES.root / "advisors.json"


def _load_advisors() -> dict:
    path = _advisors_path()
    if not path.is_file():
        return {"version": 1, "updated": "", "advisors": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "updated": "", "advisors": []}
    if not isinstance(raw, dict):
        return {"version": 1, "updated": "", "advisors": []}
    advisors = raw.get("advisors")
    if not isinstance(advisors, list):
        advisors = []
    return {
        "version": 1,
        "updated": str(raw.get("updated") or ""),
        "advisors": [a for a in advisors if isinstance(a, dict)],
    }


@app.get("/advisors")
def get_advisors(_: Principal = Depends(require_shop)):
    return _load_advisors()


@app.put("/advisors")
def put_advisors(body: dict, _: Principal = Depends(require_shop)):
    if not isinstance(body, dict):
        raise HTTPException(400, "JSON object required")
    advisors = body.get("advisors")
    if advisors is not None and not isinstance(advisors, list):
        raise HTTPException(400, "advisors must be a list")
    payload = {
        "version": 1,
        "updated": str(body.get("updated") or ""),
        "advisors": [a for a in (advisors or []) if isinstance(a, dict)],
    }
    if not payload["updated"]:
        from datetime import datetime

        payload["updated"] = datetime.now().isoformat(timespec="seconds")
    path = _advisors_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, **payload}


@app.post("/advisors/presence")
def post_advisor_presence(body: dict, _: None = Depends(require_auth)):
    if not isinstance(body, dict):
        raise HTTPException(400, "JSON object required")
    aid = str(body.get("advisor_id") or "").strip()
    if not aid:
        raise HTTPException(400, "advisor_id required")
    with _db() as conn:
        try:
            row = adv_presence.heartbeat(
                conn,
                advisor_id=aid,
                name=str(body.get("name") or ""),
                client_host=str(body.get("client_host") or ""),
            )
            conn.commit()
            return {"ok": True, **row}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@app.get("/advisors/presence")
def get_advisor_presence(
    within_seconds: int = 90, _: None = Depends(require_auth)
):
    with _db() as conn:
        rows = adv_presence.list_online(conn, within_seconds=within_seconds)
        return {"advisors": rows, "count": len(rows)}


@app.delete("/advisors/presence/{advisor_id}")
def delete_advisor_presence(advisor_id: str, _: None = Depends(require_auth)):
    with _db() as conn:
        adv_presence.clear_presence(conn, advisor_id)
        conn.commit()
        return {"ok": True}


def _suppliers_path() -> Path:
    return VOLUMES.root / "suppliers.json"


def _load_suppliers() -> dict:
    path = _suppliers_path()
    if not path.is_file():
        return {"version": 1, "updated": "", "suppliers": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "updated": "", "suppliers": []}
    if not isinstance(raw, dict):
        return {"version": 1, "updated": "", "suppliers": []}
    suppliers = raw.get("suppliers")
    if not isinstance(suppliers, list):
        suppliers = []
    return {
        "version": 1,
        "updated": str(raw.get("updated") or ""),
        "suppliers": [s for s in suppliers if isinstance(s, dict)],
    }


@app.get("/suppliers")
def get_suppliers(_: None = Depends(require_auth)):
    return _load_suppliers()


@app.put("/suppliers")
def put_suppliers(body: dict, _: Principal = Depends(require_shop)):
    if not isinstance(body, dict):
        raise HTTPException(400, "JSON object required")
    suppliers = body.get("suppliers")
    if suppliers is not None and not isinstance(suppliers, list):
        raise HTTPException(400, "suppliers must be a list")
    payload = {
        "version": 1,
        "updated": str(body.get("updated") or ""),
        "suppliers": [s for s in (suppliers or []) if isinstance(s, dict)],
    }
    if not payload["updated"]:
        from datetime import datetime

        payload["updated"] = datetime.now().isoformat(timespec="seconds")
    path = _suppliers_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, **payload}


def _bug_reports_path() -> Path:
    return VOLUMES.root / "bug_reports.jsonl"


def _append_bug_report(report: dict) -> dict:
    path = _bug_reports_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Store without nested sync bookkeeping from bays
    row = {k: v for k, v in report.items() if k not in ("sync_status",)}
    row["received_at"] = row.get("received_at") or row.get("created_at") or ""
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _list_bug_reports(*, limit: int = 50) -> list[dict]:
    path = _bug_reports_path()
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict):
            rows.append(raw)
    rows.reverse()
    lim = max(1, min(int(limit or 50), 500))
    return rows[:lim]


@app.post("/bug-reports")
def post_bug_report(body: dict, _: None = Depends(require_auth)):
    if not isinstance(body, dict):
        raise HTTPException(400, "JSON object required")
    title = str(body.get("title") or "").strip()
    description = str(body.get("description") or "").strip()
    if not title or not description:
        raise HTTPException(400, "title and description required")
    saved = _append_bug_report(body)
    return {"ok": True, "report": saved}


@app.get("/bug-reports")
def get_bug_reports(limit: int = 50, _: None = Depends(require_auth)):
    rows = _list_bug_reports(limit=limit)
    return {"reports": rows, "count": len(rows)}


@app.get("/volumes")
def list_volumes(_: None = Depends(require_auth)):
    return {
        "default": VOLUMES.default_name,
        "meta_dir": str(VOLUMES.root),
        "db_path": str(VOLUMES.db_path()),
        "volumes": VOLUMES.volume_stats(),
    }


@app.post("/volumes")
def add_volume(body: dict, _: Principal = Depends(require_shop)):
    """
    Register another drive for photo storage on a live server.

    Body: {"name": "extra", "path": "/mnt/extra/carro", "make_default": false}
    make_default=true sends *new* photo uploads to this volume (DB stays put).
    """
    name = str(body.get("name") or "").strip()
    path = str(body.get("path") or "").strip()
    if not name or not path:
        raise HTTPException(400, "name and path required")
    try:
        VOLUMES.add_volume(name, path, make_default=bool(body.get("make_default")))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "ok": True,
        "default": VOLUMES.default_name,
        "meta_dir": str(VOLUMES.root),
        "db_path": str(VOLUMES.db_path()),
        "volumes": VOLUMES.volume_stats(),
    }


@app.put("/volumes/{name}/default")
def set_default_volume(name: str, _: Principal = Depends(require_shop)):
    """Point new photo uploads at an existing volume. Does not move the database."""
    try:
        VOLUMES.set_default(name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        "ok": True,
        "default": VOLUMES.default_name,
        "volumes": VOLUMES.volume_stats(),
    }


@app.post("/volumes/reload")
def reload_volumes(_: Principal = Depends(require_shop)):
    """Re-read volumes.json after a manual edit (no full service restart required)."""
    VOLUMES.reload()
    return {
        "ok": True,
        "default": VOLUMES.default_name,
        "volumes": VOLUMES.volume_stats(),
    }


def _new_ro_id(existing: list[str], when: datetime | None = None) -> str:
    when = when or datetime.now()
    day = when.strftime("%Y%m%d")
    prefix = f"RO-{day}-"
    seq = 1
    for eid in existing:
        if eid.startswith(prefix):
            try:
                seq = max(seq, int(eid.rsplit("-", 1)[-1]) + 1)
            except ValueError:
                pass
    return f"{prefix}{seq:03d}"


@app.post("/ros")
def create_ro(body: dict | None = None, principal: Principal = Depends(require_auth)):
    """Create a repair order on the shop server (phone PWA / advisor away from a bay)."""
    body = dict(body or {})
    now = datetime.now().isoformat(timespec="seconds")
    with _db() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM repair_orders").fetchall()]
    ro_id = str(body.get("id") or "").strip() or _new_ro_id(ids)
    if ro_id in ids:
        raise HTTPException(409, f"RO already exists: {ro_id}")
    actor = principal.name if principal.kind != "shop" else str(body.get("_actor") or "")
    actor_id = principal.id if principal.kind != "shop" else str(body.get("_actor_id") or "")
    order = {
        "id": ro_id,
        "first_name": str(body.get("first_name") or ""),
        "last_name": str(body.get("last_name") or ""),
        "phone": str(body.get("phone") or ""),
        "year": str(body.get("year") or ""),
        "make": str(body.get("make") or ""),
        "model": str(body.get("model") or ""),
        "vin": str(body.get("vin") or ""),
        "mileage": str(body.get("mileage") or ""),
        "plate": str(body.get("plate") or ""),
        "complaint": str(body.get("complaint") or ""),
        "tech_notes": str(body.get("tech_notes") or ""),
        "status": str(body.get("status") or "open"),
        "photos": [],
        "work_items": [],
        "found_issues": [],
        "advisor_actions": [],
        "created": now,
        "updated": now,
        "technician_id": actor_id if principal.kind == "technician" else "",
        "technician_name": actor if principal.kind == "technician" else "",
    }
    concern = str(body.get("complaint") or "").strip()
    if concern:
        order["work_items"] = [
            {
                "id": "wi-1",
                "kind": "diag",
                "concern": concern,
                "notes": str(body.get("tech_notes") or ""),
                "status": "open",
                "created_by": actor,
                "created_by_id": actor_id,
                "created_by_role": principal.kind if principal.kind != "shop" else "",
            }
        ]
    return put_ro(ro_id, {**order, "_actor": actor, "_actor_id": actor_id}, principal)


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
    limit: int = 500,
    _: None = Depends(require_auth),
):
    with _db() as conn:
        has_filter = any(
            str(x or "").strip()
            for x in (q, make, model, year, name, vin, status, plate)
        )
        if has_filter:
            ids = search_ro_ids(
                conn,
                q=q,
                make=make,
                model=model,
                year=year,
                name=name,
                vin=vin,
                status=status,
                plate=plate,
                limit=limit,
            )
            return load_ros_by_ids(conn, ids)
        # Unfiltered: newest via index, then load blobs
        ensure_index_tables(conn)
        maybe_backfill_if_empty(conn)
        cap = max(1, min(int(limit), 2000))
        ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM ro_index ORDER BY updated DESC LIMIT ?", (cap,)
            ).fetchall()
        ]
        if not ids:
            rows = conn.execute(
                "SELECT data FROM repair_orders ORDER BY updated DESC LIMIT ?",
                (cap,),
            ).fetchall()
            return [json.loads(r["data"]) for r in rows]
        return load_ros_by_ids(conn, ids)


@app.get("/parts")
def list_parts(
    part_number: str = "",
    manufacturer: str = "",
    status: str = "",
    ro_id: str = "",
    q: str = "",
    include_received: bool = False,
    limit: int = 500,
    _: None = Depends(require_auth),
):
    with _db() as conn:
        rows = search_parts(
            conn,
            part_number=part_number,
            manufacturer=manufacturer,
            status=status,
            ro_id=ro_id,
            q=q,
            include_received=include_received,
            limit=limit,
        )
    return {"parts": rows, "count": len(rows), "source": "server"}


@app.get("/parts/usage")
def parts_usage(
    year: int | None = None,
    month: int | None = None,
    limit: int = 100,
    _: None = Depends(require_auth),
):
    now = datetime.now(tz=timezone.utc)
    y = int(year or now.year)
    m = int(month or now.month)
    with _db() as conn:
        try:
            rows = parts_usage_by_month(conn, year=y, month=m, limit=limit)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    return {"usage": rows, "count": len(rows), "year": y, "month": m}


@app.get("/parts/suggest")
def parts_suggest(q: str = "", limit: int = 25, _: None = Depends(require_auth)):
    with _db() as conn:
        rows = distinct_part_suggestions(conn, q=q, limit=limit)
    return {"suggestions": rows, "count": len(rows)}


@app.post("/admin/reindex")
def admin_reindex(_: Principal = Depends(require_shop)):
    with _db() as conn:
        stats = backfill_projections(conn)
        conn.commit()
    return {"ok": True, **stats}


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
def put_ro(ro_id: str, body: dict, principal: Principal = Depends(require_auth)):
    body = dict(body)
    body["id"] = ro_id
    actor = str(
        body.get("_actor")
        or body.get("updated_by")
        or (principal.name if principal.kind != "shop" else "")
    )
    actor_id = str(
        body.get("_actor_id")
        or (principal.id if principal.kind != "shop" else "")
    )
    base_updated = str(body.get("_base_updated") or "")
    strip_keys = {"_actor", "_actor_id", "_base_updated"}
    incoming = {k: v for k, v in body.items() if k not in strip_keys}
    with _db() as conn:
        prev_row = conn.execute(
            "SELECT data FROM repair_orders WHERE id = ?", (ro_id,)
        ).fetchone()
        before = json.loads(prev_row["data"]) if prev_row else None
        merged = merge_repair_order(
            server=before,
            incoming=incoming,
            base_updated=base_updated,
            actor=actor,
        )
        merged["id"] = ro_id
        updated = str(merged.get("updated") or incoming.get("updated") or "")
        payload = json.dumps(merged)
        conn.execute(
            """
            INSERT INTO repair_orders (id, data, updated)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated = excluded.updated
            """,
            (ro_id, payload, updated or merged.get("created") or ""),
        )
        sync_ro_projections(conn, merged)
        for ev in diff_ro_events(before, merged, actor=actor):
            ev_payload = dict(ev.get("payload") or {})
            if actor_id:
                ev_payload.setdefault("actor_id", actor_id)
            append_event(
                conn,
                type=ev["type"],
                ro_id=ev["ro_id"],
                item_id=ev.get("item_id") or "",
                actor=ev.get("actor") or "",
                summary=ev.get("summary") or "",
                at=ev.get("at"),
                payload=ev_payload or None,
            )
    return merged


@app.get("/advisor/recent")
def advisor_recent(
    minutes: int = Query(default=120, ge=1, le=60 * 24 * 14),
    _: None = Depends(require_auth),
):
    """ROs updated in the last N minutes — for a future separate advisor app."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=minutes)
    # Compare as ISO-ish strings; also accept naive local stamps from clients
    cutoff_s = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
    with _db() as conn:
        rows = conn.execute(
            "SELECT data, updated FROM repair_orders ORDER BY updated DESC"
        ).fetchall()
    orders = []
    for r in rows:
        updated = str(r["updated"] or "")
        if updated < cutoff_s:
            # still include if nested work_items updated field is newer — trust RO updated
            continue
        try:
            orders.append(json.loads(r["data"]))
        except json.JSONDecodeError:
            continue
    return {"minutes": minutes, "count": len(orders), "orders": orders}


@app.get("/assigned")
def assigned_board(
    tech_id: str = "",
    tech_name: str = "",
    _: None = Depends(require_auth),
):
    """Assigned Work board for tech app (and future advisor assignment UI)."""
    from carro_server.assignment import build_assigned_board

    with _db() as conn:
        rows = conn.execute(
            "SELECT data FROM repair_orders ORDER BY updated DESC"
        ).fetchall()
    orders: list[dict] = []
    for r in rows:
        try:
            orders.append(json.loads(r["data"]))
        except json.JSONDecodeError:
            continue
    board = build_assigned_board(orders, tech_id=tech_id, tech_name=tech_name)
    board["source"] = "server"
    return board


@app.get("/events")
def get_events(
    since: str = "",
    since_id: int = 0,
    ro_id: str = "",
    limit: int = 100,
    exclude_actor: str = "",
    exclude_actor_id: str = "",
    _: None = Depends(require_auth),
):
    with _db() as conn:
        events = list_events(
            conn,
            since=since,
            since_id=since_id,
            ro_id=ro_id,
            limit=limit,
            exclude_actor=exclude_actor,
            exclude_actor_id=exclude_actor_id,
        )
    return {"events": events}


@app.get("/events/stream")
async def events_stream(
    request: Request,
    since_id: int = 0,
    exclude_actor: str = "",
    exclude_actor_id: str = "",
    authorization: str | None = Header(default=None),
):
    """SSE stream of new RO events (poll-backed). Skips the caller's own events."""
    principal_from(authorization, request.cookies.get(COOKIE_NAME))
    last_id = int(since_id or 0)

    async def gen():
        nonlocal last_id
        yield "event: hello\ndata: {}\n\n"
        while True:
            if await request.is_disconnected():
                break
            with _db() as conn:
                batch = list_events(
                    conn,
                    since_id=last_id,
                    limit=50,
                    exclude_actor=exclude_actor,
                    exclude_actor_id=exclude_actor_id,
                )
            for ev in batch:
                last_id = max(last_id, int(ev["id"]))
                yield f"event: ro\ndata: {json.dumps(ev)}\n\n"
            await asyncio.sleep(2.0)

    return StreamingResponse(gen(), media_type="text/event-stream")


def _resolve_roster_person(person_id: str, role: str) -> tuple[str, str, str]:
    """Return (id, name, role) if person exists on the shop roster."""
    pid = (person_id or "").strip()
    role = (role or "").strip().lower()
    if not pid:
        raise HTTPException(400, "Person id required")
    if role == "technician":
        for t in _load_technicians().get("technicians") or []:
            if str(t.get("id") or "") == pid:
                return pid, str(t.get("name") or pid), "technician"
        raise HTTPException(404, f"Technician not found: {pid}")
    if role == "advisor":
        for a in _load_advisors().get("advisors") or []:
            if str(a.get("id") or "") == pid:
                return pid, str(a.get("name") or pid), "advisor"
        raise HTTPException(404, f"Advisor not found: {pid}")
    raise HTTPException(400, "role must be technician or advisor")


@app.get("/messages")
def get_messages(
    for_id: str = "",
    unread: int = 0,
    limit: int = 100,
    _: None = Depends(require_auth),
):
    """Inbox for a specific person (to_id)."""
    if not (for_id or "").strip():
        raise HTTPException(400, "for_id required")
    with _db() as conn:
        messages = list_inbox(
            conn,
            for_id=for_id,
            unread_only=bool(unread),
            limit=limit,
        )
        count = unread_count(conn, for_id=for_id)
    return {"messages": messages, "unread": count}


@app.get("/messages/sent")
def get_sent_messages(
    from_id: str = "",
    limit: int = 100,
    _: None = Depends(require_auth),
):
    if not (from_id or "").strip():
        raise HTTPException(400, "from_id required")
    with _db() as conn:
        messages = list_sent(conn, from_id=from_id, limit=limit)
    return {"messages": messages}


@app.post("/messages")
def post_message(body: dict, _: None = Depends(require_auth)):
    """
    Person-to-person shop note.
    Body: body, from_id, from_name, from_role, to_id, to_role,
          optional to_name, ro_id, work_item_id, reply_to.
    """
    if not isinstance(body, dict):
        raise HTTPException(400, "JSON object required")
    from_id = str(body.get("from_id") or "").strip()
    from_role = str(body.get("from_role") or "").strip().lower()
    to_id = str(body.get("to_id") or "").strip()
    to_role = str(body.get("to_role") or "").strip().lower()
    # Validate recipient against live roster; fill name if omitted
    to_id, to_name, to_role = _resolve_roster_person(to_id, to_role)
    if body.get("to_name"):
        to_name = str(body.get("to_name") or to_name).strip() or to_name
    from_name = str(body.get("from_name") or "").strip() or from_id
    # Soft-check sender exists (don't block if roster lag on another bay)
    try:
        from_id, resolved_from_name, from_role = _resolve_roster_person(from_id, from_role)
        if not str(body.get("from_name") or "").strip():
            from_name = resolved_from_name
    except HTTPException:
        if from_role not in ("technician", "advisor") or not from_id:
            raise
    reply_raw = body.get("reply_to")
    reply_to = None
    if reply_raw is not None and str(reply_raw).strip() != "":
        try:
            reply_to = int(reply_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "reply_to must be an integer") from exc

    with _db() as conn:
        try:
            msg = send_message(
                conn,
                body=str(body.get("body") or ""),
                from_id=from_id,
                from_name=from_name,
                from_role=from_role,
                to_id=to_id,
                to_name=to_name,
                to_role=to_role,
                ro_id=str(body.get("ro_id") or ""),
                work_item_id=str(body.get("work_item_id") or ""),
                reply_to=reply_to,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        ro_id = str(msg.get("ro_id") or "")
        bits = [msg["from_name"], "→", msg["to_name"]]
        if msg.get("work_item_id"):
            bits.append(f"({msg['work_item_id']})")
        bits.append((msg.get("body") or "")[:80])
        append_event(
            conn,
            type="shop_message",
            ro_id=ro_id or "_message",
            item_id=str(msg.get("work_item_id") or ""),
            actor=msg["from_name"],
            summary=" ".join(bits)[:240],
            payload={
                "message_id": msg["id"],
                "from_id": msg["from_id"],
                "from_name": msg["from_name"],
                "from_role": msg["from_role"],
                "to_id": msg["to_id"],
                "to_name": msg["to_name"],
                "to_role": msg["to_role"],
                "actor_id": msg["from_id"],
            },
        )
    preview = (msg.get("body") or "").strip().replace("\n", " ")
    if len(preview) > 80:
        preview = preview[:79] + "…"
    webpush.notify_person(
        VOLUMES.root,
        person_id=to_id,
        title=f"Car-RO · {msg.get('from_name') or 'Shop'}",
        body=preview or "New message",
        url="/messages",
    )
    return {"ok": True, "message": msg}


@app.post("/messages/{message_id}/read")
def post_message_read(message_id: int, body: dict | None = None, _: None = Depends(require_auth)):
    body = body if isinstance(body, dict) else {}
    for_id = str(body.get("for_id") or "").strip()
    if not for_id:
        raise HTTPException(400, "for_id required (recipient id)")
    with _db() as conn:
        try:
            msg = mark_read(conn, message_id, for_id=for_id)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
    if not msg:
        raise HTTPException(404, "Message not found")
    return {"ok": True, "message": msg}


@app.post("/messages/delivered")
def post_messages_delivered(body: dict | None = None, _: None = Depends(require_auth)):
    """Recipient bay ack that messages reached this machine (batch, idempotent)."""
    body = body if isinstance(body, dict) else {}
    for_id = str(body.get("for_id") or "").strip()
    if not for_id:
        raise HTTPException(400, "for_id required (recipient id)")
    raw_ids = body.get("ids") or []
    if not isinstance(raw_ids, list):
        raise HTTPException(400, "ids must be a list of message ids")
    ids: list[int] = []
    for x in raw_ids:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    with _db() as conn:
        messages = mark_delivered(conn, ids, for_id=for_id)
    return {"ok": True, "messages": messages, "count": len(messages)}


@app.post("/messages/{message_id}/renotify")
def post_message_renotify(
    message_id: int, body: dict | None = None, _: None = Depends(require_auth)
):
    """Sender re-pings recipient for an unread message (min 15m gap)."""
    body = body if isinstance(body, dict) else {}
    from_id = str(body.get("from_id") or "").strip()
    if not from_id:
        raise HTTPException(400, "from_id required (sender id)")
    with _db() as conn:
        try:
            msg = renotify(conn, message_id, from_id=from_id)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        bits = [msg["from_name"], "→", msg["to_name"], "(renotify)"]
        if msg.get("work_item_id"):
            bits.append(f"({msg['work_item_id']})")
        bits.append((msg.get("body") or "")[:80])
        append_event(
            conn,
            type="shop_message",
            ro_id=str(msg.get("ro_id") or "") or "_message",
            item_id=str(msg.get("work_item_id") or ""),
            actor=msg["from_name"],
            summary=" ".join(bits)[:240],
            payload={
                "message_id": msg["id"],
                "from_id": msg["from_id"],
                "from_name": msg["from_name"],
                "from_role": msg["from_role"],
                "to_id": msg["to_id"],
                "to_name": msg["to_name"],
                "to_role": msg["to_role"],
                "actor_id": msg["from_id"],
                "renotify": True,
            },
        )
    return {"ok": True, "message": msg}


@app.get("/shifts/active")
def get_active_shifts(_: None = Depends(require_auth)):
    with _db() as conn:
        return {"shifts": list_active(conn)}


@app.get("/shifts")
def get_shifts(
    tech_id: str = "",
    day_from: str = "",
    day_to: str = "",
    limit: int = 500,
    _: None = Depends(require_auth),
):
    with _db() as conn:
        return {
            "shifts": list_shifts(
                conn,
                tech_id=tech_id,
                day_from=day_from,
                day_to=day_to,
                limit=limit,
            )
        }


@app.get("/shifts/mine")
def get_my_shift(tech_id: str = "", _: None = Depends(require_auth)):
    if not (tech_id or "").strip():
        raise HTTPException(400, "tech_id required")
    with _db() as conn:
        return {"shift": get_open_shift(conn, tech_id)}


@app.post("/shifts/start")
def post_shift_start(body: dict, _: None = Depends(require_auth)):
    tech_id = str(body.get("tech_id") or "").strip()
    tech_name = str(body.get("tech_name") or "").strip()
    started_at = str(body.get("started_at") or "").strip() or None
    day = str(body.get("day") or "").strip() or None
    if not tech_id:
        raise HTTPException(400, "tech_id required")
    with _db() as conn:
        try:
            shift = start_shift(
                conn,
                tech_id=tech_id,
                tech_name=tech_name,
                day=day,
                started_at=started_at,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        append_event(
            conn,
            type="tech_day_start",
            ro_id="_shift",
            item_id=tech_id,
            actor=tech_name or tech_id,
            summary=f"{tech_name or tech_id} day start",
            payload={
                "tech_id": tech_id,
                "actor_id": tech_id,
                "shift_id": shift["id"],
            },
        )
    return {"ok": True, "shift": shift}


@app.post("/shifts/end")
def post_shift_end(body: dict, _: None = Depends(require_auth)):
    tech_id = str(body.get("tech_id") or "").strip()
    ended_at = str(body.get("ended_at") or "").strip() or None
    shift_id_raw = body.get("shift_id")
    shift_id = int(shift_id_raw) if shift_id_raw not in (None, "") else None
    if not tech_id and shift_id is None:
        raise HTTPException(400, "tech_id or shift_id required")
    with _db() as conn:
        try:
            shift = end_shift(
                conn, tech_id=tech_id, shift_id=shift_id, ended_at=ended_at
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        append_event(
            conn,
            type="tech_day_end",
            ro_id="_shift",
            item_id=str(shift.get("tech_id") or tech_id),
            actor=str(shift.get("tech_name") or tech_id),
            summary=f"{shift.get('tech_name') or tech_id} day end",
            payload={
                "tech_id": shift.get("tech_id"),
                "actor_id": str(shift.get("tech_id") or tech_id),
                "shift_id": shift["id"],
            },
        )
    return {"ok": True, "shift": shift}


@app.patch("/shifts/{shift_id}")
def patch_shift(shift_id: int, body: dict, _: None = Depends(require_auth)):
    clear_end = bool(body.get("clear_end"))
    started_at = body.get("started_at")
    ended_at = body.get("ended_at")
    day = body.get("day")
    tech_name = body.get("tech_name")
    with _db() as conn:
        try:
            shift = update_shift(
                conn,
                shift_id,
                started_at=str(started_at) if started_at is not None else None,
                ended_at=str(ended_at) if ended_at is not None else None,
                clear_end=clear_end,
                day=str(day) if day is not None else None,
                tech_name=str(tech_name) if tech_name is not None else None,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        append_event(
            conn,
            type="tech_shift_edited",
            ro_id="_shift",
            item_id=str(shift.get("tech_id") or ""),
            actor=str(body.get("edited_by") or "advisor"),
            summary=f"Shift #{shift_id} edited",
            payload={"shift_id": shift_id, "tech_id": shift.get("tech_id")},
        )
    return {"ok": True, "shift": shift}


@app.delete("/shifts/{shift_id}")
def delete_shift_route(shift_id: int, _: None = Depends(require_auth)):
    with _db() as conn:
        existing = get_shift(conn, shift_id)
        if not existing:
            raise HTTPException(404, "Shift not found")
        delete_shift(conn, shift_id)
        append_event(
            conn,
            type="tech_shift_deleted",
            ro_id="_shift",
            item_id=str(existing.get("tech_id") or ""),
            actor="advisor",
            summary=f"Shift #{shift_id} deleted",
            payload={"shift_id": shift_id, "tech_id": existing.get("tech_id")},
        )
    return {"ok": True, "id": shift_id}


@app.get("/reports/weekly")
def get_weekly_report_route(week_start: str = "", _: None = Depends(require_auth)):
    if not (week_start or "").strip():
        raise HTTPException(400, "week_start required (Sunday YYYY-MM-DD)")
    with _db() as conn:
        snap = get_weekly_report(conn, week_start.strip())
    return {"snapshot": snap}


@app.get("/reports/weekly/list")
def list_weekly_reports_route(limit: int = 52, _: None = Depends(require_auth)):
    with _db() as conn:
        return {"weeks": list_weekly_reports(conn, limit=limit)}


@app.put("/reports/weekly/{week_start}")
def put_weekly_report_route(
    week_start: str, body: dict, _: None = Depends(require_auth)
):
    week_end = str(body.get("week_end") or "").strip()
    payload = body.get("payload")
    if not isinstance(payload, dict):
        raise HTTPException(400, "payload object required")
    if not week_end:
        week_end = str(payload.get("week_end") or "").strip()
    if not week_end:
        raise HTTPException(400, "week_end required")
    with _db() as conn:
        try:
            snap = upsert_weekly_report(
                conn,
                week_start=week_start,
                week_end=week_end,
                payload=payload,
                created_by=str(body.get("created_by") or ""),
                created_by_id=str(body.get("created_by_id") or ""),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "snapshot": snap}


@app.delete("/ros/{ro_id}")
def delete_ro(ro_id: str, _: Principal = Depends(require_shop)):
    """Remove RO metadata and photo directories on all volumes."""
    import shutil

    with _db() as conn:
        cur = conn.execute("DELETE FROM repair_orders WHERE id = ?", (ro_id,))
        delete_ro_projections(conn, ro_id)
        removed = cur.rowcount > 0
    photo_dirs = 0
    for name in VOLUMES.list_volumes():
        # Do not call VOLUMES.photos_dir() — it mkdir's and would create empty folders
        pdir = VOLUMES.path_for(name) / "photos" / ro_id
        if pdir.is_dir():
            shutil.rmtree(pdir, ignore_errors=True)
            photo_dirs += 1
    if not removed and photo_dirs == 0:
        raise HTTPException(404, "RO not found")
    return {"ok": True, "id": ro_id, "removed": removed, "photo_dirs": photo_dirs}


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
            sync_ro_projections(conn, order)
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
            sync_ro_projections(conn, stub)
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


_PWA_DIR = _pwa_dir()
_PWA_INDEX = (_PWA_DIR / "index.html") if _PWA_DIR else None


def _serve_pwa_file(rel: str) -> FileResponse | None:
    if not _PWA_DIR:
        return None
    path = (_PWA_DIR / rel).resolve()
    try:
        path.relative_to(_PWA_DIR.resolve())
    except ValueError:
        return None
    if path.is_file():
        return FileResponse(path)
    return None


if _PWA_INDEX is not None:

    @app.get("/")
    def pwa_root():
        return FileResponse(_PWA_INDEX)

    @app.get("/{full_path:path}")
    def pwa_spa(full_path: str):
        """Phone PWA shell — static files, then index.html for client routes."""
        direct = _serve_pwa_file(full_path)
        if direct is not None:
            return direct
        return FileResponse(_PWA_INDEX)
