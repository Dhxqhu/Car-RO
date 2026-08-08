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

from carro.config import ensure_dirs, load_config, save_config
from carro.core.config_menu import print_config_summary, run_config_menu
from carro.core.db import LocalStore
from carro.core.form import run_ro_form
from carro.core.history import HistoryResult, vehicle_fields_from, vehicle_history
from carro.core.history_form import run_history_form
from carro.core.models import RepairOrder
from carro.core.pdf import export_pdf
from carro.core.search_form import run_search_form
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
        "history": lambda: cmd_history(
            store,
            vin=getattr(args, "vin", "") or "",
            name=getattr(args, "name", "") or "",
            exclude_id=getattr(args, "exclude", "") or None,
        ),
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
    s.add_argument(
        "action",
        nargs="?",
        choices=["show", "set", "init", "menu"],
        default="menu",
    )
    s.add_argument("key", nargs="?")
    s.add_argument("value", nargs="?")
    s = sub.add_parser("photo", help="Attach photos")
    s.add_argument(
        "action",
        choices=["add", "ingest", "list", "phone", "shortcut"],
        nargs="?",
        default="list",
    )
    s.add_argument("paths", nargs="*")
    s.add_argument("--id", dest="ro_id")
    s.add_argument("--tag", default="intake", choices=["intake", "diag", "other"])
    s.add_argument("--note", default=None, help="Optional note stored with attached photo(s)")
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
    s = sub.add_parser(
        "history",
        help="Prior repair history by VIN (fallback: customer name)",
    )
    s.add_argument("--vin", default="", help="Vehicle VIN (preferred)")
    s.add_argument("--name", default="", help="Customer name fallback")
    s.add_argument(
        "--exclude",
        default="",
        help="RO id to omit (e.g. current job when viewing prior history)",
    )
    return p


def interactive_menu(store: LocalStore) -> None:
    current: str | None = None
    while True:
        CONSOLE.print()
        table = Table(title="Car-RO", show_header=False, box=None, padding=(0, 2))
        table.add_row("[bold cyan]1[/]", "New repair order (form)")
        table.add_row("[bold cyan]2[/]", "List / open in form")
        table.add_row("[bold cyan]3[/]", "Search ROs (form + server checkbox)")
        table.add_row("[bold cyan]4[/]", "Vehicle history (VIN / name)")
        table.add_row("[bold cyan]5[/]", "History for current vehicle")
        table.add_row("[bold cyan]6[/]", "Edit current (form)")
        table.add_row("[bold cyan]7[/]", "Pull OBD / Saved Codes into current")
        table.add_row("[bold cyan]8[/]", "Add photos (file / inbox / iPhone / Shortcut)")
        table.add_row("[bold cyan]9[/]", "Export customer PDF")
        table.add_row("[bold cyan]s[/]", "Sync to server + prune local cache")
        table.add_row("[bold cyan]c[/]", "Config (edit settings)")
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
                order = cmd_new(
                    store,
                    from_obd=Confirm.ask("Pull from OBD/Saved Codes?", default=True),
                )
                current = order.id
            elif choice == "2":
                current = cmd_list(store, pick=True) or current
            elif choice == "3":
                current = cmd_search_interactive(store) or current
            elif choice == "4":
                current = cmd_history(store) or current
            elif choice == "5":
                current = _history_for_current(store, _need(current)) or current
            elif choice == "6":
                current = _need(current)
                cmd_edit(store, current)
            elif choice == "7":
                current = _need(current)
                cmd_pull_obd(store, current)
            elif choice == "8":
                current = _need(current)
                _menu_photos(store, current)
            elif choice == "9":
                current = _need(current)
                cmd_pdf(store, current)
            elif choice == "s":
                cmd_sync(store)
            elif choice == "c":
                run_config_menu()
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
    if order.vin:
        _offer_history_after_vin(store, order.vin, exclude_id=order.id)
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


def _print_ro_table(
    orders: list[RepairOrder],
    title: str = "Search results",
    *,
    numbered: bool = False,
) -> None:
    if not orders:
        CONSOLE.print("[dim]No matches.[/]")
        return
    table = Table(title=title)
    if numbered:
        table.add_column("#", style="bold cyan", justify="right")
    table.add_column("Id", style="cyan")
    table.add_column("Customer")
    table.add_column("Vehicle")
    table.add_column("VIN")
    table.add_column("Status")
    table.add_column("Updated")
    for i, o in enumerate(orders, 1):
        row = [
            o.id,
            o.customer_label(),
            o.vehicle_label(),
            o.vin or "—",
            o.status,
            o.updated,
        ]
        if numbered:
            row.insert(0, str(i))
        table.add_row(*row)
    CONSOLE.print(table)


def _pick_ro_from_list(orders: list[RepairOrder]) -> str | None:
    """Pick an RO: number when ≤10 hits, otherwise id (partial OK)."""
    if not orders:
        return None
    if len(orders) == 1:
        if Confirm.ask(f"Open [bold]{orders[0].id}[/]?", default=True):
            return orders[0].id
        return None

    use_numbers = len(orders) <= 10
    if use_numbers:
        hint = f"1–{len(orders)} (or RO id)"
        default = "1"
    else:
        hint = "RO id (partial OK)"
        default = orders[0].id

    raw = Prompt.ask(f"Open which? [{hint}]", default=default).strip()
    if not raw:
        return None

    if use_numbers and raw.isdigit():
        n = int(raw)
        if 1 <= n <= len(orders):
            return orders[n - 1].id
        CONSOLE.print(f"[yellow]Pick 1–{len(orders)}.[/]")
        return None

    # Exact id
    for o in orders:
        if o.id.lower() == raw.lower():
            return o.id
    # Partial / suffix match among results
    matches = [o for o in orders if raw.lower() in o.id.lower()]
    if len(matches) == 1:
        return matches[0].id
    if len(matches) > 1:
        CONSOLE.print("[yellow]Ambiguous — matches:[/] " + ", ".join(m.id for m in matches))
        return None
    CONSOLE.print(f"[yellow]Not in results:[/] {raw}")
    return None


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
                local_ids = {o.id for o in local_hits}
                only_remote = [o for o in remote_orders if o.id not in local_ids]
                for o in remote_orders:
                    if o.id not in local_ids:
                        store.save(o)
                # Rebuild combined list preserving search order preference:
                # local hits first, then server-only
                local_hits = local_hits + only_remote
            except Exception as exc:
                CONSOLE.print(f"[yellow]Remote search failed:[/] {exc}")

    if not local_hits:
        CONSOLE.print("[dim]No matches.[/]")
        return None

    numbered = len(local_hits) <= 10
    _print_ro_table(
        local_hits,
        title=f"Matches ({len(local_hits)})"
        + (" — pick by #" if numbered else " — enter RO id"),
        numbered=numbered,
    )

    if open_hit:
        cmd_open(store, local_hits[0].id)
        return local_hits[0].id

    if not sys.stdin.isatty():
        return None

    rid = _pick_ro_from_list(local_hits)
    if rid:
        cmd_open(store, rid)
        return rid
    return None


def cmd_search_interactive(store: LocalStore) -> str | None:
    remote_default = bool(RemoteClient().enabled)
    q = run_search_form(default_remote=remote_default)
    if q.cancelled:
        CONSOLE.print("[dim]Search cancelled.[/]")
        return None
    if not any([q.query, q.make, q.model, q.year, q.name, q.vin, q.plate, q.status]):
        CONSOLE.print("[yellow]Enter at least one search field.[/]")
        return None
    return cmd_search(
        store,
        query=q.query,
        make=q.make,
        model=q.model,
        year=q.year,
        name=q.name,
        vin=q.vin,
        status=q.status,
        plate=q.plate,
        remote=q.remote,
    )


def cmd_history(
    store: LocalStore,
    *,
    vin: str = "",
    name: str = "",
    exclude_id: str | None = None,
) -> str | None:
    """VIN-first prior repair history; name fallback. Returns last opened/created RO id."""
    if not vin and not name and sys.stdin.isatty():
        q = run_history_form()
        if q.cancelled:
            CONSOLE.print("[dim]History cancelled.[/]")
            return None
        vin, name = q.vin, q.name
        if not vin and not name:
            CONSOLE.print("[yellow]Enter a VIN or customer name.[/]")
            return None

    result = vehicle_history(
        store, vin=vin, name=name, exclude_id=exclude_id or None
    )
    return _history_flow(store, result)


def _history_for_current(store: LocalStore, ro_id: str) -> str | None:
    order = store.get(ro_id)
    if not order:
        raise ValueError(f"RO not found: {ro_id}")
    vin = order.vin or ""
    name = ""
    if not vin.strip():
        name = f"{order.last_name} {order.first_name}".strip() or order.customer_label()
        CONSOLE.print(
            "[yellow]No VIN on this RO — falling back to customer name.[/]"
        )
    else:
        CONSOLE.print(f"[dim]History for VIN[/] {vin}")
    result = vehicle_history(
        store, vin=vin, name=name, exclude_id=order.id
    )
    return _history_flow(store, result)


def _offer_history_after_vin(
    store: LocalStore, vin: str, *, exclude_id: str | None = None
) -> str | None:
    if not vin or not sys.stdin.isatty():
        return None
    result = vehicle_history(store, vin=vin, exclude_id=exclude_id)
    if not result.orders:
        return None
    label = {
        "vin_exact": "exact VIN",
        "vin_partial": "partial VIN",
        "name": "name",
    }.get(result.matched_by, "match")
    if not Confirm.ask(
        f"[cyan]{len(result.orders)}[/] prior RO(s) for this vehicle ({label}) — view?",
        default=True,
    ):
        return None
    return _history_flow(store, result)


def _history_flow(store: LocalStore, result: HistoryResult) -> str | None:
    if not result.orders:
        how = ""
        if result.vin_query:
            how = f" VIN {result.vin_query}"
        elif result.name_query:
            how = f" name “{result.name_query}”"
        CONSOLE.print(f"[dim]No prior repair history{how}.[/]")
        return None

    title = f"Vehicle history ({len(result.orders)})"
    if result.matched_by == "vin_exact":
        title += f" — exact VIN {result.vin_query}"
    elif result.matched_by == "vin_partial":
        title += f" — partial VIN {result.vin_query}"
    elif result.matched_by == "name":
        title += f" — name “{result.name_query}”"

    _print_history_table(result.orders, title=title)
    if not sys.stdin.isatty():
        return None

    action = Prompt.ask(
        "Action",
        choices=["text", "pdf", "pdf-lite", "pick", "back"],
        default="text",
    )
    if action == "back":
        return None
    if action == "text":
        return _history_text_pack(result)
    if action in {"pdf", "pdf-lite"}:
        return _history_pdf_pack(result, include_photos=(action == "pdf"))
    # pick one RO
    rid = _pick_ro_from_list(result.orders)
    if not rid:
        return None
    picked = next((o for o in result.orders if o.id == rid), store.get(rid))
    if not picked:
        return None
    return _history_actions(store, picked)


def _history_text_pack(result: HistoryResult) -> str | None:
    from carro.core.history_pack import open_text_pack, write_text_pack

    path = write_text_pack(
        result.orders,
        vin=result.vin_query,
        name=result.name_query,
    )
    CONSOLE.print(f"[green]Diag text pack[/] → {path}")
    if Confirm.ask("Open in pager?", default=True):
        open_text_pack(path)
    return None


def _history_pdf_pack(result: HistoryResult, *, include_photos: bool) -> str | None:
    from carro.core.history_pack import (
        HISTORY_PDF_PAGE_WARN,
        estimate_pack_pages,
        write_pdf_pack,
    )

    est = estimate_pack_pages(result.orders, include_photos=include_photos)
    mode = "with photos" if include_photos else "text + OBD only"
    if est > HISTORY_PDF_PAGE_WARN:
        CONSOLE.print(
            f"[yellow]This pack looks like ~{est:.0f} pages[/] ({mode}; "
            f"warn at {HISTORY_PDF_PAGE_WARN})."
        )
        if not Confirm.ask("Write anyway?", default=False):
            CONSOLE.print(
                "[dim]Skipped. Try [bold]pdf-lite[/] or [bold]text[/] for a smaller pack.[/]"
            )
            return None
    path = write_pdf_pack(
        result.orders,
        vin=result.vin_query,
        name=result.name_query,
        include_photos=include_photos,
    )
    CONSOLE.print(f"[green]History PDF pack[/] → {path} (~{est:.0f} pages est., {mode})")
    if Confirm.ask("Open in PDF viewer?", default=True):
        _open_pdf(path)
    return None


def _print_history_table(orders: list[RepairOrder], *, title: str) -> None:
    numbered = len(orders) <= 10
    table = Table(title=title)
    if numbered:
        table.add_column("#", style="bold cyan", justify="right")
    table.add_column("Id", style="cyan")
    table.add_column("Customer")
    table.add_column("Vehicle")
    table.add_column("VIN")
    table.add_column("Status")
    table.add_column("Updated")
    table.add_column("Complaint")
    for i, o in enumerate(orders, 1):
        complaint = (o.complaint or "").replace("\n", " ").strip()
        if len(complaint) > 48:
            complaint = complaint[:45] + "…"
        row = [
            o.id,
            o.customer_label(),
            o.vehicle_label(),
            o.vin or "—",
            o.status,
            o.updated,
            complaint or "—",
        ]
        if numbered:
            row.insert(0, str(i))
        table.add_row(*row)
    CONSOLE.print(table)


def _history_actions(store: LocalStore, prior: RepairOrder) -> str | None:
    CONSOLE.print(
        Panel(
            f"[bold]{prior.id}[/] · {prior.customer_label()} · {prior.vehicle_label()}\n"
            f"Complaint: {(prior.complaint or '—')[:120]}",
            title="Prior RO",
            border_style="magenta",
        )
    )
    action = Prompt.ask(
        "Action",
        choices=["open", "new", "back"],
        default="open",
    )
    if action == "back":
        return None
    if action == "open":
        cmd_open(store, prior.id)
        return prior.id
    # new RO from vehicle
    fields = vehicle_fields_from(prior)
    order = store.create(**fields)
    CONSOLE.print(
        f"[green]New RO[/] {order.id} with vehicle from {prior.id} "
        f"({order.vehicle_label() or order.vin})"
    )
    saved = _open_ro_form(store, order)
    return (saved or order).id


def cmd_list(store: LocalStore, pick: bool = False) -> str | None:
    orders = store.list_orders()
    if not orders:
        CONSOLE.print("[dim]No local repair orders yet.[/]")
        return None
    numbered = pick and len(orders) <= 10
    _print_ro_table(
        orders,
        title="Repair orders" + (" — pick by #" if numbered else ""),
        numbered=numbered,
    )
    if not pick:
        return None
    rid = _pick_ro_from_list(orders)
    if rid:
        cmd_open(store, rid)
        return rid
    return None


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
    if order.vin:
        _offer_history_after_vin(store, order.vin, exclude_id=order.id)
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
    if sys.stdin.isatty() and Confirm.ask("Open in PDF viewer?", default=True):
        _open_pdf(path)


def _open_pdf(path: Path) -> None:
    import shutil
    import subprocess

    viewers = ("zathura", "papers", "xdg-open")
    for name in viewers:
        exe = shutil.which(name)
        if not exe:
            continue
        try:
            subprocess.Popen(
                [exe, str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            CONSOLE.print(f"[dim]Opened with {name}[/]")
            return
        except OSError:
            continue
    CONSOLE.print("[yellow]No PDF viewer found (install zathura).[/]")


def cmd_sync(store: LocalStore) -> None:
    from carro.config import resolve_local_keep, resolve_local_photo_keep

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
    cfg = load_config()
    keep_n = resolve_local_keep(cfg)
    photo_n = resolve_local_photo_keep(cfg)
    if removed:
        CONSOLE.print(f"[dim]Pruned local cache:[/] {', '.join(removed)}")
    else:
        CONSOLE.print(
            f"[dim]Local cache within limits "
            f"(keep {keep_n} ROs, {photo_n} with photos).[/]"
        )


def cmd_config(args: argparse.Namespace) -> None:
    cfg = load_config()
    action = args.action or "menu"
    if action == "menu":
        run_config_menu()
        return
    if action == "init":
        cfg["token"] = cfg.get("token") or secrets.token_urlsafe(24)
        path = save_config(cfg)
        ensure_dirs(cfg)
        CONSOLE.print(f"[green]Wrote[/] {path}")
        return
    if action == "set":
        if not args.key:
            raise ValueError("Usage: carro config set <key> <value>")
        key, value = args.key, args.value if args.value is not None else ""
        if key.startswith("photos."):
            cfg.setdefault("photos", {})[key.split(".", 1)[1]] = value
        elif key in {"local_keep", "local_photo_keep"}:
            v = str(value).strip().lower()
            if v in {"auto", "dynamic", "match"}:
                cfg[key] = "match" if v == "match" else "auto"
            else:
                cfg[key] = int(value)
        else:
            cfg[key] = value
        save_config(cfg)
        CONSOLE.print(f"[green]Set[/] {key}")
        return
    print_config_summary()


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
            note = (p.get("notes") or p.get("note") or "").strip()
            line = f"  {p.get('tag')}: {p.get('filename')} ({p.get('volume')})"
            if note:
                line += f" — {note}"
            CONSOLE.print(line)
        return

    if args.action == "phone":
        _phone_upload_flow(store, order, tag=args.tag, mode="phone")
        return
    if args.action == "shortcut":
        _phone_upload_flow(store, order, tag=args.tag, mode="shortcut")
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
    if not found:
        CONSOLE.print("[yellow]No images found.[/]")
        return
    notes_by_path = _collect_photo_notes(found, preset=getattr(args, "note", None))
    order = attach_photos(
        store,
        order,
        found,
        tag=args.tag,
        notes_by_path=notes_by_path,
    )
    if args.action == "ingest":
        for p in found:
            try:
                p.unlink()
            except OSError:
                pass
    CONSOLE.print(f"[green]Attached[/] {len(found)} photo(s) → {order.id}")
    _maybe_push(order)


def _collect_photo_notes(
    paths: list[Path], *, preset: str | None = None
) -> dict[str, str]:
    """Optional notes at attach time. Blank skips."""
    if preset is not None:
        note = preset.strip()
        return {str(p): note for p in paths} if note else {}
    if len(paths) == 1:
        note = Prompt.ask(
            f"Note for {paths[0].name} (optional)",
            default="",
        ).strip()
        return {str(paths[0]): note} if note else {}
    shared = Prompt.ask(
        "Note for all photos (optional; leave blank to note each)",
        default="",
    ).strip()
    if shared:
        return {str(p): shared for p in paths}
    out: dict[str, str] = {}
    for p in paths:
        note = Prompt.ask(f"Note for {p.name} (optional)", default="").strip()
        if note:
            out[str(p)] = note
    return out


def _phone_upload_flow(
    store: LocalStore,
    order: RepairOrder,
    *,
    tag: str,
    mode: str = "phone",
) -> None:
    from carro.photos.phone_upload import start_phone_upload, start_shortcut_upload

    remote = RemoteClient()
    if not remote.enabled:
        raise RuntimeError(
            "Configure server_url (Tailscale) first: carro config show"
        )
    # Ensure RO exists on server before phone uploads
    try:
        remote.upsert_ro(order)
    except Exception as exc:
        raise RuntimeError(f"Could not sync RO to server before phone upload: {exc}") from exc

    def refresh() -> None:
        from carro.storage.photos import ensure_local_photos

        try:
            remote_data = remote.get_ro(order.id)
            updated = RepairOrder.from_dict(remote_data)
            local = store.get(order.id) or order
            seen = {p.get("id") for p in local.photos}
            for p in updated.photos:
                if p.get("id") not in seen:
                    local.photos.append(p)
            # Prefer full server photo list if richer
            if len(updated.photos) > len(local.photos):
                local.photos = list(updated.photos)
            store.save(local)
            paths = ensure_local_photos(local)
            CONSOLE.print(
                f"[green]RO now has {len(local.photos)} photo(s)[/] "
                f"· {len(paths)} file(s) in ~/Documents/Car-RO/photos/{local.id}/"
            )
        except Exception as exc:
            CONSOLE.print(f"[yellow]Could not refresh RO:[/] {exc}")

    if mode == "shortcut":
        start_shortcut_upload(order.id, tag=tag, on_done=refresh)
    else:
        start_phone_upload(order.id, tag=tag, on_done=refresh)


def _menu_photos(store: LocalStore, ro_id: str) -> None:
    tag = Prompt.ask("Tag", choices=["intake", "diag", "other"], default="intake")
    mode = Prompt.ask(
        "Source",
        choices=["shortcut", "phone", "add", "ingest"],
        default="shortcut",
    )
    args = argparse.Namespace(action=mode, paths=[], ro_id=ro_id, tag=tag, note=None)
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
