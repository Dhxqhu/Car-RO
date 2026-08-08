"""Attach photo files into a repair order (local + optional remote)."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from carro.config import photos_dir
from carro.core.db import LocalStore
from carro.core.models import RepairOrder, now_iso
from carro.storage.remote import RemoteClient


def local_photo_path(order_id: str, relpath: str) -> Path:
    return photos_dir() / order_id / Path(relpath).name


def attach_photos(
    store: LocalStore,
    order: RepairOrder,
    paths: list[Path],
    *,
    tag: str = "other",
    notes: str = "",
    notes_by_path: dict[str, str] | None = None,
    sync_remote: bool = True,
) -> RepairOrder:
    dest_dir = photos_dir() / order.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    remote = RemoteClient()
    notes_by_path = notes_by_path or {}
    for src in paths:
        src = Path(src)
        if not src.is_file():
            continue
        photo_id = uuid.uuid4().hex[:12]
        dest_name = f"{photo_id}_{src.name}"
        dest = dest_dir / dest_name
        shutil.copy2(src, dest)
        note = (notes_by_path.get(str(src)) or notes or "").strip()
        meta = {
            "id": photo_id,
            "filename": src.name,
            "tag": tag,
            "notes": note,
            "volume": "local",
            "relpath": dest_name,
            "created": now_iso(),
        }
        order.photos.append(meta)
        if sync_remote and remote.enabled:
            try:
                remote_meta = remote.upload_photo(
                    order.id,
                    str(dest),
                    tag=tag,
                    filename=dest_name,
                    notes=note,
                )
                if isinstance(remote_meta, dict):
                    meta["volume"] = remote_meta.get("volume", meta["volume"])
                    meta["remote"] = True
            except Exception:
                meta["remote"] = False
    return store.save(order)


def ensure_local_photos(order: RepairOrder) -> list[Path]:
    """
    Make sure each photo exists under Documents/Car-RO/photos/<ro_id>/.
    Downloads from the server when metadata exists but the file is missing
    (common after iPhone Tailscale upload).
    """
    dest_dir = photos_dir() / order.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    remote = RemoteClient()
    found: list[Path] = []
    for meta in order.photos:
        rel = meta.get("relpath") or meta.get("filename")
        if not rel:
            continue
        dest = dest_dir / Path(rel).name
        if dest.is_file():
            found.append(dest)
            continue
        if not remote.enabled:
            continue
        try:
            remote.download_photo(
                order.id,
                Path(rel).name,
                dest,
                volume=str(meta.get("volume") or "") or None,
            )
            if dest.is_file():
                found.append(dest)
        except Exception:
            continue
    return found
