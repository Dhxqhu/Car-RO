"""Local path + inbox photo provider."""

from __future__ import annotations

from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif"}


class LocalPhotoIngress:
    name = "local"

    def __init__(self, cfg: dict):
        photos = cfg.get("photos") or {}
        self.inbox = Path(photos.get("inbox_dir") or "").expanduser()
        self._pending: list[Path] = []
        self._tag = "other"
        self._ro_id = ""

    def start(self, ro_id: str, tag: str) -> None:
        self._ro_id = ro_id
        self._tag = tag or "other"
        self._pending = []
        self.inbox.mkdir(parents=True, exist_ok=True)

    def add_paths(self, paths: list[Path]) -> list[Path]:
        found = []
        for p in paths:
            p = Path(p).expanduser().resolve()
            if p.is_file() and p.suffix.lower() in IMAGE_EXT:
                found.append(p)
        self._pending.extend(found)
        return found

    def ingest_inbox(self) -> list[Path]:
        if not self.inbox.is_dir():
            return []
        found = [
            p
            for p in sorted(self.inbox.iterdir())
            if p.is_file() and p.suffix.lower() in IMAGE_EXT
        ]
        self._pending.extend(found)
        return found

    def collect(self) -> list[Path]:
        items = list(self._pending)
        self._pending = []
        return items

    def stop(self) -> None:
        self._pending = []
