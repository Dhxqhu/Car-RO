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
DEFAULTS: dict = {
    "shop_name": "My Shop",
    "server_url": "",
    "token": "",
    "local_keep": 20,
    "local_photo_keep": 20,
    "photos": {
        "provider": "local",
        "inbox_dir": str(Path.home() / "Documents" / "Car-RO" / "inbox"),
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
    # Expand inbox path
    inbox = cfg.get("photos", {}).get("inbox_dir", "")
    if inbox:
        cfg["photos"]["inbox_dir"] = str(Path(inbox).expanduser())
    cfg["server_url"] = str(cfg.get("server_url") or "").rstrip("/")
    return cfg


def save_config(cfg: dict) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Minimal TOML writer without tomli_w dependency
    lines = [
        f'shop_name = {_toml_str(cfg.get("shop_name", "My Shop"))}',
        f'server_url = {_toml_str(cfg.get("server_url", ""))}',
        f'token = {_toml_str(cfg.get("token", ""))}',
        f'local_keep = {int(cfg.get("local_keep", 20))}',
        f'local_photo_keep = {int(cfg.get("local_photo_keep", 20))}',
        "",
        "[photos]",
        f'provider = {_toml_str((cfg.get("photos") or {}).get("provider", "local"))}',
        f'inbox_dir = {_toml_str((cfg.get("photos") or {}).get("inbox_dir", ""))}',
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
    (DATA_DIR / "photos").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "pdf").mkdir(parents=True, exist_ok=True)
    inbox = Path((cfg.get("photos") or {}).get("inbox_dir") or DATA_DIR / "inbox")
    inbox.mkdir(parents=True, exist_ok=True)
