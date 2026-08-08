"""Easy shop-logo setup for PDF headers (copy into a standard place)."""

from __future__ import annotations

import shutil
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from carro.config import CONFIG_DIR, load_config, save_config

CONSOLE = Console()

LOGO_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
CANONICAL_LOGO = CONFIG_DIR / "logo.png"
BRANDING_DIR = Path.home() / "Documents" / "Car-RO" / "branding"
BRANDING_LOGO = BRANDING_DIR / "logo.png"


def logo_status(cfg: dict | None = None) -> tuple[str, Path | None]:
    """Return (status label, resolved path if any)."""
    from carro.core.pdf import _resolve_logo

    cfg = cfg or load_config()
    path = _resolve_logo(cfg)
    if path:
        return f"ready · {path}", path
    return "(none — PDF will show shop name only)", None


def install_logo(source: Path, *, cfg: dict | None = None) -> Path:
    """
    Copy an image into ~/.config/carro/logo.png (and Documents branding/)
    and point config logo_path at the canonical file.
    """
    source = source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"No file at {source}")
    if source.suffix.lower() not in LOGO_EXTS:
        raise ValueError(
            f"Unsupported type {source.suffix!r} — use PNG or JPG (GIF/WebP also ok)."
        )

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    BRANDING_DIR.mkdir(parents=True, exist_ok=True)

    # Keep a stable name so PDF always finds it; preserve format via suffix.
    dest = CONFIG_DIR / f"logo{source.suffix.lower()}"
    if dest.suffix.lower() == ".jpeg":
        dest = CONFIG_DIR / "logo.jpg"
    shutil.copy2(source, dest)
    # Also drop a copy under Documents for people who browse folders
    branding_dest = BRANDING_DIR / dest.name
    shutil.copy2(source, branding_dest)

    cfg = cfg or load_config()
    cfg["logo_path"] = str(dest)
    save_config(cfg)
    return dest


def clear_logo(cfg: dict | None = None) -> None:
    cfg = cfg or load_config()
    cfg["logo_path"] = ""
    save_config(cfg)
    for folder in (CONFIG_DIR, BRANDING_DIR):
        if not folder.is_dir():
            continue
        for p in folder.glob("logo.*"):
            if p.suffix.lower() in LOGO_EXTS:
                try:
                    p.unlink()
                except OSError:
                    pass


def find_logo_candidates(*, limit: int = 20) -> list[Path]:
    """Recent-ish images from places techs usually drop a logo."""
    roots = [
        Path.home() / "Downloads",
        Path.home() / "Desktop",
        Path.home() / "Pictures",
        BRANDING_DIR,
        Path.home() / "Documents",
    ]
    found: list[tuple[float, Path]] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for p in entries:
            if not p.is_file():
                continue
            if p.suffix.lower() not in LOGO_EXTS:
                continue
            try:
                resolved = p.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                mtime = p.stat().st_mtime
            except OSError:
                mtime = 0.0
            found.append((mtime, p))
    found.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in found[:limit]]


def run_logo_setup() -> None:
    """Guided logo installer for inexperienced users."""
    cfg = load_config()
    status, current = logo_status(cfg)

    CONSOLE.print()
    CONSOLE.print(
        Panel(
            "[bold]Shop logo for PDF[/]\n\n"
            "This image appears [bold]top-right[/] on customer PDFs next to your shop name.\n"
            "Use a [bold]PNG[/] or [bold]JPG[/] (transparent PNG looks best).\n\n"
            f"Current: [cyan]{status}[/]\n\n"
            "[dim]Easiest: save your logo into Downloads, then pick it from the list below.\n"
            f"Or put it here first: {BRANDING_LOGO}[/]",
            title="Logo setup",
            border_style="cyan",
        )
    )

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[bold cyan]1[/]", "Pick from Downloads / Desktop / Pictures")
    table.add_row("[bold cyan]2[/]", "I already saved logo.png in Documents/Car-RO/branding/")
    table.add_row("[bold cyan]3[/]", "Type a file path")
    table.add_row("[bold cyan]4[/]", "Clear logo (shop name only)")
    table.add_row("[bold cyan]b[/]", "Back")
    CONSOLE.print(table)

    choice = Prompt.ask("Choice", default="1").strip().lower()
    if choice in {"b", "q", "back", ""}:
        return

    try:
        if choice == "1":
            _pick_from_candidates()
        elif choice == "2":
            _from_branding_drop()
        elif choice == "3":
            _from_typed_path()
        elif choice == "4":
            if Confirm.ask("Clear logo from config?", default=False):
                clear_logo()
                CONSOLE.print("[green]Logo cleared[/] — PDFs will use shop name only.")
        else:
            CONSOLE.print("[yellow]Unknown option[/]")
    except (OSError, ValueError) as exc:
        CONSOLE.print(f"[red]{exc}[/]")


def _finish(dest: Path) -> None:
    CONSOLE.print(f"[green]Logo ready[/] → {dest}")
    CONSOLE.print(
        "[dim]Export any RO PDF (menu 9 or `carro pdf`) to see it. "
        "Change anytime: config → Logo.[/]"
    )


def _pick_from_candidates() -> None:
    cands = find_logo_candidates()
    if not cands:
        CONSOLE.print(
            "[yellow]No PNG/JPG found[/] in Downloads, Desktop, Pictures, or branding.\n"
            "Save your logo there (or into Documents/Car-RO/branding/), then try again.\n"
            "Or choose option 3 and type the full path."
        )
        return
    table = Table(title="Recent images")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("File")
    table.add_column("Folder")
    for i, p in enumerate(cands, 1):
        table.add_row(str(i), p.name, str(p.parent))
    CONSOLE.print(table)
    raw = Prompt.ask(f"Pick 1–{len(cands)} (or empty to cancel)", default="1").strip()
    if not raw:
        return
    if not raw.isdigit() or not (1 <= int(raw) <= len(cands)):
        CONSOLE.print("[yellow]Cancelled[/]")
        return
    dest = install_logo(cands[int(raw) - 1])
    _finish(dest)


def _from_branding_drop() -> None:
    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    # Prefer logo.png / logo.jpg, else any image in branding/
    for name in ("logo.png", "logo.jpg", "logo.jpeg", "logo.gif", "logo.webp"):
        p = BRANDING_DIR / name
        if p.is_file():
            dest = install_logo(p)
            _finish(dest)
            return
    extras = [
        p
        for p in BRANDING_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in LOGO_EXTS
    ] if BRANDING_DIR.is_dir() else []
    if extras:
        dest = install_logo(extras[0])
        _finish(dest)
        return
    CONSOLE.print(
        f"[yellow]Nothing in[/] {BRANDING_DIR}\n"
        f"Copy your file there as [bold]logo.png[/], then choose this option again."
    )
    CONSOLE.print(f"[dim]mkdir -p {BRANDING_DIR} && cp ~/Downloads/mylogo.png {BRANDING_LOGO}[/]")


def _from_typed_path() -> None:
    raw = Prompt.ask("Full path to PNG/JPG").strip().strip('"').strip("'")
    if not raw:
        return
    dest = install_logo(Path(raw))
    _finish(dest)
