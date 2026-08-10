"""Textual editor for RO work items (itemized concerns + notes)."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static, TextArea

from carro.core.models import RepairOrder
from carro.core.textual_theme import CARRO_SCROLL_BINDINGS, CarroThemeApp
from carro.core.touch_scroll import TouchFriendlyScroll
from carro.core.work_items import (
    WORK_ITEM_STATUSES,
    ensure_work_items_on_order,
    format_items_for_display,
    remove_work_item,
    upsert_work_item,
)

STATUS_OPTIONS = [(s, s) for s in WORK_ITEM_STATUSES]


class WorkItemsForm(CarroThemeApp[RepairOrder | None]):
    CSS = """
    Screen { layout: vertical; }
    #body { height: 1fr; padding: 0 1; }
    .label { color: $text-muted; margin-top: 1; }
    TextArea { height: 5; width: 1fr; }
    #list { color: $text; padding: 1 0; }
    #actions { height: auto; dock: bottom; padding: 0 1 1 1; background: $surface; }
    #title { text-style: bold; padding: 1 1 0 1; color: $accent; }
    """

    BINDINGS = [
        *CARRO_SCROLL_BINDINGS,
        Binding("ctrl+s", "done", "Done", show=True),
        Binding("ctrl+q", "cancel", "Cancel", show=True),
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+n", "add_item", "Add", show=True),
    ]

    def __init__(self, order: RepairOrder, *, actor: str = "", actor_role: str = "tech"):
        super().__init__()
        self.order = order
        self.actor = actor
        self.actor_role = actor_role
        self._done = False
        ensure_work_items_on_order(self.order)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(
            f"Work items · {self.order.id} · Ctrl+N add · Ctrl+S done · Esc cancel",
            id="title",
        )
        with TouchFriendlyScroll(id="body"):
            yield Static(format_items_for_display(ensure_work_items_on_order(self.order)), id="list")
            yield Label("Item # (blank = new)", classes="label")
            yield Input(placeholder="1 or WI-001", id="pick")
            yield Label("Concern / customer request", classes="label")
            yield TextArea("", id="concern")
            yield Label("Diagnosis / tech notes for this item", classes="label")
            yield TextArea("", id="notes")
            with Horizontal():
                yield Label("Status", classes="label")
                yield Select(STATUS_OPTIONS, value="open", id="status", allow_blank=False)
            yield Label("Assigned tech (name; blank = unassigned)", classes="label")
            yield Input(placeholder="Tech name for this item only", id="assigned_to_name")
            yield Label("Quick paste (creates one new item from concern text)", classes="label")
            yield TextArea("", id="quick_paste")
        with Horizontal(id="actions"):
            yield Button("Load #", id="btn_load", variant="primary")
            yield Button("Save item", id="btn_save_item", variant="success")
            yield Button("Add blank", id="btn_add", variant="default")
            yield Button("Delete item", id="btn_del", variant="error")
            yield Button("Done (Ctrl+S)", id="btn_done", variant="success")
            yield Button("Cancel", id="btn_cancel", variant="default")
        yield Footer()

    def _refresh_list(self) -> None:
        self.query_one("#list", Static).update(
            format_items_for_display(ensure_work_items_on_order(self.order))
        )

    def _resolve_pick(self) -> str | None:
        raw = self.query_one("#pick", Input).value.strip()
        if not raw:
            return None
        items = ensure_work_items_on_order(self.order)
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(items):
                return items[idx - 1].id
            return None
        return raw

    def _load_pick(self) -> None:
        wid = self._resolve_pick()
        items = ensure_work_items_on_order(self.order)
        target = next((w for w in items if w.id == wid), None) if wid else None
        if not target:
            self.notify("Pick a valid item # or id", severity="warning")
            return
        self.query_one("#pick", Input).value = target.id
        self.query_one("#concern", TextArea).load_text(target.concern or "")
        self.query_one("#notes", TextArea).load_text(target.notes or "")
        self.query_one("#status", Select).value = (
            target.status if target.status in WORK_ITEM_STATUSES else "open"
        )
        self.query_one("#assigned_to_name", Input).value = target.assigned_to_name or ""
        self.notify(f"Loaded {target.id}", severity="information")

    def _resolve_assignee(self, name: str) -> tuple[str, str]:
        name = (name or "").strip()
        if not name:
            return "", ""
        from carro.core import technicians as techmod

        match = next((t for t in techmod.list_technicians() if t.name == name), None)
        return (match.id if match else "", name)

    def _save_item(self) -> None:
        quick = self.query_one("#quick_paste", TextArea).text.strip()
        if quick:
            upsert_work_item(
                self.order,
                concern=quick,
                notes="",
                status="open",
                actor=self.actor,
                actor_role=self.actor_role,
            )
            self.query_one("#quick_paste", TextArea).load_text("")
            self._refresh_list()
            self.notify("Added item from paste", severity="information")
            return
        wid = self._resolve_pick()
        concern = self.query_one("#concern", TextArea).text
        notes = self.query_one("#notes", TextArea).text
        status = self.query_one("#status", Select).value
        st = status if isinstance(status, str) else "open"
        aid, aname = self._resolve_assignee(
            self.query_one("#assigned_to_name", Input).value
        )
        item = upsert_work_item(
            self.order,
            item_id=wid,
            concern=concern,
            notes=notes,
            status=st,
            assigned_to_id=aid,
            assigned_to_name=aname,
            actor=self.actor,
            actor_role=self.actor_role,
        )
        self.query_one("#pick", Input).value = item.id
        self._refresh_list()
        self.notify(f"Saved {item.id}", severity="information")

    def action_add_item(self) -> None:
        item = upsert_work_item(
            self.order,
            concern="",
            notes="",
            status="open",
            actor=self.actor,
            actor_role=self.actor_role,
        )
        self.query_one("#pick", Input).value = item.id
        self.query_one("#concern", TextArea).load_text("")
        self.query_one("#notes", TextArea).load_text("")
        self._refresh_list()
        self.notify(f"Added {item.id}", severity="information")

    def action_done(self) -> None:
        from carro.core.work_items import apply_rollups

        apply_rollups(self.order)
        self._done = True
        self.exit(self.order)

    def action_cancel(self) -> None:
        self.exit(None)

    @on(Button.Pressed, "#btn_load")
    def _btn_load(self) -> None:
        self._load_pick()

    @on(Button.Pressed, "#btn_save_item")
    def _btn_save(self) -> None:
        self._save_item()

    @on(Button.Pressed, "#btn_add")
    def _btn_add(self) -> None:
        self.action_add_item()

    @on(Button.Pressed, "#btn_del")
    def _btn_del(self) -> None:
        wid = self._resolve_pick()
        if not wid:
            self.notify("Load or enter an item id first", severity="warning")
            return
        if remove_work_item(self.order, wid):
            self.query_one("#pick", Input).value = ""
            self.query_one("#concern", TextArea).load_text("")
            self.query_one("#notes", TextArea).load_text("")
            self._refresh_list()
            self.notify(f"Deleted {wid}", severity="information")
        else:
            self.notify("Item not found", severity="warning")

    @on(Button.Pressed, "#btn_done")
    def _btn_done(self) -> None:
        self.action_done()

    @on(Button.Pressed, "#btn_cancel")
    def _btn_cancel(self) -> None:
        self.action_cancel()


def run_work_items_form(
    order: RepairOrder,
    *,
    actor: str = "",
    actor_role: str = "tech",
) -> RepairOrder | None:
    return WorkItemsForm(order, actor=actor, actor_role=actor_role).run()
