"""Optional web/QR photo provider stub — swap in later without changing RO core."""

from __future__ import annotations

from pathlib import Path


class WebQrPhotoIngress:
    """Placeholder. Enable later via photos.provider = \"web_qr\"."""

    name = "web_qr"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._ro_id = ""
        self._tag = "other"

    def start(self, ro_id: str, tag: str) -> None:
        self._ro_id = ro_id
        self._tag = tag
        raise RuntimeError(
            "web_qr provider is not enabled yet. "
            "Set photos.provider = \"local\" or use: carro photo add <file>"
        )

    def collect(self) -> list[Path]:
        return []

    def stop(self) -> None:
        return None
