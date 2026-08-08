"""Interactive config menu (selectable settings)."""

from __future__ import annotations

import secrets
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from carro.config import (
    CONFIG_FILE,
    disk_info,
    ensure_dirs,
    format_keep_setting,
    keep_presets,
    load_config,
    photo_keep_presets,
    resolve_local_keep,
    resolve_local_photo_keep,
    save_config,
)
from carro.core.logo_setup import logo_status

CONSOLE = Console()


def run_config_menu() -> None:
    """Numbered settings menu; loops until back."""
    ensure_dirs()
    while True:
        cfg = load_config()
        ro_keep = resolve_local_keep(cfg)
        photo_keep = resolve_local_photo_keep(cfg)
        info = disk_info()
        photos = cfg.get("photos") or {}

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[bold cyan]1[/]", "Shop name", str(cfg.get("shop_name") or ""))
        table.add_row(
            "[bold cyan]2[/]",
            "Server URL",
            str(cfg.get("server_url") or "(local only)"),
        )
        table.add_row(
            "[bold cyan]3[/]",
            "API token",
            "(set)" if cfg.get("token") else "(empty)",
        )
        table.add_row(
            "[bold cyan]4[/]",
            "Local RO keep",
            format_keep_setting(cfg.get("local_keep"), ro_keep),
        )
        table.add_row(
            "[bold cyan]5[/]",
            "Local photo keep",
            format_keep_setting(cfg.get("local_photo_keep"), photo_keep),
        )
        table.add_row(
            "[bold cyan]6[/]",
            "Shop logo (PDF)",
            logo_status(cfg)[0],
        )
        table.add_row(
            "[bold cyan]7[/]",
            "Photos directory",
            str(photos.get("dir") or ""),
        )
        table.add_row(
            "[bold cyan]8[/]",
            "Inbox directory",
            str(photos.get("inbox_dir") or ""),
        )
        table.add_row(
            "[bold cyan]9[/]",
            "Apply disk recommendation",
            recommend_pair(),
        )
        table.add_row(
            "[bold cyan]10[/]",
            "Textual theme",
            str(cfg.get("textual_theme") or "ansi-dark"),
        )
        table.add_row("[bold cyan]b[/]", "Back", "")

        CONSOLE.print()
        CONSOLE.print(
            Panel(
                table,
                title="Config",
                subtitle=(
                    f"{CONFIG_FILE} · disk {info['free_gb']:.0f} GB free "
                    f"of {info['total_gb']:.0f} GB on {info['path']}"
                ),
                border_style="cyan",
            )
        )
        choice = Prompt.ask("Setting", default="b").strip().lower()
        if choice in {"b", "q", "quit", "back", ""}:
            return
        try:
            if choice == "1":
                _edit_str(cfg, "shop_name", "Shop name")
            elif choice == "2":
                _edit_str(cfg, "server_url", "Server URL (empty = local only)")
            elif choice == "3":
                _edit_token(cfg)
            elif choice == "4":
                _edit_keep(cfg, key="local_keep")
            elif choice == "5":
                _edit_keep(cfg, key="local_photo_keep")
            elif choice == "6":
                from carro.core.logo_setup import run_logo_setup

                run_logo_setup()
            elif choice == "7":
                _edit_photos_path(cfg, "dir", "Photos directory")
            elif choice == "8":
                _edit_photos_path(cfg, "inbox_dir", "Inbox directory")
            elif choice == "9":
                _apply_disk_recommendation(cfg)
            elif choice == "10":
                _edit_str(
                    cfg,
                    "textual_theme",
                    "Textual theme (e.g. ansi-dark, textual-dark, nord)",
                )
            else:
                CONSOLE.print("[yellow]Unknown option[/]")
        except (ValueError, OSError) as exc:
            CONSOLE.print(f"[red]{exc}[/]")


def recommend_pair() -> str:
    from carro.config import recommend_local_keep, recommend_local_photo_keep

    rk = recommend_local_keep()
    pk = recommend_local_photo_keep(ro_keep=rk)
    return f"{rk} ROs / {pk} with photos"


def _save(cfg: dict) -> None:
    path = save_config(cfg)
    ensure_dirs(cfg)
    CONSOLE.print(f"[green]Saved[/] {path}")


def _edit_str(cfg: dict, key: str, label: str) -> None:
    cur = str(cfg.get(key) or "")
    val = Prompt.ask(label, default=cur).strip()
    cfg[key] = val
    _save(cfg)


def _edit_photos_path(cfg: dict, key: str, label: str) -> None:
    photos = cfg.setdefault("photos", {})
    cur = str(photos.get(key) or "")
    val = Prompt.ask(label, default=cur).strip()
    photos[key] = str(Path(val).expanduser()) if val else ""
    _save(cfg)


def _edit_token(cfg: dict) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[bold cyan]1[/]", "Keep current token")
    table.add_row("[bold cyan]2[/]", "Paste / type a new token")
    table.add_row("[bold cyan]3[/]", "Generate a new random token")
    CONSOLE.print(Panel(table, title="API token", border_style="magenta"))
    choice = Prompt.ask("Choice", choices=["1", "2", "3"], default="1")
    if choice == "1":
        return
    if choice == "2":
        cfg["token"] = Prompt.ask("Token").strip()
    else:
        cfg["token"] = secrets.token_urlsafe(24)
        CONSOLE.print(f"[dim]New token:[/] {cfg['token']}")
    _save(cfg)


def _edit_keep(cfg: dict, *, key: str) -> None:
    ro_keep = resolve_local_keep(cfg)
    if key == "local_keep":
        presets = keep_presets()
        title = "Local RO keep"
        help_txt = (
            "How many recent repair orders stay on this machine. "
            "Older ones are pruned on sync (server still has them if configured)."
        )
    else:
        presets = photo_keep_presets(ro_keep=ro_keep)
        title = "Local photo keep"
        help_txt = (
            "Of the ROs kept locally, how many newest also keep photo files on disk. "
            "Older kept ROs retain metadata; images can be re-fetched from the server."
        )

    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("#", style="cyan bold")
    table.add_column("Option")
    table.add_column("Detail", style="dim")
    for i, (label, value, detail) in enumerate(presets, start=1):
        shown = label if value is None else f"{label} = {value}"
        table.add_row(str(i), shown, detail)
    CONSOLE.print(Panel(table, title=title, subtitle=help_txt, border_style="magenta"))

    raw = Prompt.ask("Choice", default="1").strip()
    try:
        idx = int(raw)
    except ValueError:
        raise ValueError("Pick a numbered option") from None
    if idx < 1 or idx > len(presets):
        raise ValueError("Out of range")
    _label, value, _detail = presets[idx - 1]
    if value is None:
        n = int(Prompt.ask("Number of items to keep", default=str(ro_keep)).strip())
        if n < 0:
            raise ValueError("Must be >= 0")
        cfg[key] = n
    else:
        cfg[key] = value
    _save(cfg)
    if key == "local_keep":
        CONSOLE.print(
            f"[dim]Effective now:[/] {resolve_local_keep(cfg)} ROs"
        )
    else:
        CONSOLE.print(
            f"[dim]Effective now:[/] {resolve_local_photo_keep(cfg)} ROs with local photos"
        )


def _apply_disk_recommendation(cfg: dict) -> None:
    from carro.config import recommend_local_keep, recommend_local_photo_keep

    rk = recommend_local_keep()
    pk = recommend_local_photo_keep(ro_keep=rk)
    info = disk_info()
    CONSOLE.print(
        f"Disk: [cyan]{info['free_gb']:.1f} GB[/] free on {info['path']}\n"
        f"Recommend: [green]local_keep=auto[/] (→ {rk}), "
        f"[green]local_photo_keep=auto[/] (→ {pk})"
    )
    if not Confirm.ask("Set both to auto (follow this machine's disk)?", default=True):
        return
    cfg["local_keep"] = "auto"
    cfg["local_photo_keep"] = "auto"
    _save(cfg)


def print_config_summary() -> None:
    cfg = load_config()
    info = disk_info()
    CONSOLE.print(
        Panel(
            f"file: {CONFIG_FILE}\n"
            f"shop_name: {cfg.get('shop_name')}\n"
            f"server_url: {cfg.get('server_url') or '(local only)'}\n"
            f"token: {'(set)' if cfg.get('token') else '(empty)'}\n"
            f"local_keep: {format_keep_setting(cfg.get('local_keep'), resolve_local_keep(cfg))}\n"
            f"local_photo_keep: "
            f"{format_keep_setting(cfg.get('local_photo_keep'), resolve_local_photo_keep(cfg))}\n"
            f"logo: {logo_status(cfg)[0]}\n"
            f"photos.provider: {(cfg.get('photos') or {}).get('provider')}\n"
            f"photos.dir: {(cfg.get('photos') or {}).get('dir')}\n"
            f"photos.inbox_dir: {(cfg.get('photos') or {}).get('inbox_dir')}\n"
            f"disk: {info['free_gb']:.0f} GB free / {info['total_gb']:.0f} GB",
            title="carro config",
            border_style="cyan",
        )
    )
