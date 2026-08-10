"""Car-RO configuration (~/.config/carro/config.toml)."""

from __future__ import annotations

import shutil
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

# Rough average footprint per RO with a few phone photos (for auto sizing)
_AVG_RO_BYTES = 18 * 1024 * 1024
_AVG_PHOTO_RO_BYTES = 28 * 1024 * 1024

DEFAULTS: dict = {
    "shop_name": "(shop name here)",
    "logo_path": "",
    "server_url": "",
    "token": "",
    # "auto" sizes from free disk on the photos volume; or an int count
    "local_keep": "auto",
    "local_photo_keep": "auto",
    # Closed (billed_out) ROs kept locally for quick reopen / recent history
    "local_billed_keep": 20,
    # Hours to keep received part lines locally before stripping (server still has RO)
    "local_parts_received_keep_hours": 24,
    # Nudge when a work item or part sits untouched this long (0 = off)
    "idle_nudge_hours": 24,
    # Background push to shop server while engine/CLI menu is open. 0 = off.
    "autosync_minutes": 0,
    # Textual TUI theme (search / history / RO forms). Ctrl+P changes persist here.
    "textual_theme": "ansi-dark",
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
    if cfg.get("logo_path"):
        cfg["logo_path"] = str(Path(cfg["logo_path"]).expanduser())
    cfg["server_url"] = str(cfg.get("server_url") or "").rstrip("/")
    cfg["autosync_minutes"] = _parse_autosync_minutes(cfg.get("autosync_minutes", 0))
    return cfg


def _parse_autosync_minutes(raw: object) -> int:
    try:
        n = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        n = 0
    return max(0, min(n, 24 * 60))  # cap at 24h


def resolve_autosync_minutes(cfg: dict | None = None) -> int:
    """Minutes between background syncs. 0 (default) means off."""
    if cfg is None:
        return int(load_config().get("autosync_minutes") or 0)
    return _parse_autosync_minutes(cfg.get("autosync_minutes", 0))


def photos_dir(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    return Path((cfg.get("photos") or {}).get("dir") or PHOTOS_DIR).expanduser()


def storage_root(cfg: dict | None = None) -> Path:
    """Directory used to judge free disk for local cache sizing."""
    root = photos_dir(cfg)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        root = DATA_DIR
        root.mkdir(parents=True, exist_ok=True)
    return root


def disk_info(path: Path | None = None) -> dict:
    """Free/total space for the volume holding local photos/cache."""
    path = path or storage_root()
    usage = shutil.disk_usage(path)
    return {
        "path": str(path),
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
        "total_gb": usage.total / (1024**3),
        "used_gb": usage.used / (1024**3),
        "free_gb": usage.free / (1024**3),
    }


def recommend_local_keep(path: Path | None = None) -> int:
    """
    Suggest how many ROs to keep locally from free disk.
    Uses a slice of free space (capped) at a typical RO+photos footprint.
    """
    info = disk_info(path)
    free = info["free"]
    # Budget: smaller of 8% of free disk or 12 GiB; leave machines with little free room light
    budget = min(int(free * 0.08), 12 * 1024**3)
    if info["free_gb"] < 8:
        budget = min(budget, int(free * 0.03))
    n = int(budget / _AVG_RO_BYTES)
    return max(5, min(n, 300))


def recommend_local_photo_keep(path: Path | None = None, *, ro_keep: int | None = None) -> int:
    """Suggest how many recent ROs should retain local photo files."""
    info = disk_info(path)
    free = info["free"]
    budget = min(int(free * 0.05), 8 * 1024**3)
    if info["free_gb"] < 8:
        budget = min(budget, int(free * 0.02))
    n = int(budget / _AVG_PHOTO_RO_BYTES)
    n = max(3, min(n, 200))
    if ro_keep is not None:
        n = min(n, int(ro_keep))
    return n


def keep_presets(path: Path | None = None) -> list[tuple[str, object, str]]:
    """Selectable local_keep choices: (label, value, detail)."""
    rec = recommend_local_keep(path)
    info = disk_info(path)
    light = 10
    standard = max(20, min(rec, max(25, rec // 2)))
    heavy = min(300, max(rec, standard + 20))
    return [
        ("auto", "auto", f"follow free disk → ~{rec} ROs now ({info['free_gb']:.0f} GB free)"),
        ("light", light, "small SSD / low free space"),
        ("standard", standard, "typical shop laptop"),
        ("recommended", rec, "sized for this machine right now"),
        ("heavy", heavy, "keep more history locally"),
        ("custom", None, "type any number"),
    ]


def photo_keep_presets(
    path: Path | None = None, *, ro_keep: int | None = None
) -> list[tuple[str, object, str]]:
    rec = recommend_local_photo_keep(path, ro_keep=ro_keep)
    info = disk_info(path)
    light = 5
    standard = max(8, min(rec, max(10, rec // 2)))
    heavy = min(200, max(rec, standard + 10))
    if ro_keep is not None:
        heavy = min(heavy, int(ro_keep))
        rec = min(rec, int(ro_keep))
        standard = min(standard, int(ro_keep))
    return [
        ("auto", "auto", f"follow free disk → ~{rec} with photos ({info['free_gb']:.0f} GB free)"),
        ("light", light, "metadata-heavy, few local images"),
        ("standard", standard, "recent jobs keep photos"),
        ("recommended", rec, "sized for this machine right now"),
        ("heavy", heavy, "keep more photo files locally"),
        ("match_ros", "match", "same as local RO keep"),
        ("custom", None, "type any number"),
    ]


def _is_auto(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in {"auto", "dynamic", ""}:
        return True
    return False


def resolve_local_keep(cfg: dict | None = None) -> int:
    cfg = cfg or load_config()
    raw = cfg.get("local_keep", "auto")
    if _is_auto(raw):
        return recommend_local_keep()
    return max(0, int(raw))


def resolve_local_photo_keep(cfg: dict | None = None) -> int:
    cfg = cfg or load_config()
    ro_keep = resolve_local_keep(cfg)
    raw = cfg.get("local_photo_keep", "auto")
    if isinstance(raw, str) and raw.strip().lower() == "match":
        return ro_keep
    if _is_auto(raw):
        return recommend_local_photo_keep(ro_keep=ro_keep)
    return max(0, min(int(raw), ro_keep if ro_keep else int(raw)))


def resolve_local_billed_keep(cfg: dict | None = None) -> int:
    """How many newest billed_out ROs to retain locally (default 20)."""
    cfg = cfg or load_config()
    raw = cfg.get("local_billed_keep", 20)
    if _is_auto(raw):
        return 20
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 20


def resolve_local_parts_received_keep_hours(cfg: dict | None = None) -> float:
    """Hours to keep received part lines locally before stripping (default 24)."""
    cfg = cfg or load_config()
    raw = cfg.get("local_parts_received_keep_hours", 24)
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 24.0


def resolve_idle_nudge_hours(cfg: dict | None = None) -> float:
    """Hours before an untouched work item / part shows an idle nudge (0 = off)."""
    cfg = cfg or load_config()
    raw = cfg.get("idle_nudge_hours", 24)
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 24.0


def format_keep_setting(raw: object, resolved: int) -> str:
    if isinstance(raw, str) and raw.strip().lower() == "match":
        return f"match (→ {resolved})"
    if _is_auto(raw):
        return f"auto (→ {resolved})"
    return str(int(raw))


def save_config(cfg: dict) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    photos = cfg.get("photos") or {}

    def _keep_toml(value: object, default: object = "auto") -> str:
        if value is None:
            value = default
        if isinstance(value, str):
            return _toml_str(value.strip() or "auto")
        return str(int(value))

    lines = [
        f'shop_name = {_toml_str(cfg.get("shop_name", "(shop name here)"))}',
        f'logo_path = {_toml_str(cfg.get("logo_path", ""))}',
        f'server_url = {_toml_str(cfg.get("server_url", ""))}',
        f'token = {_toml_str(cfg.get("token", ""))}',
        f'local_keep = {_keep_toml(cfg.get("local_keep", "auto"))}',
        f'local_photo_keep = {_keep_toml(cfg.get("local_photo_keep", "auto"))}',
        f"local_billed_keep = {int(resolve_local_billed_keep(cfg))}",
        f"local_parts_received_keep_hours = {resolve_local_parts_received_keep_hours(cfg):g}",
        f"idle_nudge_hours = {resolve_idle_nudge_hours(cfg):g}",
        f"autosync_minutes = {_parse_autosync_minutes(cfg.get('autosync_minutes', 0))}",
        f'textual_theme = {_toml_str(cfg.get("textual_theme", "ansi-dark"))}',
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
