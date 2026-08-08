"""iPhone / Tailscale QR upload session helper."""

from __future__ import annotations

import io
from typing import Callable

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from carro.storage.remote import RemoteClient

CONSOLE = Console()


def start_phone_upload(
    ro_id: str,
    *,
    tag: str = "intake",
    ttl_sec: int = 3600,
    on_done: Callable[[], None] | None = None,
) -> str:
    """
    Create a short-lived upload URL, print QR + link, wait for Enter, then callback.
    Returns the public upload URL.
    """
    remote = RemoteClient()
    if not remote.enabled:
        raise RuntimeError(
            "Phone upload needs server_url in ~/.config/carro/config.toml "
            "(Tailscale URL of carro-server)."
        )
    sess = remote.create_upload_session(ro_id, tag=tag, ttl_sec=ttl_sec)
    path = sess.get("path") or f"/u/{sess['token']}"
    url = f"{remote.base.rstrip('/')}{path}"

    CONSOLE.print(
        Panel(
            f"[bold]iPhone photo upload[/]\n\n"
            f"RO: [cyan]{ro_id}[/]  tag: [cyan]{tag}[/]\n"
            f"1. Turn on Tailscale on the iPhone\n"
            f"2. Scan the QR (or open the URL in Safari)\n"
            f"3. Take / choose photos and tap Upload\n"
            f"4. Come back here and press Enter to refresh the RO\n\n"
            f"[bold]{url}[/]",
            border_style="magenta",
            title="Phone upload",
        )
    )
    _print_qr(url)
    Prompt.ask("Press Enter after uploading on the phone", default="")
    try:
        st = remote.upload_session_status(sess["token"])
        CONSOLE.print(
            f"[dim]Session uploads reported:[/] {st.get('uploads', 0)}"
        )
    except Exception:
        pass
    if on_done:
        on_done()
    return url


def _print_qr(url: str) -> None:
    try:
        import qrcode
    except ImportError:
        CONSOLE.print("[yellow]qrcode package missing — open the URL manually.[/]")
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=True)
    CONSOLE.print(buf.getvalue())
