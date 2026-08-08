"""Optional web/QR provider — use menu photo → phone (Tailscale upload page)."""

from __future__ import annotations

from pathlib import Path


class WebQrPhotoIngress:
    """Deprecated stub: phone uploads go through `carro photo phone`."""

    name = "web_qr"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def start(self, ro_id: str, tag: str) -> None:
        raise RuntimeError(
            "Use: carro photo phone --id RO-… --tag intake "
            "(or menu 6 → phone) with Tailscale on the iPhone."
        )

    def collect(self) -> list[Path]:
        return []

    def stop(self) -> None:
        return None
