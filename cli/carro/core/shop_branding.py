"""Shop name + PDF logo — local config with optional shop-server sync."""

from __future__ import annotations

import json
import mimetypes
import shutil
from pathlib import Path
from typing import Any

from carro.config import CONFIG_DIR, load_config, save_config
from carro.core.logo_setup import CANONICAL_LOGO, LOGO_EXTS, clear_logo, install_logo
from carro.core.models import now_iso

DEFAULT_SHOP_NAME = "(shop name here)"
META_FILE = CONFIG_DIR / "shop_branding.json"
SERVER_LOGO_BASENAME = "shop_logo"


def empty_meta() -> dict[str, Any]:
    return {"updated": "", "source": "local"}


def load_meta() -> dict[str, Any]:
    if not META_FILE.is_file():
        return empty_meta()
    try:
        raw = json.loads(META_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_meta()
    if not isinstance(raw, dict):
        return empty_meta()
    return {
        "updated": str(raw.get("updated") or ""),
        "source": str(raw.get("source") or "local"),
    }


def save_meta(meta: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated": str(meta.get("updated") or now_iso()),
        "source": str(meta.get("source") or "local"),
    }
    META_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _logo_candidates() -> list[Path]:
    cfg = load_config()
    paths: list[Path] = []
    raw = str(cfg.get("logo_path") or "").strip()
    if raw:
        paths.append(Path(raw).expanduser())
    paths.extend(
        [
            CANONICAL_LOGO,
            CONFIG_DIR / "logo.jpg",
            Path.home() / "Documents" / "Car-RO" / "branding" / "logo.png",
        ]
    )
    out: list[Path] = []
    seen: set[str] = set()
    for p in paths:
        try:
            key = str(p.resolve())
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        if p.is_file():
            out.append(p)
    return out


def resolve_logo_path(cfg: dict[str, Any] | None = None) -> Path | None:
    cfg = cfg or load_config()
    for p in _logo_candidates():
        if p.is_file():
            want = str(p)
            if str(cfg.get("logo_path") or "") != want:
                cfg["logo_path"] = want
                save_config(cfg)
            return p
    raw = str(cfg.get("logo_path") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if p.is_file():
            return p
    return None


def local_payload() -> dict[str, Any]:
    cfg = load_config()
    meta = load_meta()
    logo = resolve_logo_path(cfg)
    return {
        "shop_name": str(cfg.get("shop_name") or "").strip(),
        "updated": str(meta.get("updated") or ""),
        "has_logo": bool(logo and logo.is_file()),
    }


def apply_local_name(shop_name: str, *, source: str = "local") -> None:
    name = (shop_name or "").strip()
    if not name:
        return
    cfg = load_config()
    cfg["shop_name"] = name
    save_config(cfg)
    save_meta({"updated": now_iso(), "source": source})


def install_logo_bytes(data: bytes, *, suffix: str = ".png") -> Path:
    if not data:
        raise ValueError("Empty logo file")
    ext = suffix if suffix.startswith(".") else f".{suffix}"
    if ext.lower() not in LOGO_EXTS:
        ext = ".png"
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    dest = CONFIG_DIR / f"logo{ext.lower()}"
    if dest.suffix.lower() == ".jpeg":
        dest = CONFIG_DIR / "logo.jpg"
    dest.write_bytes(data)
    branding = Path.home() / "Documents" / "Car-RO" / "branding"
    branding.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dest, branding / dest.name)
    cfg = load_config()
    cfg["logo_path"] = str(dest)
    save_config(cfg)
    return dest


def apply_remote(payload: dict[str, Any], *, logo_bytes: bytes | None = None) -> dict[str, Any]:
    """Apply shop-server branding to this PC (config + cached logo)."""
    if not isinstance(payload, dict):
        raise ValueError("shop branding payload must be an object")
    name = str(payload.get("shop_name") or "").strip()
    if name:
        apply_local_name(name, source="server")
    ts = str(payload.get("updated") or now_iso())
    save_meta({"updated": ts, "source": "server"})
    if logo_bytes:
        suffix = str(payload.get("logo_ext") or ".png")
        install_logo_bytes(logo_bytes, suffix=suffix)
    elif payload.get("has_logo") is False:
        clear_logo()
        save_meta({"updated": ts, "source": "server"})
    return load_config()


def resolve_pdf_branding(*, refresh_remote: bool = False) -> dict[str, Any]:
    """
    Shop name + logo path for customer PDF headers.
    Uses local config; optionally pulls from shop server when unset.
    """
    cfg = load_config()
    local_name = str(cfg.get("shop_name") or "").strip()
    local_logo = resolve_logo_path(cfg)
    if refresh_remote and (
        not local_name or local_name == DEFAULT_SHOP_NAME or not local_logo
    ):
        try:
            pull_from_server()
        except Exception:
            pass
    cfg = load_config()
    shop_name = str(cfg.get("shop_name") or "").strip() or DEFAULT_SHOP_NAME
    logo = resolve_logo_path(cfg)
    return {
        "shop_name": shop_name,
        "logo_path": logo,
        "source": load_meta().get("source") or "local",
    }


def pull_from_server() -> str:
    from carro.storage.remote import RemoteClient

    remote = RemoteClient()
    if not remote.enabled:
        return "skipped"
    payload = remote.get_shop_branding()
    if not isinstance(payload, dict):
        return "error: bad response"
    logo_bytes = None
    if payload.get("has_logo"):
        try:
            logo_bytes = remote.download_shop_logo()
        except Exception:
            logo_bytes = None
    apply_remote(payload, logo_bytes=logo_bytes)
    name = str(payload.get("shop_name") or "").strip()
    return f"pulled:{name or 'logo'}"


def push_to_server() -> str:
    from carro.storage.remote import RemoteClient

    remote = RemoteClient()
    if not remote.enabled:
        return "skipped"
    cfg = load_config()
    ts = now_iso()
    payload = {
        "shop_name": str(cfg.get("shop_name") or "").strip(),
        "updated": ts,
        "has_logo": bool(resolve_logo_path(cfg)),
    }
    remote.put_shop_branding(payload)
    save_meta({"updated": ts, "source": "local"})
    logo = resolve_logo_path(cfg)
    if logo and logo.is_file():
        remote.upload_shop_logo(logo)
    else:
        try:
            remote.delete_shop_logo()
        except Exception:
            pass
    return "pushed"


def sync_with_server() -> str:
    """Merge local vs shop-server branding by updated timestamp."""
    from carro.storage.remote import RemoteClient

    remote = RemoteClient()
    if not remote.enabled:
        return "skipped"
    local = local_payload()
    local_updated = str(local.get("updated") or "")
    meta = load_meta()
    if not local_updated:
        local_updated = str(meta.get("updated") or "")
    try:
        server = remote.get_shop_branding()
    except Exception as exc:
        return f"error: {exc}"
    if not isinstance(server, dict):
        return "error: bad response"
    server_updated = str(server.get("updated") or "")
    server_name = str(server.get("shop_name") or "").strip()
    local_name = str(local.get("shop_name") or "").strip()

    def _pull() -> str:
        logo_bytes = None
        if server.get("has_logo"):
            try:
                logo_bytes = remote.download_shop_logo()
            except Exception:
                logo_bytes = None
        apply_remote(server, logo_bytes=logo_bytes)
        return "pulled"

    if server_name and not local_name:
        return _pull()
    if local_name and not server_name:
        return push_to_server()
    if server_updated and local_updated:
        if server_updated > local_updated:
            return _pull()
        if local_updated > server_updated:
            return push_to_server()
        return "ok"
    if server_name and local_name == DEFAULT_SHOP_NAME:
        return _pull()
    if server_name:
        return _pull()
    if local_name and local_name != DEFAULT_SHOP_NAME:
        return push_to_server()
    return "ok"
