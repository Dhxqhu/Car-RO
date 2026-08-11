"""Interactive advisor login, setup, desk pool, and roster management (CLI)."""

from __future__ import annotations

from getpass import getpass
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from carro.core import advisors as advmod
from carro.core import technicians as techmod
from carro.core.advisors import Advisor
from carro.core.db import LocalStore

CONSOLE = Console()


def _ask_pin(label: str = "4-digit PIN") -> str:
    try:
        raw = getpass(f"{label}: ")
    except Exception:
        raw = Prompt.ask(label)
    return (raw or "").strip()


def _show_pin_once(name: str, pin: str, *, kind: str = "advisor") -> None:
    CONSOLE.print(
        Panel(
            f"[bold]{name}[/]\n\n"
            f"Login PIN: [bold cyan]{pin}[/]\n\n"
            f"[dim]Shown once — write it down. {kind.title()} login: pick name, then this PIN.[/]",
            title=f"New {kind} PIN",
            border_style="green",
        )
    )


def ensure_advisor_session(*, allow_skip: bool = False) -> Advisor | None:
    """First-run advisor setup or PIN login for advisor desk CLI."""
    _try_pull_advisor_roster()
    _try_pull_tech_roster()

    if not advmod.has_advisors():
        CONSOLE.print(
            Panel(
                "[bold]Advisor setup[/]\n\n"
                "Desk login is separate from technicians.\n"
                "Use the [bold]global admin PIN[/] (shared with the tech app).\n"
                "If none exists yet, you will set it here first.",
                border_style="cyan",
            )
        )
        if allow_skip and not Confirm.ask("Set up an advisor now?", default=True):
            return None
        return run_first_advisor_setup()

    existing = advmod.current_advisor()
    if existing:
        CONSOLE.print(f"[dim]Logged in as advisor[/] [cyan]{existing.name}[/]")
        if Confirm.ask("Continue as this advisor?", default=True):
            return existing
        advmod.clear_session()

    return prompt_advisor_login(retries=3)


def run_first_advisor_setup() -> Advisor:
    """Create first advisor; set or verify global admin PIN."""
    set_admin = not techmod.has_admin_pin()
    while True:
        if set_admin:
            admin = _ask_pin("New shop admin PIN (4 digits — shared with tech app)")
            admin2 = _ask_pin("Confirm admin PIN")
            if admin != admin2:
                CONSOLE.print("[red]Admin PINs did not match.[/]")
                continue
            try:
                techmod.validate_pin(admin)
            except ValueError as exc:
                CONSOLE.print(f"[red]{exc}[/]")
                continue
        else:
            admin = _ask_pin("Shop admin PIN")
            if not techmod.verify_admin_pin(admin):
                CONSOLE.print("[red]Incorrect admin PIN.[/]")
                continue
        break

    name = Prompt.ask("Advisor name").strip()
    while not name:
        name = Prompt.ask("Advisor name").strip()

    while True:
        pin = _ask_pin("Your advisor login PIN (must differ from admin / techs)")
        pin2 = _ask_pin("Confirm login PIN")
        if pin != pin2:
            CONSOLE.print("[red]PINs did not match.[/]")
            continue
        try:
            advmod.ensure_advisor_pin_available(pin, admin_pin_plain=admin)
        except ValueError as exc:
            CONSOLE.print(f"[red]{exc}[/]")
            continue
        break

    advisor = advmod.bootstrap_first_advisor(
        name, pin, admin_pin=admin, set_admin=set_admin
    )
    advmod.login_advisor(advisor.id, pin)
    techmod.clear_session()
    _try_push_advisor_roster()
    _try_push_tech_roster()
    CONSOLE.print(
        f"[green]Saved[/] advisor [cyan]{advisor.name}[/] · {advmod.ADVISORS_FILE}"
    )
    return advisor


def prompt_advisor_login(*, retries: int = 3) -> Advisor:
    advisors = advmod.list_advisors()
    if not advisors:
        raise RuntimeError("No advisors configured")

    if len(advisors) == 1:
        advisor = advisors[0]
    else:
        table = Table(show_header=False, box=None, padding=(0, 2))
        for i, a in enumerate(advisors, 1):
            table.add_row(f"[bold cyan]{i}[/]", a.name)
        CONSOLE.print(Panel(table, title="Advisor login", border_style="cyan"))
        raw = Prompt.ask("Advisor #", default="1").strip()
        if not raw.isdigit() or not (1 <= int(raw) <= len(advisors)):
            raise RuntimeError("Pick a number from the list")
        advisor = advisors[int(raw) - 1]

    # Reject technician PIN misuse early
    CONSOLE.print(f"Enter PIN for advisor [cyan]{advisor.name}[/]")
    last_err = "Incorrect PIN"
    for attempt in range(retries):
        pin = _ask_pin("PIN")
        if techmod.find_tech_by_pin(pin):
            raise RuntimeError("Technician PINs cannot log into the advisor CLI")
        try:
            logged = advmod.login_advisor(advisor.id, pin)
            techmod.clear_session()
            CONSOLE.print(f"[green]Welcome[/] [cyan]{logged.name}[/] (advisor)")
            return logged
        except ValueError as exc:
            last_err = str(exc)
            left = retries - attempt - 1
            if left:
                CONSOLE.print(f"[red]{last_err}[/] ([dim]{left} tries left[/])")
    raise RuntimeError(last_err)


def switch_advisor() -> Advisor | None:
    cur = advmod.current_advisor()
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[bold cyan]1[/]", "Login / switch")
    table.add_row("[bold cyan]2[/]", "Change my PIN")
    table.add_row("[bold cyan]3[/]", "Manage people (advisors + techs)")
    table.add_row("[bold cyan]4[/]", "Logout")
    table.add_row("[bold cyan]b[/]", "Back")
    CONSOLE.print(
        Panel(
            table,
            title="Advisor",
            subtitle=f"Current: {cur.name if cur else '(none)'}",
            border_style="cyan",
        )
    )
    choice = Prompt.ask("Choice", default="1").strip().lower()
    if choice in {"b", "q", "back", ""}:
        return cur
    if choice == "2":
        change_my_advisor_pin()
        return advmod.current_advisor()
    if choice == "3":
        run_people_menu()
        return advmod.current_advisor()
    if choice == "4":
        advmod.clear_session()
        CONSOLE.print("[dim]Logged out.[/]")
        return None
    try:
        return prompt_advisor_login()
    except RuntimeError as exc:
        CONSOLE.print(f"[red]{exc}[/]")
        return advmod.current_advisor()


def change_my_advisor_pin() -> bool:
    advisor = advmod.current_advisor()
    if not advisor:
        CONSOLE.print("[yellow]Log in as an advisor first.[/]")
        return False
    while True:
        pin = _ask_pin("New login PIN")
        pin2 = _ask_pin("Confirm new PIN")
        if pin != pin2:
            CONSOLE.print("[red]PINs did not match.[/]")
            continue
        try:
            advmod.update_advisor_pin(advisor.id, pin)
            break
        except ValueError as exc:
            CONSOLE.print(f"[red]{exc}[/]")
            if not Confirm.ask("Try again?", default=True):
                return False
    advmod.save_session(advmod.get_advisor(advisor.id) or advisor)
    _try_push_advisor_roster()
    CONSOLE.print("[green]Your login PIN was updated.[/]")
    return True


def run_people_menu() -> None:
    """Add advisors (always) and techs (advisor session or admin PIN)."""
    if not advmod.current_advisor() and not _verify_admin_once():
        return
    while True:
        CONSOLE.clear()
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[bold cyan]1[/]", "List advisors")
        table.add_row("[bold cyan]2[/]", "Add advisor")
        table.add_row("[bold cyan]3[/]", "Reset advisor PIN")
        table.add_row("[bold cyan]4[/]", "Rename advisor")
        table.add_row("[bold cyan]5[/]", "Remove advisor")
        table.add_row("[bold cyan]6[/]", "List technicians")
        table.add_row("[bold cyan]7[/]", "Add technician")
        table.add_row("[bold cyan]8[/]", "Pull rosters from server")
        table.add_row("[bold cyan]9[/]", "Push rosters to server")
        table.add_row("[bold cyan]b[/]", "Back")
        CONSOLE.print(
            Panel(
                table,
                title="People (advisor desk)",
                subtitle=f"{len(advmod.list_advisors())} advisor(s) · "
                f"{len(techmod.list_technicians())} tech(s)",
                border_style="cyan",
            )
        )
        choice = Prompt.ask("Setting", default="b").strip().lower()
        if choice in {"b", "q", "back", ""}:
            return
        try:
            if choice == "1":
                _list_advisors()
            elif choice == "2":
                _add_advisor()
            elif choice == "3":
                _reset_advisor_pin()
            elif choice == "4":
                _rename_advisor()
            elif choice == "5":
                _remove_advisor()
            elif choice == "6":
                _list_techs()
            elif choice == "7":
                _add_tech()
            elif choice == "8":
                a = _try_pull_advisor_roster(force=True)
                t = _try_pull_tech_roster(force=True)
                CONSOLE.print(
                    f"[green]Pull[/] advisors={'ok' if a else 'skip'} · "
                    f"techs={'ok' if t else 'skip'}"
                )
            elif choice == "9":
                a = _try_push_advisor_roster()
                t = _try_push_tech_roster()
                CONSOLE.print(
                    f"[green]Push[/] advisors={'ok' if a else 'skip'} · "
                    f"techs={'ok' if t else 'skip'}"
                )
            else:
                CONSOLE.print("[yellow]Unknown option[/]")
                continue
        except (ValueError, RuntimeError, OSError) as exc:
            CONSOLE.print(f"[red]{exc}[/]")
        Prompt.ask("[dim]Press Enter for menu[/]", default="")


def _verify_admin_once() -> bool:
    if not techmod.has_admin_pin():
        CONSOLE.print("[yellow]No admin PIN set.[/]")
        return False
    pin = _ask_pin("Admin PIN")
    if not techmod.verify_admin_pin(pin):
        CONSOLE.print("[red]Incorrect admin PIN.[/]")
        return False
    return True


def _list_advisors() -> None:
    rows = advmod.list_advisors()
    if not rows:
        CONSOLE.print("[dim]No advisors yet.[/]")
        return
    table = Table(title="Advisors")
    table.add_column("Id", style="cyan")
    table.add_column("Name")
    for a in rows:
        table.add_row(a.id, a.name)
    CONSOLE.print(table)


def _list_techs() -> None:
    rows = techmod.list_technicians()
    if not rows:
        CONSOLE.print("[dim]No technicians yet.[/]")
        return
    table = Table(title="Technicians")
    table.add_column("Id", style="cyan")
    table.add_column("Name")
    for t in rows:
        table.add_row(t.id, t.name)
    CONSOLE.print(table)


def _pick_advisor() -> Advisor | None:
    rows = advmod.list_advisors()
    if not rows:
        CONSOLE.print("[dim]No advisors.[/]")
        return None
    for i, a in enumerate(rows, 1):
        CONSOLE.print(f"  [cyan]{i}[/] {a.name} ([dim]{a.id}[/])")
    raw = Prompt.ask("Pick #", default="1").strip()
    if not raw.isdigit() or not (1 <= int(raw) <= len(rows)):
        return None
    return rows[int(raw) - 1]


def _ask_new_pin() -> str:
    mode = Prompt.ask("PIN", choices=["generate", "enter"], default="generate").strip().lower()
    if mode == "generate":
        # reuse tech generate but check advisor conflicts via ensure
        for _ in range(50):
            pin = techmod.generate_pin()
            try:
                return advmod.ensure_advisor_pin_available(pin)
            except ValueError:
                continue
        raise RuntimeError("Could not generate a free PIN")
    while True:
        pin = _ask_pin("New 4-digit PIN")
        pin2 = _ask_pin("Confirm PIN")
        if pin != pin2:
            CONSOLE.print("[red]PINs did not match.[/]")
            continue
        try:
            return advmod.ensure_advisor_pin_available(pin)
        except ValueError as exc:
            CONSOLE.print(f"[red]{exc}[/]")


def _add_advisor() -> None:
    name = Prompt.ask("Name").strip()
    while not name:
        name = Prompt.ask("Name").strip()
    pin = _ask_new_pin()
    advisor = advmod.add_advisor(name, pin)
    _try_push_advisor_roster()
    _show_pin_once(advisor.name, pin, kind="advisor")
    CONSOLE.print(f"[green]Added[/] advisor {advisor.name}")


def _reset_advisor_pin() -> None:
    advisor = _pick_advisor()
    if not advisor:
        return
    pin = _ask_new_pin()
    advmod.update_advisor_pin(advisor.id, pin)
    _try_push_advisor_roster()
    _show_pin_once(advisor.name, pin, kind="advisor")
    CONSOLE.print("[green]PIN updated[/]")


def _rename_advisor() -> None:
    advisor = _pick_advisor()
    if not advisor:
        return
    name = Prompt.ask("New name", default=advisor.name).strip()
    advmod.rename_advisor(advisor.id, name)
    _try_push_advisor_roster()
    CONSOLE.print("[green]Renamed[/]")


def _remove_advisor() -> None:
    advisor = _pick_advisor()
    if not advisor:
        return
    if not Confirm.ask(f"Remove {advisor.name}?", default=False):
        return
    advmod.remove_advisor(advisor.id)
    _try_push_advisor_roster()
    CONSOLE.print("[green]Removed[/]")


def _add_tech() -> None:
    name = Prompt.ask("Technician name").strip()
    while not name:
        name = Prompt.ask("Technician name").strip()
    while True:
        pin = _ask_pin("Technician login PIN")
        pin2 = _ask_pin("Confirm PIN")
        if pin != pin2:
            CONSOLE.print("[red]PINs did not match.[/]")
            continue
        try:
            tech = techmod.add_technician(name, pin)
            break
        except ValueError as exc:
            CONSOLE.print(f"[red]{exc}[/]")
            if not Confirm.ask("Try again?", default=True):
                return
    _try_push_tech_roster()
    _show_pin_once(tech.name, pin, kind="technician")
    CONSOLE.print(f"[green]Added[/] technician {tech.name}")


def run_desk_pool_menu(store: LocalStore) -> None:
    """Shared advisor pool: parts / customer / ready-to-bill / found issues."""
    advisor = advmod.current_advisor()
    if not advisor:
        CONSOLE.print("[yellow]Advisor login required.[/]")
        return
    from carro.core.advisor_actions import append_advisor_action
    from carro.core.assignment import (
        assign_work_item,
        bill_out_ro,
        build_assigned_board,
    )
    from carro.core.found_issues import (
        approve_found_issue,
        decline_found_issue,
        unapprove_found_issue,
    )

    while True:
        CONSOLE.clear()
        board = build_assigned_board(store.list_orders())
        _print_pool_board(board)
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[bold cyan]1[/]", "Approve found issue → work item")
        table.add_row("[bold cyan]2[/]", "Decline found issue")
        table.add_row("[bold cyan]3[/]", "Undo found-issue approval")
        table.add_row("[bold cyan]4[/]", "Mark RO billed out (ready-to-bill)")
        table.add_row("[bold cyan]5[/]", "Assign work item to a technician")
        table.add_row("[bold cyan]6[/]", "Show advisor action trail on an RO")
        table.add_row("[bold cyan]r[/]", "Refresh")
        table.add_row("[bold cyan]b[/]", "Back")
        CONSOLE.print(
            Panel(
                table,
                title="Desk pool actions",
                subtitle=f"Acting as {advisor.name}",
                border_style="cyan",
            )
        )
        choice = Prompt.ask("Action", default="r").strip().lower()
        if choice in {"b", "q", "back"}:
            return
        if choice == "r":
            continue
        try:
            if choice == "1":
                _desk_approve_fi(store, advisor, approve_found_issue, append_advisor_action)
            elif choice == "2":
                _desk_decline_fi(store, advisor, decline_found_issue, append_advisor_action)
            elif choice == "3":
                _desk_unapprove_fi(store, advisor, unapprove_found_issue, append_advisor_action)
            elif choice == "4":
                _desk_bill_out(store, advisor, bill_out_ro, append_advisor_action)
            elif choice == "5":
                _desk_assign(store, advisor, assign_work_item, append_advisor_action)
            elif choice == "6":
                _desk_show_trail(store)
            else:
                CONSOLE.print("[yellow]Unknown option[/]")
                continue
        except (ValueError, RuntimeError) as exc:
            CONSOLE.print(f"[red]{exc}[/]")
        Prompt.ask("[dim]Press Enter[/]", default="")


def _print_pool_board(board: dict[str, Any]) -> None:
    def _section(title: str, rows: list[dict[str, Any]], *, keys: tuple[str, ...]) -> None:
        CONSOLE.print(f"\n[bold]{title}[/] ([cyan]{len(rows)}[/])")
        if not rows:
            CONSOLE.print("  [dim](empty)[/]")
            return
        for r in rows[:25]:
            bits = [str(r.get(k) or "") for k in keys]
            CONSOLE.print("  · " + " · ".join(b for b in bits if b))
        if len(rows) > 25:
            CONSOLE.print(f"  [dim]… {len(rows) - 25} more[/]")

    _section(
        "Waiting on parts",
        list(board.get("waiting_parts") or []),
        keys=("ro_id", "item_id", "customer", "concern"),
    )
    _section(
        "Customer approval",
        list(board.get("waiting_customer") or []),
        keys=("ro_id", "item_id", "customer", "concern"),
    )
    _section(
        "Found issues pending",
        list(board.get("found_issues_pending") or []),
        keys=("ro_id", "id", "customer", "description"),
    )
    _section(
        "Ready to bill",
        list(board.get("ready_to_bill") or []),
        keys=("id", "customer", "vehicle"),
    )
    _section(
        "Unassigned work items",
        list(board.get("unassigned") or []),
        keys=("ro_id", "item_id", "customer", "concern"),
    )


def _desk_approve_fi(store, advisor, approve_found_issue, append_advisor_action) -> None:
    ro_id = Prompt.ask("RO id").strip()
    fi_id = Prompt.ask("Found-issue id (FI-…)").strip()
    order = store.get(ro_id)
    if not order:
        raise ValueError("RO not found")
    item_type = Prompt.ask("Item type", default="repair").strip() or "repair"
    assign_id = Prompt.ask(
        "Assign to tech id (blank = Needs attention Unassigned)",
        default="",
    ).strip()
    assign_name = ""
    if assign_id:
        tech = techmod.get_technician(assign_id)
        if not tech:
            raise ValueError(f"Unknown technician id: {assign_id}")
        assign_name = tech.name
    approve_found_issue(
        order,
        fi_id,
        item_type=item_type,
        actor=advisor.name,
        actor_id=advisor.id,
        actor_role="advisor",
        assign_to_id=assign_id,
        assign_to_name=assign_name,
    )
    append_advisor_action(
        order,
        action="found_issue_approved",
        advisor_id=advisor.id,
        advisor_name=advisor.name,
        found_issue_id=fi_id,
    )
    store.save(order)
    _push_ro(order)
    if assign_name:
        CONSOLE.print(f"[green]Approved → assigned to {assign_name}[/]")
    else:
        CONSOLE.print("[green]Approved → Unassigned (Needs attention)[/]")


def _desk_unapprove_fi(store, advisor, unapprove_found_issue, append_advisor_action) -> None:
    ro_id = Prompt.ask("RO id").strip()
    fi_id = Prompt.ask("Found-issue id (FI-…)").strip()
    order = store.get(ro_id)
    if not order:
        raise ValueError("RO not found")
    unapprove_found_issue(
        order,
        fi_id,
        actor=advisor.name,
        actor_id=advisor.id,
    )
    append_advisor_action(
        order,
        action="found_issue_unapproved",
        advisor_id=advisor.id,
        advisor_name=advisor.name,
        found_issue_id=fi_id,
    )
    store.save(order)
    _push_ro(order)
    CONSOLE.print("[green]Approval undone — found issue is pending again[/]")


def _desk_decline_fi(store, advisor, decline_found_issue, append_advisor_action) -> None:
    ro_id = Prompt.ask("RO id").strip()
    fi_id = Prompt.ask("Found-issue id (FI-…)").strip()
    order = store.get(ro_id)
    if not order:
        raise ValueError("RO not found")
    reason = Prompt.ask(
        "Reason",
        choices=["customer_declined", "not_needed", "other"],
        default="customer_declined",
    )
    decline_found_issue(
        order,
        fi_id,
        reason=reason,
        actor=advisor.name,
        actor_id=advisor.id,
    )
    append_advisor_action(
        order,
        action="found_issue_declined",
        advisor_id=advisor.id,
        advisor_name=advisor.name,
        found_issue_id=fi_id,
        detail=reason,
    )
    store.save(order)
    _push_ro(order)
    CONSOLE.print("[green]Declined[/]")


def _desk_bill_out(store, advisor, bill_out_ro, append_advisor_action) -> None:
    ro_id = Prompt.ask("RO id (ready to bill)").strip()
    order = store.get(ro_id)
    if not order:
        raise ValueError("RO not found")
    bill_out_ro(order, tech_id=advisor.id, tech_name=advisor.name)
    append_advisor_action(
        order,
        action="billed_out",
        advisor_id=advisor.id,
        advisor_name=advisor.name,
    )
    store.save(order)
    _push_ro(order)
    CONSOLE.print("[green]Billed out[/]")


def _desk_assign(store, advisor, assign_work_item, append_advisor_action) -> None:
    ro_id = Prompt.ask("RO id").strip()
    item_id = Prompt.ask("Work item id (WI-…)").strip()
    techs = techmod.list_technicians()
    if not techs:
        raise ValueError("No technicians to assign")
    for i, t in enumerate(techs, 1):
        CONSOLE.print(f"  [cyan]{i}[/] {t.name}")
    raw = Prompt.ask("Tech #", default="1").strip()
    if not raw.isdigit() or not (1 <= int(raw) <= len(techs)):
        raise ValueError("Invalid tech #")
    tech = techs[int(raw) - 1]
    order = store.get(ro_id)
    if not order:
        raise ValueError("RO not found")
    if not assign_work_item(order, item_id, tech_id=tech.id, tech_name=tech.name):
        raise ValueError("Work item not found")
    append_advisor_action(
        order,
        action="assigned_to_tech",
        advisor_id=advisor.id,
        advisor_name=advisor.name,
        work_item_id=item_id,
        detail=f"{tech.name} ({tech.id})",
    )
    store.save(order)
    _push_ro(order)
    CONSOLE.print(f"[green]Assigned[/] {item_id} → {tech.name}")


def _desk_show_trail(store) -> None:
    ro_id = Prompt.ask("RO id").strip()
    order = store.get(ro_id)
    if not order:
        raise ValueError("RO not found")
    actions = list(getattr(order, "advisor_actions", None) or [])
    if not actions:
        CONSOLE.print("[dim]No advisor actions on this RO yet.[/]")
        return
    table = Table(title=f"Advisor trail · {ro_id}")
    table.add_column("When")
    table.add_column("Advisor")
    table.add_column("Action")
    table.add_column("Detail")
    for a in actions[-40:]:
        table.add_row(
            str(a.get("at") or ""),
            str(a.get("advisor_name") or a.get("advisor_id") or ""),
            str(a.get("action") or ""),
            " ".join(
                x
                for x in (
                    a.get("work_item_id") or "",
                    a.get("found_issue_id") or "",
                    a.get("detail") or "",
                    a.get("note") or "",
                )
                if x
            ),
        )
    CONSOLE.print(table)


def interactive_advisor_menu(store: LocalStore) -> None:
    """Top-level advisor desk loop (no scanner / bay timers)."""
    from carro.core.autosync import start_autosync, stop_autosync
    from carro.core.parts_sheet import run_parts_sheet_menu

    while True:
        try:
            ensure_advisor_session()
            break
        except RuntimeError as exc:
            CONSOLE.print(f"[red]{exc}[/]")
            if not Confirm.ask("Try login again?", default=True):
                return

    start_autosync(store)
    try:
        while True:
            CONSOLE.clear()
            advisor = advmod.current_advisor()
            title = f"Car-RO Advisor · {advisor.name}" if advisor else "Car-RO Advisor"
            table = Table(title=title, show_header=False, box=None, padding=(0, 2))
            table.add_row("[bold cyan]1[/]", "Desk pool (parts / approval / billing / found issues)")
            table.add_row("[bold cyan]2[/]", "Parts sheet / archive search")
            table.add_row("[bold cyan]3[/]", "People (advisors + techs)")
            table.add_row("[bold cyan]4[/]", "Advisor account (switch / logout)")
            table.add_row("[bold cyan]m[/]", "Messages")
            table.add_row("[bold cyan]s[/]", "Sync to server")
            table.add_row("[bold cyan]q[/]", "Quit")
            CONSOLE.print(Panel(table, border_style="cyan"))
            choice = Prompt.ask("Select", default="1").strip().lower()
            if choice in {"q", "quit"}:
                return
            try:
                if choice == "1":
                    run_desk_pool_menu(store)
                elif choice == "2":
                    run_parts_sheet_menu(store)
                elif choice == "3":
                    run_people_menu()
                elif choice == "4":
                    switch_advisor()
                    if not advmod.current_advisor():
                        ensure_advisor_session()
                elif choice == "m":
                    from carro.core.messages_ui import run_messages_menu

                    run_messages_menu()
                elif choice == "s":
                    from carro.core.sync_ops import perform_sync

                    r = perform_sync(store)
                    CONSOLE.print(r.get("message") or r)
                    Prompt.ask("[dim]Press Enter[/]", default="")
                else:
                    CONSOLE.print("[yellow]Unknown option[/]")
                    Prompt.ask("[dim]Press Enter[/]", default="")
            except (RuntimeError, ValueError) as exc:
                CONSOLE.print(f"[red]{exc}[/]")
                Prompt.ask("[dim]Press Enter[/]", default="")
    finally:
        stop_autosync()


def _push_ro(order: Any) -> None:
    try:
        from carro.core.sync_ops import try_push_ro
        from carro.core.db import LocalStore

        try_push_ro(LocalStore(), order)
    except Exception:
        pass


def _try_pull_advisor_roster(*, force: bool = False) -> bool:
    try:
        from carro.storage.remote import RemoteClient

        remote = RemoteClient()
        if not remote.enabled:
            return False
        data = remote.get_advisors()
        if force and isinstance(data, dict):
            from carro.core.models import now_iso

            advmod.save_roster(
                {
                    "version": 1,
                    "updated": str(data.get("updated") or now_iso()),
                    "advisors": list(data.get("advisors") or []),
                }
            )
            return True
        return advmod.apply_remote_roster(data)
    except Exception:
        return False


def _try_push_advisor_roster() -> bool:
    try:
        from carro.storage.remote import RemoteClient

        remote = RemoteClient()
        if not remote.enabled:
            return False
        remote.put_advisors(advmod.roster_for_sync())
        return True
    except Exception:
        return False


def _try_pull_tech_roster(*, force: bool = False) -> bool:
    try:
        from carro.core.tech_ui import _try_pull_roster

        return _try_pull_roster(force=force)
    except Exception:
        return False


def _try_push_tech_roster() -> bool:
    try:
        from carro.core.tech_ui import _try_push_roster

        return _try_push_roster()
    except Exception:
        return False
