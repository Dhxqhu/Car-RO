"""Car-RO configuration (~/.config/carro/config.toml)."""

from __future__ import annotations

import tomllib
from copy import deepcopy
from pathlib import Path

try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore

CONFIG_DIR = Path.home() / ".config" / "carro"
CONFIG_FILE = CONFIG_DIR / "config.toml"
DATA_DIR = Path.home() / ".local" / "share" / "carro"
# Human-visible photo library (not the empty repo share/ stub)
PHOTOS_DIR = Path.home() / "Documents" / "Car-RO" / "photos"
DEFAULTS: dict = {
    "shop_name": "(shop name here)",
    "server_url": "",
    "token": "",
    "local_keep": 20,
    "local_photo_keep": 20,
    "photos": {
        "provider": "local",
        "inbox_dir": str(Path.home() / "Documents" / "Car-RO" / "inbox"),
        "dir": str(PHOTOS_DIR),
    },
}


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = deepcopy(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    cfg = deepcopy(DEFAULTS)
    if CONFIG_FILE.is_file():
        with CONFIG_FILE.open("rb") as fh:
            raw = tomllib.load(fh)
        if isinstance(raw, dict):
            cfg = _deep_merge(cfg, raw)
    photos = cfg.setdefault("photos", {})
    for key in ("inbox_dir", "dir"):
        if photos.get(key):
            photos[key] = str(Path(photos[key]).expanduser())
    if not photos.get("dir"):
        photos["dir"] = str(PHOTOS_DIR)
    cfg["server_url"] = str(cfg.get("server_url") or "").rstrip("/")
    return cfg


def photos_dir(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    return Path((cfg.get("photos") or {}).get("dir") or PHOTOS_DIR).expanduser()


def save_config(cfg: dict) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    photos = cfg.get("photos") or {}
    lines = [
        f'shop_name = {_toml_str(cfg.get("shop_name", "(shop name here)"))}',
        f'server_url = {_toml_str(cfg.get("server_url", ""))}',
        f'token = {_toml_str(cfg.get("token", ""))}',
        f'local_keep = {int(cfg.get("local_keep", 20))}',
        f'local_photo_keep = {int(cfg.get("local_photo_keep", 20))}',
        "",
        "[photos]",
        f'provider = {_toml_str(photos.get("provider", "local"))}',
        f'inbox_dir = {_toml_str(photos.get("inbox_dir", ""))}',
        f'dir = {_toml_str(photos.get("dir", str(PHOTOS_DIR)))}',
        "",
    ]
    CONFIG_FILE.write_text("\n".join(lines), encoding="utf-8")
    return CONFIG_FILE


def _toml_str(value: object) -> str:
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def ensure_dirs(cfg: dict | None = None) -> None:
    cfg = cfg or load_config()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "pdf").mkdir(parents=True, exist_ok=True)
    photos_dir(cfg).mkdir(parents=True, exist_ok=True)
    inbox = Path((cfg.get("photos") or {}).get("inbox_dir") or DATA_DIR / "inbox")
    inbox.mkdir(parents=True, exist_ok=True)
