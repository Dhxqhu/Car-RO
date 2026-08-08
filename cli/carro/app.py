#!/usr/bin/env python3
"""Car-RO CLI — technician repair orders."""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

# Allow running from a git checkout without install
_ROOT = Path(__file__).resolve().parents[2]
_CLI = _ROOT / "cli"
if _CLI.is_dir() and str(_CLI) not in sys.path:
    sys.path.insert(0, str(_CLI))
_SERVER = _ROOT / "server"
if _SERVER.is_dir() and str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from carro.config import CONFIG_FILE, ensure_dirs, load_config, save_config
from carro.core.db import LocalStore
from carro.core.form import run_ro_form
from carro.core.models import RepairOrder
from carro.core.pdf import export_pdf
from carro.obd.provider import pull_vehicle_fields
from carro.photos.base import get_provider
from carro.photos.providers.local import LocalPhotoIngress
from carro.storage.photos import attach_photos
from carro.storage.remote import RemoteClient

CONSOLE = Console()


def main(argv: list[str] | None = None) -> None:
    ensure_dirs()
    parser = build_parser()
    args = parser.parse_args(argv)
    store = LocalStore()
    if not args.cmd or args.cmd == "menu":
        interactive_menu(store)
        return
    handlers = {
        "new": lambda: cmd_new(store, from_obd=args.from_obd),
        "list": lambda: cmd_list(store),
        "open": lambda: cmd_open(store, args.id),
        "edit": lambda: cmd_edit(store, args.id),
        "pull-obd": lambda: cmd_pull_obd(store, args.id),
        "pdf": lambda: cmd_pdf(store, args.id),
        "sync": lambda: cmd_sync(store),
        "config": lambda: cmd_config(args),
        "photo": lambda: cmd_photo(store, args),
    }
    fn = handlers.get(args.cmd)
    if not fn:
        parser.print_help()
        sys.exit(1)
    try:
        fn()
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        CONSOLE.print(f"[red]{exc}[/]")
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="carro", description="Car repair order CLI")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("menu", help="Interactive menu (default)")
    s = sub.add_parser("new", help="Create repair order")
    s.add_argument("--from-obd", action="store_true")
    sub.add_parser("list", help="List local repair orders")
    s = sub.add_parser("open", help="Show one RO")
    s.add_argument("id")
    s = sub.add_parser("edit", help="Edit fields")
    s.add_argument("id", nargs="?")
    s = sub.add_parser("pull-obd", help="Autofill from obdscan / Saved Codes")
    s.add_argument("id", nargs="?")
    s = sub.add_parser("pdf", help="Export customer PDF")
    s.add_argument("id", nargs="?")
    sub.add_parser("sync", help="Push local ROs to server + prune cache")
    s = sub.add_parser("config", help="Show or set config")
    s.add_argument("action", nargs="?", choices=["show", "set", "init"], default="show")
    s.add_argument("key", nargs="?")
    s.add_argument("value", nargs="?")
    s = sub.add_parser("photo", help="Attach photos")
    s.add_argument("action", choices=["add", "ingest", "list"], nargs="?", default="list")
    s.add_argument("paths", nargs="*")
    s.add_argument("--id", dest="ro_id")
    s.add_argument("--tag", default="intake", choices=["intake", "diag", "other"])
    return p


def interactive_menu(store: LocalStore) -> None:
    current: str | None = None
    while True:
        CONSOLE.print()
        table = Table(title="Car-RO", show_header=False, box=None, padding=(0, 2))
        table.add_row("[bold cyan]1[/]", "New repair order (form)")
        table.add_row("[bold cyan]2[/]", "List / open in form")
        table.add_row("[bold cyan]3[/]", "Edit current (form)")
        table.add_row("[bold cyan]4[/]", "Pull OBD / Saved Codes into current")
        table.add_row("[bold cyan]5[/]", "Add photos (local / inbox)")
        table.add_row("[bold cyan]6[/]", "Export customer PDF")
        table.add_row("[bold cyan]7[/]", "Sync to server + prune local cache")
        table.add_row("[bold cyan]8[/]", "Config")
        table.add_row("[bold cyan]q[/]", "Quit")
        CONSOLE.print(Panel(table, border_style="cyan"))
        if current:
            order = store.get(current)
            if order:
                CONSOLE.print(
                    f"[magenta]Current:[/] {order.id} · {order.customer_label()} · "
                    f"{order.vehicle_label()}"
                )
        choice = Prompt.ask("Select", default="2").strip().lower()
        if choice in {"q", "quit", "b"}:
            return
        try:
            if choice == "1":
                order = cmd_new(store, from_obd=Confirm.ask("Pull from OBD/Saved Codes?", default=True))
                current = order.id
            elif choice == "2":
                current = cmd_list(store, pick=True) or current
            elif choice == "3":
                current = _need(current)
                cmd_edit(store, current)
            elif choice == "4":
                current = _need(current)
                cmd_pull_obd(store, current)
            elif choice == "5":
                current = _need(current)
                _menu_photos(store, current)
            elif choice == "6":
                current = _need(current)
                cmd_pdf(store, current)
            elif choice == "7":
                cmd_sync(store)
            elif choice == "8":
                cmd_config(argparse.Namespace(action="show", key=None, value=None))
            else:
                CONSOLE.print("[yellow]Unknown option[/]")
        except (RuntimeError, ValueError) as exc:
            CONSOLE.print(f"[red]{exc}[/]")


def _need(current: str | None) -> str:
    if current:
        return current
    rid = Prompt.ask("RO id").strip()
    if not rid:
        raise ValueError("No RO selected")
    return rid


def _apply_obd_to_order(order: RepairOrder, *, ask: bool = False) -> RepairOrder:
    raw = pull_vehicle_fields()
    if not raw:
        raise RuntimeError("Nothing found from obdscan / Saved Codes")
    mapped = _map_obd(raw)
    for key, val in mapped.items():
        if not val:
            continue
        cur = getattr(order, key, "")
        if ask and cur and cur != val:
            # Non-interactive inside TUI — prefer incoming OBD values
            pass
        setattr(order, key, val)
    return order


def _open_ro_form(store: LocalStore, order: RepairOrder) -> RepairOrder | None:
    """Full-screen navigable form; save persists + syncs."""

    def on_pull(o: RepairOrder) -> RepairOrder:
        return _apply_obd_to_order(o)

    result = run_ro_form(order, on_pull_obd=on_pull)
    if result is None:
        CONSOLE.print("[dim]Form closed without saving.[/]")
        return None
    store.save(result)
    CONSOLE.print(f"[green]Saved[/] {result.id}")
    _maybe_push(result)
    return result


def cmd_new(store: LocalStore, from_obd: bool = False) -> RepairOrder:
    fields: dict = {}
    if from_obd:
        try:
            fields.update(_map_obd(pull_vehicle_fields()))
            CONSOLE.print("[dim]Prefilled from OBD / Saved Codes — edit in the form.[/]")
        except Exception:
            CONSOLE.print("[yellow]OBD autofill unavailable — blank form.[/]")
    order = store.create(**{k: v for k, v in fields.items() if v})
    CONSOLE.print(f"[cyan]Opening form[/] {order.id}")
    saved = _open_ro_form(store, order)
    return saved or order


def _map_obd(raw: dict) -> dict:
    return {
        "vin": raw.get("vin", ""),
        "year": raw.get("year", ""),
        "make": raw.get("make", ""),
        "obd_snapshot": raw.get("obd_snapshot", ""),
    }


def cmd_list(store: LocalStore, pick: bool = False) -> str | None:
    orders = store.list_orders()
    if not orders:
        CONSOLE.print("[dim]No local repair orders yet.[/]")
        return None
    table = Table(title="Repair orders")
    table.add_column("Id", style="cyan")
    table.add_column("Customer")
    table.add_column("Vehicle")
    table.add_column("Status")
    table.add_column("Updated")
    for o in orders:
        table.add_row(o.id, o.customer_label(), o.vehicle_label(), o.status, o.updated)
    CONSOLE.print(table)
    if not pick:
        return None
    rid = Prompt.ask("Open id (Enter=cancel)", default="").strip()
    if not rid:
        return None
    cmd_open(store, rid)
    return rid


def cmd_open(store: LocalStore, ro_id: str) -> None:
    order = store.get(ro_id)
    if not order:
        raise ValueError(f"RO not found: {ro_id}")
    _open_ro_form(store, order)


def cmd_edit(store: LocalStore, ro_id: str | None) -> None:
    if not ro_id:
        ro_id = Prompt.ask("RO id").strip()
    order = store.get(ro_id)
    if not order:
        raise ValueError(f"RO not found: {ro_id}")
    _open_ro_form(store, order)


def cmd_pull_obd(store: LocalStore, ro_id: str | None) -> None:
    if not ro_id:
        ro_id = Prompt.ask("RO id").strip()
    order = store.get(ro_id)
    if not order:
        raise ValueError(f"RO not found: {ro_id}")
    CONSOLE.print("[cyan]Pulling vehicle info…[/]")
    try:
        order = _apply_obd_to_order(order, ask=True)
    except RuntimeError as exc:
        CONSOLE.print(f"[yellow]{exc}[/]")
        return
    store.save(order)
    CONSOLE.print(f"[green]Updated[/] {order.id} from OBD sources")
    _maybe_push(order)
    if Confirm.ask("Open form to review?", default=True):
        _open_ro_form(store, order)


def cmd_pdf(store: LocalStore, ro_id: str | None) -> None:
    if not ro_id:
        ro_id = Prompt.ask("RO id").strip()
    order = store.get(ro_id)
    if not order:
        raise ValueError(f"RO not found: {ro_id}")
    path = export_pdf(order)
    CONSOLE.print(f"[green]PDF[/] → {path}")


def cmd_sync(store: LocalStore) -> None:
    remote = RemoteClient()
    if not remote.enabled:
        CONSOLE.print("[yellow]No server_url configured — local only.[/]")
        CONSOLE.print("[dim]Set with: carro config set server_url http://YOUR_SERVER:8787[/]")
    else:
        try:
            health = remote.health()
            CONSOLE.print(f"[green]Server OK[/] default volume={health.get('default_volume')}")
        except Exception as exc:
            CONSOLE.print(f"[red]Server unreachable:[/] {exc}")
            return
        for order in store.list_orders():
            remote.upsert_ro(order)
            CONSOLE.print(f"  pushed {order.id}")
    removed = store.prune()
    if removed:
        CONSOLE.print(f"[dim]Pruned local cache:[/] {', '.join(removed)}")
    else:
        CONSOLE.print("[dim]Local cache within local_keep limit.[/]")


def cmd_config(args: argparse.Namespace) -> None:
    cfg = load_config()
    if args.action == "init":
        cfg["token"] = cfg.get("token") or secrets.token_urlsafe(24)
        path = save_config(cfg)
        ensure_dirs(cfg)
        CONSOLE.print(f"[green]Wrote[/] {path}")
        return
    if args.action == "set":
        if not args.key:
            raise ValueError("Usage: carro config set <key> <value>")
        key, value = args.key, args.value if args.value is not None else ""
        if key.startswith("photos."):
            cfg.setdefault("photos", {})[key.split(".", 1)[1]] = value
        elif key in {"local_keep", "local_photo_keep"}:
            cfg[key] = int(value)
        else:
            cfg[key] = value
        save_config(cfg)
        CONSOLE.print(f"[green]Set[/] {key}")
        return
    CONSOLE.print(Panel(
        f"file: {CONFIG_FILE}\n"
        f"shop_name: {cfg.get('shop_name')}\n"
        f"server_url: {cfg.get('server_url') or '(local only)'}\n"
        f"token: {'(set)' if cfg.get('token') else '(empty)'}\n"
        f"local_keep: {cfg.get('local_keep')}\n"
        f"photos.provider: {(cfg.get('photos') or {}).get('provider')}\n"
        f"photos.inbox_dir: {(cfg.get('photos') or {}).get('inbox_dir')}",
        title="carro config",
        border_style="cyan",
    ))


def cmd_photo(store: LocalStore, args: argparse.Namespace) -> None:
    ro_id = args.ro_id or Prompt.ask("RO id").strip()
    order = store.get(ro_id)
    if not order:
        raise ValueError(f"RO not found: {ro_id}")
    if args.action == "list":
        if not order.photos:
            CONSOLE.print("[dim]No photos.[/]")
            return
        for p in order.photos:
            CONSOLE.print(f"  {p.get('tag')}: {p.get('filename')} ({p.get('volume')})")
        return
    cfg = load_config()
    provider = get_provider((cfg.get("photos") or {}).get("provider", "local"), cfg)
    if not isinstance(provider, LocalPhotoIngress):
        provider.start(ro_id, args.tag)
        return
    provider.start(ro_id, args.tag)
    if args.action == "add":
        paths = [Path(p) for p in args.paths] if args.paths else []
        if not paths:
            raw = Prompt.ask("Image path").strip()
            if raw:
                paths = [Path(raw)]
        found = provider.add_paths(paths)
    else:
        found = provider.ingest_inbox()
        # move ingested out of inbox after copy
    if not found:
        CONSOLE.print("[yellow]No images found.[/]")
        return
    order = attach_photos(store, order, found, tag=args.tag)
    if args.action == "ingest":
        for p in found:
            try:
                p.unlink()
            except OSError:
                pass
    CONSOLE.print(f"[green]Attached[/] {len(found)} photo(s) → {order.id}")
    _maybe_push(order)


def _menu_photos(store: LocalStore, ro_id: str) -> None:
    tag = Prompt.ask("Tag", choices=["intake", "diag", "other"], default="intake")
    mode = Prompt.ask("Source", choices=["add", "ingest"], default="add")
    args = argparse.Namespace(action=mode, paths=[], ro_id=ro_id, tag=tag)
    if mode == "add":
        raw = Prompt.ask("Image path(s), space-separated").strip()
        args.paths = raw.split() if raw else []
    cmd_photo(store, args)


def _maybe_push(order: RepairOrder) -> None:
    remote = RemoteClient()
    if not remote.enabled:
        return
    try:
        remote.upsert_ro(order)
        CONSOLE.print(f"[dim]Synced to server[/]")
    except Exception as exc:
        CONSOLE.print(f"[yellow]Server sync skipped:[/] {exc}")


if __name__ == "__main__":
    main()
