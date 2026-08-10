"""Multi-volume storage layout for carro-server.

Volumes are named mounts (e.g. primary, extra). New drives are added via
POST /volumes or by editing volumes.json — no code change required.

- CARRO_DATA_DIR (self.root) always holds volumes.json, the SQLite DB,
  technicians/advisors JSON, and upload sessions.
- Named volumes hold photo blobs under <path>/photos/<ro_id>/.
- ``default`` is where *new* photos land; changing it never moves the DB.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")

DEFAULT_VOLUMES = {
    "version": 1,
    "default": "primary",
    "volumes": {
        "primary": {
            "path": "",  # filled from CARRO_DATA_DIR or first volume
            "role": "primary",
        }
    },
}


class VolumeManager:
    def __init__(self, root: Path | None = None, volumes_file: Path | None = None):
        env_root = os.environ.get("CARRO_DATA_DIR", "").strip()
        self.root = Path(root or env_root or "./carro-data").expanduser().resolve()
        self.volumes_file = volumes_file or (self.root / "volumes.json")
        self.root.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict:
        if self.volumes_file.is_file():
            try:
                raw = json.loads(self.volumes_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and "volumes" in raw:
                    return raw
            except (OSError, json.JSONDecodeError):
                pass
        data = json.loads(json.dumps(DEFAULT_VOLUMES))
        # If CARRO_VOLUMES is set: name=path,name=path (first-run bootstrap only)
        extra = os.environ.get("CARRO_VOLUMES", "").strip()
        if extra:
            vols = {}
            for part in extra.split(","):
                part = part.strip()
                if "=" not in part:
                    continue
                name, path = part.split("=", 1)
                name, path = name.strip(), path.strip()
                if not name or not path:
                    continue
                vols[name] = {"path": str(Path(path).expanduser().resolve()), "role": "data"}
            if vols:
                data["volumes"] = vols
                data["default"] = next(iter(vols))
                data["volumes"][data["default"]]["role"] = "primary"
        else:
            data["volumes"]["primary"]["path"] = str(self.root)
        self._save(data)
        return data

    def _save(self, data: dict | None = None) -> None:
        data = data or self.data
        self.volumes_file.parent.mkdir(parents=True, exist_ok=True)
        self.volumes_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def reload(self) -> None:
        """Re-read volumes.json (e.g. after a hand edit + API reload)."""
        self.data = self._load()

    @property
    def default_name(self) -> str:
        return str(self.data.get("default") or "primary")

    def list_volumes(self) -> dict[str, dict]:
        return dict(self.data.get("volumes") or {})

    def volume_stats(self) -> dict[str, dict]:
        """Volume metadata plus free/total disk (bytes) when the path is mounted."""
        out: dict[str, dict] = {}
        for name, meta in self.list_volumes().items():
            entry = {
                "path": meta.get("path"),
                "role": meta.get("role") or "data",
                "is_default": name == self.default_name,
            }
            try:
                p = Path(str(meta.get("path") or "")).expanduser()
                if p.exists():
                    usage = shutil.disk_usage(p)
                    entry["free_bytes"] = int(usage.free)
                    entry["total_bytes"] = int(usage.total)
                    entry["used_bytes"] = int(usage.used)
                    entry["free_gb"] = round(usage.free / (1024**3), 2)
                    entry["total_gb"] = round(usage.total / (1024**3), 2)
                    entry["mounted"] = True
                else:
                    entry["mounted"] = False
            except OSError:
                entry["mounted"] = False
            out[name] = entry
        return out

    @staticmethod
    def validate_name(name: str) -> str:
        name = (name or "").strip()
        if not _NAME_RE.match(name):
            raise ValueError(
                "Volume name must be 1–64 chars: letters, digits, . _ - "
                "(start with letter or digit)"
            )
        return name

    def add_volume(self, name: str, path: str, *, make_default: bool = False) -> None:
        name = self.validate_name(name)
        p = Path(path).expanduser().resolve()
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".carro_write_test"
            probe.write_text("ok\n", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            raise ValueError(f"Path not writable: {p} ({exc})") from exc

        vols = self.data.setdefault("volumes", {})
        if name in vols:
            # Update path on existing name (same drive remounted elsewhere).
            vols[name]["path"] = str(p)
            if make_default:
                self.set_default(name)
            else:
                self._save()
            return

        vols[name] = {"path": str(p), "role": "data"}
        if make_default or not self.data.get("default"):
            self.set_default(name)
        else:
            self._save()

    def set_default(self, name: str) -> None:
        """Send new photo uploads to this volume. Does not move the SQLite DB."""
        name = self.validate_name(name)
        vols = self.list_volumes()
        if name not in vols:
            raise KeyError(f"Unknown volume '{name}'. Known: {', '.join(vols) or '(none)'}")
        for n, meta in vols.items():
            if not isinstance(meta, dict):
                continue
            if n == name:
                meta["role"] = "primary"
            elif meta.get("role") == "primary":
                meta["role"] = "data"
        self.data["default"] = name
        self.data["volumes"] = vols
        self._save()

    def path_for(self, name: str | None = None) -> Path:
        name = name or self.default_name
        vols = self.list_volumes()
        if name not in vols:
            raise KeyError(f"Unknown volume '{name}'. Known: {', '.join(vols) or '(none)'}")
        p = Path(vols[name]["path"]).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def photos_dir(self, ro_id: str, volume: str | None = None) -> Path:
        base = self.path_for(volume) / "photos" / ro_id
        base.mkdir(parents=True, exist_ok=True)
        return base

    def db_path(self) -> Path:
        """
        Prefer CARRO_DATA_DIR/carro_server.db so photo volumes can change freely.
        If an older install already has the DB on the default volume path, keep using it.
        """
        preferred = self.root / "carro_server.db"
        if preferred.is_file():
            return preferred
        try:
            legacy = Path(self.list_volumes().get(self.default_name, {}).get("path") or "")
            if legacy:
                candidate = legacy.expanduser() / "carro_server.db"
                if candidate.is_file():
                    return candidate
        except Exception:
            pass
        self.root.mkdir(parents=True, exist_ok=True)
        return preferred
