"""Attach photo files into a repair order (local + optional remote)."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from carro.config import DATA_DIR
from carro.core.db import LocalStore
from carro.core.models import RepairOrder, now_iso
from carro.storage.remote import RemoteClient


def attach_photos(
    store: LocalStore,
    order: RepairOrder,
    paths: list[Path],
    *,
    tag: str = "other",
    sync_remote: bool = True,
) -> RepairOrder:
    dest_dir = DATA_DIR / "photos" / order.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    remote = RemoteClient()
    for src in paths:
        src = Path(src)
        if not src.is_file():
            continue
        photo_id = uuid.uuid4().hex[:12]
        dest_name = f"{photo_id}_{src.name}"
        dest = dest_dir / dest_name
        shutil.copy2(src, dest)
        meta = {
            "id": photo_id,
            "filename": src.name,
            "tag": tag,
            "volume": "local",
            "relpath": dest_name,
            "created": now_iso(),
        }
        order.photos.append(meta)
        if sync_remote and remote.enabled:
            try:
                remote_meta = remote.upload_photo(order.id, str(dest), tag=tag, filename=dest_name)
                if isinstance(remote_meta, dict):
                    meta["volume"] = remote_meta.get("volume", meta["volume"])
                    meta["remote"] = True
            except Exception:
                meta["remote"] = False
    return store.save(order)
