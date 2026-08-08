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
        "search": lambda: cmd_search(
            store,
            query=" ".join(args.query) if getattr(args, "query", None) else "",
            make=getattr(args, "make", "") or "",
            model=getattr(args, "model", "") or "",
            year=getattr(args, "year", "") or "",
            name=getattr(args, "name", "") or "",
            vin=getattr(args, "vin", "") or "",
            status=getattr(args, "status", "") or "",
            plate=getattr(args, "plate", "") or "",
            remote=getattr(args, "remote", False),
            open_hit=getattr(args, "open", False),
        ),
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
    s = sub.add_parser("search", help="Search ROs by make/model/year/name/VIN/…")
    s.add_argument("query", nargs="*", help="Free-text query")
    s.add_argument("--make", default="")
    s.add_argument("--model", default="")
    s.add_argument("--year", default="")
    s.add_argument("--name", default="", help="Customer first/last name")
    s.add_argument("--vin", default="")
    s.add_argument("--plate", default="")
    s.add_argument("--status", default="", choices=["", "open", "in_progress", "done"])
    s.add_argument("--remote", action="store_true", help="Also search server store")
    s.add_argument("--open", action="store_true", help="Open first hit in form")
    return p


def interactive_menu(store: LocalStore) -> None:
    current: str | None = None
    while True:
        CONSOLE.print()
        table = Table(title="Car-RO", show_header=False, box=None, padding=(0, 2))
        table.add_row("[bold cyan]1[/]", "New repair order (form)")
        table.add_row("[bold cyan]2[/]", "List / open in form")
        table.add_row("[bold cyan]3[/]", "Search ROs (make/model/year/name/…)")
        table.add_row("[bold cyan]4[/]", "Edit current (form)")
        table.add_row("[bold cyan]5[/]", "Pull OBD / Saved Codes into current")
        table.add_row("[bold cyan]6[/]", "Add photos (local / inbox)")
        table.add_row("[bold cyan]7[/]", "Export customer PDF")
        table.add_row("[bold cyan]8[/]", "Sync to server + prune local cache")
        table.add_row("[bold cyan]9[/]", "Config")
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
                current = cmd_search_interactive(store) or current
            elif choice == "4":
                current = _need(current)
                cmd_edit(store, current)
            elif choice == "5":
                current = _need(current)
                cmd_pull_obd(store, current)
            elif choice == "6":
                current = _need(current)
                _menu_photos(store, current)
            elif choice == "7":
                current = _need(current)
                cmd_pdf(store, current)
            elif choice == "8":
                cmd_sync(store)
            elif choice == "9":
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


def _print_ro_table(orders: list[RepairOrder], title: str = "Search results") -> None:
    if not orders:
        CONSOLE.print("[dim]No matches.[/]")
        return
    table = Table(title=title)
    table.add_column("Id", style="cyan")
    table.add_column("Customer")
    table.add_column("Vehicle")
    table.add_column("VIN")
    table.add_column("Status")
    table.add_column("Updated")
    for o in orders:
        table.add_row(
            o.id,
            o.customer_label(),
            o.vehicle_label(),
            o.vin or "—",
            o.status,
            o.updated,
        )
    CONSOLE.print(table)


def cmd_search(
    store: LocalStore,
    *,
    query: str = "",
    make: str = "",
    model: str = "",
    year: str = "",
    name: str = "",
    vin: str = "",
    status: str = "",
    plate: str = "",
    remote: bool = False,
    open_hit: bool = False,
) -> str | None:
    local_hits = store.search(
        query,
        make=make,
        model=model,
        year=year,
        name=name,
        vin=vin,
        status=status,
        plate=plate,
    )
    _print_ro_table(local_hits, title=f"Local matches ({len(local_hits)})")

    if remote:
        client = RemoteClient()
        if not client.enabled:
            CONSOLE.print("[yellow]No server_url — skip remote search.[/]")
        else:
            try:
                raw = client.search_ros(
                    query,
                    make=make,
                    model=model,
                    year=year,
                    name=name,
                    vin=vin,
                    status=status,
                    plate=plate,
                )
                remote_orders = [RepairOrder.from_dict(r) for r in raw]
                # Dedupe against local ids for display
                local_ids = {o.id for o in local_hits}
                only_remote = [o for o in remote_orders if o.id not in local_ids]
                _print_ro_table(
                    only_remote,
                    title=f"Server-only matches ({len(only_remote)})",
                )
                # Merge remote into local cache if opening
                for o in remote_orders:
                    if o.id not in local_ids:
                        store.save(o)
                local_hits = store.search(
                    query,
                    make=make,
                    model=model,
                    year=year,
                    name=name,
                    vin=vin,
                    status=status,
                    plate=plate,
                )
            except Exception as exc:
                CONSOLE.print(f"[yellow]Remote search failed:[/] {exc}")

    if not local_hits:
        return None
    if open_hit:
        cmd_open(store, local_hits[0].id)
        return local_hits[0].id
    if sys.stdin.isatty() and Confirm.ask("Open one in the form?", default=True):
        rid = Prompt.ask("RO id", default=local_hits[0].id).strip()
        if rid:
            cmd_open(store, rid)
            return rid
    return None


def cmd_search_interactive(store: LocalStore) -> str | None:
    CONSOLE.print("[cyan]Search[/] — free text and/or filters (Enter skips a filter)")
    query = Prompt.ask("Free text (name, make, VIN, complaint…)", default="").strip()
    make = Prompt.ask("Make", default="").strip()
    model = Prompt.ask("Model", default="").strip()
    year = Prompt.ask("Year", default="").strip()
    name = Prompt.ask("Customer name", default="").strip()
    vin = Prompt.ask("VIN", default="").strip()
    remote = Confirm.ask("Include server store?", default=bool(RemoteClient().enabled))
    return cmd_search(
        store,
        query=query,
        make=make,
        model=model,
        year=year,
        name=name,
        vin=vin,
        remote=remote,
    )


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
