"""CLI parts order sheet — compiled from local RO work-item parts."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from carro.core.db import LocalStore
from carro.core.work_items import (
    PART_STATUSES,
    collect_parts_sheet,
    part_status_label,
    set_part_status,
)

CONSOLE = Console()


def run_parts_sheet_menu(store: LocalStore) -> None:
    """Interactive shop parts sheet (filter + status transitions)."""
    status_filter = ""
    mfr_filter = ""
    pn_filter = ""
    ro_filter = ""
    include_received = False
    while True:
        CONSOLE.clear()
        rows = collect_parts_sheet(
            store.list_orders(),
            status=status_filter,
            manufacturer=mfr_filter,
            part_number=pn_filter,
            ro_id=ro_filter,
            include_received=include_received,
        )
        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("#", style="cyan bold")
        table.add_column("RO")
        table.add_column("Item")
        table.add_column("Status")
        table.add_column("Brand")
        table.add_column("Mfr")
        table.add_column("PN")
        table.add_column("Description")
        table.add_column("Vehicle", style="dim")
        for i, r in enumerate(rows, 1):
            table.add_row(
                str(i),
                str(r.get("ro_id") or ""),
                str(r.get("work_item_id") or ""),
                part_status_label(r.get("status")),
                str(r.get("brand") or "")[:14] or "—",
                str(r.get("manufacturer") or "")[:16],
                str(r.get("part_number") or "")[:18] or "—",
                str(r.get("description") or "")[:36],
                str(r.get("vehicle") or "")[:24],
            )
        filters = []
        if status_filter:
            filters.append(f"status={status_filter}")
        if mfr_filter:
            filters.append(f"mfr~{mfr_filter}")
        if pn_filter:
            filters.append(f"pn~{pn_filter}")
        if ro_filter:
            filters.append(f"ro={ro_filter}")
        if include_received:
            filters.append("include received")
        subtitle = " · ".join(filters) if filters else "open requests + ordered"
        CONSOLE.print(
            Panel(
                table if rows else "(no matching parts)",
                title=f"Parts order sheet ({len(rows)})",
                subtitle=subtitle,
                border_style="cyan",
            )
        )
        menu = Table(show_header=False, box=None, padding=(0, 2))
        menu.add_row("[bold cyan]1[/]", "Set status on a row (ordered / received / wrong)")
        menu.add_row("[bold cyan]2[/]", "Filter by status")
        menu.add_row("[bold cyan]3[/]", "Filter by manufacturer")
        menu.add_row("[bold cyan]4[/]", "Filter by part number")
        menu.add_row("[bold cyan]5[/]", "Filter by RO id")
        menu.add_row(
            "[bold cyan]6[/]",
            f"Toggle include received (now {'on' if include_received else 'off'})",
        )
        menu.add_row("[bold cyan]7[/]", "Clear filters")
        menu.add_row("[bold cyan]b[/]", "Back")
        CONSOLE.print(Panel(menu, border_style="magenta"))
        choice = Prompt.ask("Select", default="b").strip().lower()
        if choice in {"b", "q", "quit", "back", ""}:
            return
        try:
            if choice == "1":
                _set_row_status(store, rows)
            elif choice == "2":
                status_filter = _pick_status_filter(status_filter)
            elif choice == "3":
                mfr_filter = Prompt.ask("Manufacturer contains", default=mfr_filter).strip()
            elif choice == "4":
                pn_filter = Prompt.ask("Part number contains", default=pn_filter).strip()
            elif choice == "5":
                ro_filter = Prompt.ask("RO id (exact)", default=ro_filter).strip()
            elif choice == "6":
                include_received = not include_received
            elif choice == "7":
                status_filter = ""
                mfr_filter = ""
                pn_filter = ""
                ro_filter = ""
                include_received = False
            else:
                CONSOLE.print("[yellow]Unknown option[/]")
        except (ValueError, RuntimeError) as exc:
            CONSOLE.print(f"[red]{exc}[/]")
        Prompt.ask("[dim]Press Enter[/]", default="")


def _pick_status_filter(current: str) -> str:
    CONSOLE.print("Statuses: " + ", ".join(PART_STATUSES) + " (blank = all open)")
    raw = Prompt.ask("Status filter", default=current).strip().lower()
    if not raw:
        return ""
    if raw not in PART_STATUSES:
        raise ValueError(f"Unknown status: {raw}")
    return raw


def _set_row_status(store: LocalStore, rows: list[dict]) -> None:
    if not rows:
        raise ValueError("No rows to update")
    raw = Prompt.ask("Row #").strip()
    idx = int(raw)
    if idx < 1 or idx > len(rows):
        raise ValueError("Out of range")
    row = rows[idx - 1]
    CONSOLE.print(
        f"{row.get('ro_id')} / {row.get('work_item_id')} / {row.get('part_id')}: "
        f"{row.get('description')} [{part_status_label(row.get('status'))}]"
    )
    CONSOLE.print("Set to: ordered | received | received_wrong | new_request")
    st = Prompt.ask("New status", default="ordered").strip().lower()
    if st not in PART_STATUSES:
        raise ValueError(f"Unknown status: {st}")
    wrong = ""
    if st == "received_wrong":
        wrong = Prompt.ask("What was wrong?", default="Received wrong part").strip()
    order = store.get(str(row.get("ro_id") or ""))
    if not order:
        raise ValueError("RO not found locally")
    from carro.core import technicians as techmod

    tech = techmod.current_technician()
    set_part_status(
        order,
        str(row.get("work_item_id") or ""),
        str(row.get("part_id") or ""),
        st,
        wrong_note=wrong,
        actor=(tech.name if tech else "") or "",
        actor_id=(tech.id if tech else "") or "",
    )
    store.save(order)
    try:
        from carro.core.sync_ops import try_push_ro

        try_push_ro(store, order)
    except Exception:
        pass
    CONSOLE.print(f"[green]Updated {row.get('part_id')} → {part_status_label(st)}[/]")
