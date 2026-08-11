"""Interactive technician login, setup, and roster management."""

from __future__ import annotations

from getpass import getpass

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from carro.core import technicians as techmod
from carro.core.technicians import Technician

CONSOLE = Console()


def _ask_pin(label: str = "4-digit PIN") -> str:
    """Prefer hidden input; fall back to Prompt."""
    try:
        raw = getpass(f"{label}: ")
    except Exception:
        raw = Prompt.ask(label)
    return (raw or "").strip()


def _show_pin_once(name: str, pin: str) -> None:
    CONSOLE.print(
        Panel(
            f"[bold]{name}[/]\n\n"
            f"Login PIN: [bold cyan]{pin}[/]\n\n"
            "[dim]Shown once — write it down. Login is: pick your name, then this PIN.[/]",
            title="New technician PIN",
            border_style="green",
        )
    )


def ensure_technician_session(*, allow_skip: bool = False) -> Technician | None:
    """
    First-run setup or PIN login for interactive menu.
    Returns logged-in tech, or None only if allow_skip and user skips.
    """
    # Try pull from server before login (best-effort)
    _try_pull_roster()

    if not techmod.has_technicians():
        CONSOLE.print(
            Panel(
                "[bold]Technician setup[/]\n\n"
                "Car-RO stamps the tech name on repair orders and PDFs.\n"
                "Set an [bold]admin PIN[/] (managing techs) and your login PIN "
                "[bold](must be different)[/].",
                border_style="cyan",
            )
        )
        if allow_skip and not Confirm.ask("Set up technicians now?", default=True):
            return None
        return run_first_tech_setup()

    existing = techmod.current_technician()
    if existing:
        CONSOLE.print(f"[dim]Logged in as[/] [cyan]{existing.name}[/]")
        if Confirm.ask("Continue as this technician?", default=True):
            return existing
        techmod.clear_session()

    return prompt_login(retries=3)


def run_first_tech_setup() -> Technician:
    """Create first technician; set or verify global admin PIN."""
    set_admin = not techmod.has_admin_pin()
    while True:
        if set_admin:
            admin = _ask_pin("Admin PIN (4 digits — for adding/editing techs)")
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
            CONSOLE.print(
                "[dim]Shop admin PIN already set (e.g. from Advisor app). Enter it to continue.[/]"
            )
            admin = _ask_pin("Shop admin PIN")
            if not techmod.verify_admin_pin(admin):
                CONSOLE.print("[red]Incorrect admin PIN.[/]")
                continue
        break

    name = Prompt.ask("Your name (as it should appear on ROs)").strip()
    while not name:
        name = Prompt.ask("Your name").strip()

    while True:
        pin = _ask_pin("Your 4-digit login PIN (must differ from admin)")
        pin2 = _ask_pin("Confirm your login PIN")
        if pin != pin2:
            CONSOLE.print("[red]PINs did not match.[/]")
            continue
        try:
            techmod.ensure_pin_available(pin, admin_pin_plain=admin, check_admin=False)
        except ValueError as exc:
            CONSOLE.print(f"[red]{exc}[/]")
            continue
        break

    if set_admin:
        roster = techmod.empty_roster()
        techmod.set_admin_pin(admin, roster=roster)
        tech = techmod.add_technician(name, pin)
    else:
        tech = techmod.add_technician(name, pin, admin_pin_plain=admin)
    techmod.save_session(tech)
    _try_push_roster()
    CONSOLE.print(f"[green]Saved[/] technician [cyan]{tech.name}[/] · {techmod.TECHNICIANS_FILE}")
    return tech


def _pick_tech_by_name(*, prompt: str = "Who are you?") -> tuple[Technician | None, str]:
    """
    Returns (tech, raw_input). raw_input is set when the user typed something
    that wasn't a valid list index (often a PIN by mistake).
    """
    techs = techmod.list_technicians()
    if not techs:
        CONSOLE.print("[dim]No technicians configured.[/]")
        return None, ""
    if len(techs) == 1:
        return techs[0], ""
    table = Table(show_header=False, box=None, padding=(0, 2))
    for i, t in enumerate(techs, 1):
        table.add_row(f"[bold cyan]{i}[/]", t.name)
    CONSOLE.print(Panel(table, title=prompt, border_style="cyan"))
    CONSOLE.print("[dim]Enter the number next to your name (PIN comes next).[/]")
    raw = Prompt.ask("Technician #", default="1").strip()
    if raw.isdigit() and 1 <= int(raw) <= len(techs):
        return techs[int(raw) - 1], ""
    CONSOLE.print("[yellow]Pick a number from the list (not your PIN).[/]")
    return None, raw


def prompt_login(*, retries: int = 3) -> Technician:
    """Pick name from list (skipped if only one tech), then enter that tech's PIN."""
    techs = techmod.list_technicians()
    if not techs:
        raise RuntimeError("No technicians configured")

    if len(techs) == 1:
        tech = techs[0]
    else:
        tech, mistaken = _pick_tech_by_name(prompt="Technician login")
        if tech is None:
            if mistaken and techmod.find_tech_by_pin(mistaken):
                found = techmod.find_tech_by_pin(mistaken)
                assert found is not None
                techmod.save_session(found)
                CONSOLE.print(f"[green]Welcome[/] [cyan]{found.name}[/]")
                return found
            raise RuntimeError(
                "No technician selected — enter the list number (e.g. 1), then your PIN"
            )

    CONSOLE.print(f"Enter PIN for [cyan]{tech.name}[/]")
    last_err = "Incorrect PIN"
    for attempt in range(retries):
        pin = _ask_pin("PIN")
        try:
            from carro.core import advisors as advmod

            for adv in advmod.list_advisors():
                if techmod.verify_pin(pin, adv.pin_hash):
                    raise ValueError("Advisor PINs cannot log into the technician CLI")
        except ValueError as exc:
            last_err = str(exc)
            left = retries - attempt - 1
            if left:
                CONSOLE.print(f"[red]{last_err}[/] ([dim]{left} tries left[/])")
            continue
        try:
            logged = techmod.login_technician(tech.id, pin)
            try:
                from carro.core import advisors as advmod

                advmod.clear_session()
            except Exception:
                pass
            CONSOLE.print(f"[green]Welcome[/] [cyan]{logged.name}[/]")
            return logged
        except ValueError as exc:
            last_err = str(exc)
            left = retries - attempt - 1
            if left:
                CONSOLE.print(f"[red]{last_err}[/] ([dim]{left} tries left[/])")
    raise RuntimeError(last_err)


def change_my_pin() -> bool:
    """Logged-in tech changes their own login PIN (no admin required)."""
    tech = techmod.current_technician()
    if not tech:
        CONSOLE.print("[yellow]Log in first, then change your PIN.[/]")
        return False
    CONSOLE.print(
        Panel(
            f"Change login PIN for [cyan]{tech.name}[/]\n"
            "[dim]Must not match the admin PIN or another technician.[/]",
            border_style="cyan",
        )
    )
    while True:
        pin = _ask_pin("New login PIN")
        pin2 = _ask_pin("Confirm new PIN")
        if pin != pin2:
            CONSOLE.print("[red]PINs did not match.[/]")
            continue
        try:
            techmod.update_technician_pin(tech.id, pin)
            break
        except ValueError as exc:
            CONSOLE.print(f"[red]{exc}[/]")
            if not Confirm.ask("Try again?", default=True):
                return False
    # Refresh session name/id (same tech)
    techmod.save_session(techmod.get_technician(tech.id) or tech)
    _try_push_roster()
    CONSOLE.print("[green]Your login PIN was updated.[/]")
    return True


def switch_technician() -> Technician | None:
    """Menu: login / change my PIN / manage roster / logout / stay."""
    cur = techmod.current_technician()
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[bold cyan]1[/]", "Login / switch (pick name + PIN)")
    table.add_row("[bold cyan]2[/]", "Change my PIN")
    table.add_row("[bold cyan]3[/]", "Manage technicians (admin PIN)")
    table.add_row("[bold cyan]4[/]", "Logout")
    table.add_row("[bold cyan]b[/]", "Back")
    CONSOLE.print(
        Panel(
            table,
            title="Technician",
            subtitle=f"Current: {cur.name if cur else '(none)'}",
            border_style="cyan",
        )
    )
    choice = Prompt.ask("Choice", default="1").strip().lower()
    if choice in {"b", "q", "back", ""}:
        return cur
    if choice == "2":
        change_my_pin()
        return techmod.current_technician()
    if choice == "3":
        CONSOLE.print(
            "[dim]Admin PIN is the shop PIN from setup — not your personal login PIN "
            "(unless you never changed them apart).[/]"
        )
        run_technicians_config_menu()
        return techmod.current_technician()
    if choice == "4":
        techmod.clear_session()
        CONSOLE.print("[dim]Logged out.[/]")
        return None
    try:
        return prompt_login()
    except RuntimeError as exc:
        CONSOLE.print(f"[red]{exc}[/]")
        return techmod.current_technician()


def require_admin() -> bool:
    if not techmod.load_roster().get("admin_pin_hash"):
        CONSOLE.print("[yellow]No admin PIN set — run technician setup first.[/]")
        return False
    CONSOLE.print(
        "[dim]Enter the [bold]admin[/] PIN (shop PIN for adding techs), "
        "not your personal login PIN.[/]"
    )
    pin = _ask_pin("Admin PIN")
    if not techmod.verify_admin_pin(pin):
        CONSOLE.print(
            "[red]Incorrect admin PIN.[/]\n"
            "[dim]Hint: if you reused the same digits for login + admin at setup, "
            "admin is still that original PIN — even after you changed your login PIN.[/]"
        )
        return False
    return True


def run_technicians_config_menu() -> None:
    """Config submenu: manage roster (admin unlocked once for edits)."""
    admin_ok = False

    def _need_admin() -> bool:
        nonlocal admin_ok
        if admin_ok:
            return True
        if require_admin():
            admin_ok = True
            return True
        return False

    while True:
        CONSOLE.clear()
        roster = techmod.load_roster()
        techs = techmod.list_technicians(roster)
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[bold cyan]1[/]", "List technicians")
        table.add_row("[bold cyan]2[/]", "Add technician")
        table.add_row("[bold cyan]3[/]", "Reset technician PIN")
        table.add_row("[bold cyan]4[/]", "Rename technician")
        table.add_row("[bold cyan]5[/]", "Remove technician")
        table.add_row("[bold cyan]6[/]", "Change admin PIN")
        table.add_row("[bold cyan]7[/]", "Change my PIN (logged-in tech)")
        table.add_row("[bold cyan]8[/]", "Pull roster from server")
        table.add_row("[bold cyan]9[/]", "Push roster to server")
        table.add_row("[bold cyan]b[/]", "Back")
        unlock = "admin unlocked" if admin_ok else "admin required for edits"
        CONSOLE.print(
            Panel(
                table,
                title="Technicians",
                subtitle=f"{len(techs)} tech(s) · {unlock} · {techmod.TECHNICIANS_FILE}",
                border_style="cyan",
            )
        )
        choice = Prompt.ask("Setting", default="b").strip().lower()
        if choice in {"b", "q", "back", ""}:
            return
        try:
            if choice == "1":
                _list_techs()
            elif choice == "2":
                if _need_admin():
                    _add_tech()
            elif choice == "3":
                if _need_admin():
                    _reset_pin()
            elif choice == "4":
                if _need_admin():
                    _rename_tech()
            elif choice == "5":
                if _need_admin():
                    _remove_tech()
            elif choice == "6":
                if _need_admin():
                    _change_admin()
            elif choice == "7":
                change_my_pin()
            elif choice == "8":
                status = sync_roster_with_server()
                CONSOLE.print(f"[green]Roster sync[/] {status}")
            elif choice == "9":
                ok_tech = _try_push_roster()
                ok_adv = False
                try:
                    from carro.core import advisors as advmod
                    from carro.storage.remote import RemoteClient

                    remote = RemoteClient()
                    if remote.enabled and advmod.has_advisors():
                        remote.put_advisors(advmod.roster_for_sync())
                        ok_adv = True
                except Exception:
                    pass
                if ok_tech or ok_adv:
                    parts = []
                    if ok_tech:
                        parts.append("technicians")
                    if ok_adv:
                        parts.append("advisors")
                    CONSOLE.print(f"[green]Pushed[/] {', '.join(parts)} to server")
                else:
                    CONSOLE.print("[yellow]Push skipped (server not configured or failed).[/]")
            else:
                CONSOLE.print("[yellow]Unknown option[/]")
                continue
        except (ValueError, RuntimeError, OSError) as exc:
            CONSOLE.print(f"[red]{exc}[/]")
        Prompt.ask("[dim]Press Enter for menu[/]", default="")


def _list_techs() -> None:
    techs = techmod.list_technicians()
    if not techs:
        CONSOLE.print("[dim]No technicians yet.[/]")
        return
    table = Table(title="Technicians")
    table.add_column("Id", style="cyan")
    table.add_column("Name")
    for t in techs:
        table.add_row(t.id, t.name)
    CONSOLE.print(table)


def _pick_tech() -> Technician | None:
    techs = techmod.list_technicians()
    if not techs:
        CONSOLE.print("[dim]No technicians.[/]")
        return None
    for i, t in enumerate(techs, 1):
        CONSOLE.print(f"  [cyan]{i}[/] {t.name} ([dim]{t.id}[/])")
    raw = Prompt.ask("Pick #", default="1").strip()
    if not raw.isdigit() or not (1 <= int(raw) <= len(techs)):
        return None
    return techs[int(raw) - 1]


def _ask_new_pin(*, label: str = "PIN") -> str:
    """Generate (default) or enter a PIN that does not conflict."""
    mode = Prompt.ask(
        "PIN",
        choices=["generate", "enter"],
        default="generate",
    ).strip().lower()
    if mode == "generate":
        return techmod.generate_pin()
    while True:
        pin = _ask_pin(f"New 4-digit {label}")
        pin2 = _ask_pin(f"Confirm {label}")
        if pin != pin2:
            CONSOLE.print("[red]PINs did not match.[/]")
            continue
        try:
            return techmod.ensure_pin_available(pin)
        except ValueError as exc:
            CONSOLE.print(f"[red]{exc}[/]")


def _add_tech() -> None:
    name = Prompt.ask("Name").strip()
    while not name:
        name = Prompt.ask("Name").strip()
    pin = _ask_new_pin(label="login PIN")
    tech = techmod.add_technician(name, pin)
    _try_push_roster()
    _show_pin_once(tech.name, pin)
    CONSOLE.print(f"[green]Added[/] {tech.name}")


def _reset_pin() -> None:
    tech = _pick_tech()
    if not tech:
        return
    pin = _ask_new_pin(label=f"PIN for {tech.name}")
    techmod.update_technician_pin(tech.id, pin)
    _try_push_roster()
    _show_pin_once(tech.name, pin)
    CONSOLE.print("[green]PIN updated[/]")


def _rename_tech() -> None:
    tech = _pick_tech()
    if not tech:
        return
    name = Prompt.ask("New name", default=tech.name).strip()
    techmod.rename_technician(tech.id, name)
    _try_push_roster()
    CONSOLE.print("[green]Renamed[/]")


def _remove_tech() -> None:
    tech = _pick_tech()
    if not tech:
        return
    if not Confirm.ask(f"Remove {tech.name}?", default=False):
        return
    techmod.remove_technician(tech.id)
    _try_push_roster()
    CONSOLE.print("[green]Removed[/]")


def _change_admin() -> None:
    while True:
        pin = _ask_pin("New admin PIN")
        pin2 = _ask_pin("Confirm admin PIN")
        if pin != pin2:
            CONSOLE.print("[red]PINs did not match.[/]")
            continue
        try:
            techmod.set_admin_pin(pin)
            break
        except ValueError as exc:
            CONSOLE.print(f"[red]{exc}[/]")
            if not Confirm.ask("Try again?", default=True):
                return
    _try_push_roster()
    CONSOLE.print("[green]Admin PIN updated[/]")


def _try_pull_roster(*, force: bool = False) -> bool:
    try:
        from carro.storage.remote import RemoteClient

        remote = RemoteClient()
        if not remote.enabled:
            return False
        data = remote.get_technicians()
        if force:
            from carro.core.models import now_iso

            if not isinstance(data, dict):
                return False
            techmod.save_roster(
                {
                    "version": 1,
                    "updated": str(data.get("updated") or now_iso()),
                    "admin_pin_hash": str(data.get("admin_pin_hash") or ""),
                    "technicians": list(data.get("technicians") or []),
                }
            )
            return True
        return techmod.apply_remote_roster(data)
    except Exception:
        return False


def _try_push_roster() -> bool:
    try:
        from carro.storage.remote import RemoteClient

        remote = RemoteClient()
        if not remote.enabled:
            return False
        remote.put_technicians(techmod.roster_for_sync())
        return True
    except Exception:
        return False


def sync_roster_with_server() -> str:
    """
    Pull if server roster is newer; push if local is newer / server empty.
    Syncs technicians, advisors, and suppliers. Returns combined status string.
    """
    try:
        from carro.core import advisors as advmod
        from carro.storage.remote import RemoteClient

        remote = RemoteClient()
        if not remote.enabled:
            return "skipped"

        def _sync_one(
            *,
            get_remote,
            put_remote,
            load_local,
            apply_remote,
            roster_for_sync,
            list_key: str,
        ) -> str:
            data = get_remote()
            if not isinstance(data, dict):
                return "error: bad server response"
            local = load_local()
            remote_updated = str(data.get("updated") or "")
            local_updated = str(local.get("updated") or "")
            remote_items = [t for t in (data.get(list_key) or []) if isinstance(t, dict)]
            local_items = list(local.get(list_key) or [])

            remote_newer = bool(remote_items) and (
                not local_items
                or (remote_updated and not local_updated)
                or (remote_updated and local_updated and remote_updated > local_updated)
            )
            if remote_newer:
                apply_remote(data)
                return "pulled"

            local_newer = bool(local_items) and (
                not remote_items
                or (local_updated and not remote_updated)
                or (local_updated and remote_updated and local_updated > remote_updated)
            )
            if local_newer:
                put_remote(roster_for_sync())
                return "pushed"
            return "ok"

        tech_status = _sync_one(
            get_remote=remote.get_technicians,
            put_remote=remote.put_technicians,
            load_local=techmod.load_roster,
            apply_remote=techmod.apply_remote_roster,
            roster_for_sync=techmod.roster_for_sync,
            list_key="technicians",
        )
        adv_status = _sync_one(
            get_remote=remote.get_advisors,
            put_remote=remote.put_advisors,
            load_local=advmod.load_roster,
            apply_remote=advmod.apply_remote_roster,
            roster_for_sync=advmod.roster_for_sync,
            list_key="advisors",
        )
        from carro.core import suppliers as suppliersmod

        sup_status = _sync_one(
            get_remote=remote.get_suppliers,
            put_remote=remote.put_suppliers,
            load_local=suppliersmod.load_roster,
            apply_remote=suppliersmod.replace_roster,
            roster_for_sync=suppliersmod.roster_for_sync,
            list_key="suppliers",
        )
        return f"techs={tech_status};advisors={adv_status};suppliers={sup_status}"
    except Exception as exc:
        return f"error: {exc}"
