"""CLI inbox / send for shop person-to-person messages."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from carro.core import advisors as advmod
from carro.core import technicians as techmod
from carro.storage.remote import RemoteClient

CONSOLE = Console()


def _actor(*, prefer: str | None = None) -> tuple[str, str, str]:
    tech = techmod.current_technician()
    adv = advmod.current_advisor()
    pref = (prefer or "").strip().lower()
    if pref in ("technician", "tech"):
        if tech:
            return tech.id, tech.name, "technician"
        if adv:
            return adv.id, adv.name, "advisor"
    elif pref == "advisor":
        if adv:
            return adv.id, adv.name, "advisor"
        if tech:
            return tech.id, tech.name, "technician"
    else:
        if tech and not adv:
            return tech.id, tech.name, "technician"
        if adv and not tech:
            return adv.id, adv.name, "advisor"
        if tech:
            return tech.id, tech.name, "technician"
        if adv:
            return adv.id, adv.name, "advisor"
    raise RuntimeError("Log in first (carro tech login or carroadviser login)")


def _remote() -> RemoteClient:
    remote = RemoteClient()
    if not remote.enabled:
        raise RuntimeError(
            "Shop messaging needs server_url — messages are shared across bay PCs."
        )
    return remote


def _people(exclude_id: str) -> list[dict]:
    rows: list[dict] = []
    for t in techmod.list_technicians():
        if t.id != exclude_id:
            rows.append({"id": t.id, "name": t.name, "role": "technician"})
    for a in advmod.list_advisors():
        if a.id != exclude_id:
            rows.append({"id": a.id, "name": a.name, "role": "advisor"})
    rows.sort(key=lambda p: (p["role"], p["name"].lower()))
    return rows


def _print_messages(messages: list[dict], *, sent: bool = False) -> None:
    if not messages:
        CONSOLE.print("[dim]No messages.[/]")
        return
    table = Table(title="Sent" if sent else "Inbox")
    table.add_column("Id", style="cyan")
    table.add_column("When")
    table.add_column("Who")
    table.add_column("Tags")
    table.add_column("Body")
    table.add_column("Read")
    for m in messages:
        who = (
            f"→ {m.get('to_name')} ({m.get('to_role')})"
            if sent
            else f"← {m.get('from_name')} ({m.get('from_role')})"
        )
        tags = " ".join(
            x for x in (m.get("ro_id") or "", m.get("work_item_id") or "") if x
        )
        table.add_row(
            str(m.get("id") or ""),
            str(m.get("at") or "")[:19],
            who,
            tags or "—",
            (str(m.get("body") or "")[:80]),
            "yes" if m.get("read_at") else ("—" if sent else "no"),
        )
    CONSOLE.print(table)


def run_messages_menu() -> None:
    while True:
        CONSOLE.clear()
        me_id, me_name, me_role = _actor()
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[bold cyan]1[/]", "Inbox")
        table.add_row("[bold cyan]2[/]", "Unread only")
        table.add_row("[bold cyan]3[/]", "Sent")
        table.add_row("[bold cyan]4[/]", "Send message")
        table.add_row("[bold cyan]5[/]", "Mark message read")
        table.add_row("[bold cyan]6[/]", "Renotify unread sent message")
        table.add_row("[bold cyan]b[/]", "Back")
        CONSOLE.print(
            Panel(
                table,
                title="Messages",
                subtitle=f"{me_name} ({me_role})",
                border_style="cyan",
            )
        )
        choice = Prompt.ask("Choice", default="1").strip().lower()
        if choice in {"b", "q", "back"}:
            return
        try:
            remote = _remote()
            if choice == "1":
                data = remote.list_messages(for_id=me_id)
                CONSOLE.print(f"[dim]Unread: {data.get('unread', 0)}[/]")
                _print_messages(list(data.get("messages") or []))
            elif choice == "2":
                data = remote.list_messages(for_id=me_id, unread=True)
                _print_messages(list(data.get("messages") or []))
            elif choice == "3":
                data = remote.list_sent_messages(from_id=me_id)
                _print_messages(list(data.get("messages") or []), sent=True)
            elif choice == "4":
                _send_flow(remote, me_id, me_name, me_role)
            elif choice == "5":
                mid = Prompt.ask("Message id").strip()
                if not mid.isdigit():
                    raise ValueError("Need numeric message id")
                remote.mark_message_read(int(mid), for_id=me_id)
                CONSOLE.print("[green]Marked read[/]")
            elif choice == "6":
                mid = Prompt.ask("Sent message id").strip()
                if not mid.isdigit():
                    raise ValueError("Need numeric message id")
                remote.renotify_message(int(mid), from_id=me_id)
                CONSOLE.print("[green]Renotify sent[/]")
            else:
                CONSOLE.print("[yellow]Unknown option[/]")
                continue
        except Exception as exc:
            CONSOLE.print(f"[red]{exc}[/]")
        Prompt.ask("[dim]Press Enter[/]", default="")


def _send_flow(remote: RemoteClient, me_id: str, me_name: str, me_role: str) -> None:
    people = _people(me_id)
    if not people:
        raise RuntimeError("No other people on the roster to message")
    for i, p in enumerate(people, 1):
        CONSOLE.print(
            f"  [cyan]{i}[/] {p['name']} ({'advisor' if p['role'] == 'advisor' else 'tech'})"
        )
    raw = Prompt.ask("Person #", default="1").strip()
    if not raw.isdigit() or not (1 <= int(raw) <= len(people)):
        raise ValueError("Invalid person #")
    person = people[int(raw) - 1]
    body = Prompt.ask("Message").strip()
    if not body:
        raise ValueError("Empty message")
    ro_id = ""
    work_item_id = ""
    if Confirm.ask("Tag an RO / work item?", default=False):
        ro_id = Prompt.ask("RO id", default="").strip()
        work_item_id = Prompt.ask("Work item id (optional)", default="").strip()
    result = remote.send_message(
        {
            "body": body,
            "from_id": me_id,
            "from_name": me_name,
            "from_role": me_role,
            "to_id": person["id"],
            "to_name": person["name"],
            "to_role": person["role"],
            "ro_id": ro_id,
            "work_item_id": work_item_id,
        }
    )
    mid = (result.get("message") or {}).get("id")
    CONSOLE.print(f"[green]Sent[/] message {mid} → {person['name']}")
