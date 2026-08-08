"""Multi-volume storage layout for carro-server.

Volumes are named mounts (e.g. hdd2, hdd1). New drives are added by appending
to volumes.json — no code change required.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

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
        # If CARRO_VOLUMES is set: name=path,name=path
        extra = os.environ.get("CARRO_VOLUMES", "").strip()
        if extra:
            vols = {}
            for part in extra.split(","):
                part = part.strip()
                if "=" not in part:
                    continue
                name, path = part.split("=", 1)
                vols[name.strip()] = {"path": path.strip(), "role": "data"}
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

    @property
    def default_name(self) -> str:
        return str(self.data.get("default") or "primary")

    def list_volumes(self) -> dict[str, dict]:
        return dict(self.data.get("volumes") or {})

    def add_volume(self, name: str, path: str, *, make_default: bool = False) -> None:
        name = name.strip()
        p = Path(path).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        vols = self.data.setdefault("volumes", {})
        vols[name] = {"path": str(p), "role": "data"}
        if make_default or not self.data.get("default"):
            self.data["default"] = name
            vols[name]["role"] = "primary"
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
        # Metadata DB always on primary volume
        return self.path_for(self.default_name) / "carro_server.db"
