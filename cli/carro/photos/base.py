"""Photo ingress protocol + registry."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class PhotoIngress(Protocol):
    name: str

    def start(self, ro_id: str, tag: str) -> None: ...

    def collect(self) -> list[Path]: ...

    def stop(self) -> None: ...


def get_provider(name: str, cfg: dict) -> PhotoIngress:
    name = (name or "local").lower()
    if name == "local":
        from carro.photos.providers.local import LocalPhotoIngress

        return LocalPhotoIngress(cfg)
    if name == "web_qr":
        from carro.photos.providers.web_qr import WebQrPhotoIngress

        return WebQrPhotoIngress(cfg)
    raise ValueError(f"Unknown photo provider: {name}")
