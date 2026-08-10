"""Full-screen navigable repair-order form (Textual TUI)."""

from __future__ import annotations

from typing import Callable

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from carro.core.touch_scroll import TouchFriendlyScroll
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    TextArea,
)

from carro.core.models import RepairOrder
from carro.core.textual_theme import CARRO_SCROLL_BINDINGS, CarroThemeApp
from carro.core.work_items import (
    apply_rollups,
    ensure_work_items_on_order,
    format_items_for_display,
)

STATUS_OPTIONS = [
    ("open", "open"),
    ("assigned", "assigned"),
    ("in_progress", "in_progress"),
    ("waiting_parts", "waiting on parts (advisor)"),
    ("waiting_customer", "awaiting customer approval"),
    ("done", "done — ready to bill"),
    ("billed_out", "billed out"),
]


class RepairOrderForm(CarroThemeApp[RepairOrder | None]):
    """nano/vim-style form: Tab between fields, Ctrl+S save, Ctrl+Q quit."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #body {
        height: 1fr;
        padding: 0 1;
    }
    .row {
        height: auto;
        margin-bottom: 0;
    }
    .label {
        width: 16;
        color: $text-muted;
        padding-top: 1;
    }
    Input, Select {
        width: 1fr;
    }
    TextArea {
        height: 6;
        width: 1fr;
    }
    #obd_snapshot {
        height: 14;
    }
    #work_items_list {
        color: $text;
        padding: 0 0 1 0;
    }
    #actions {
        height: auto;
        dock: bottom;
        padding: 0 1 1 1;
        background: $surface;
    }
    #hint {
        color: $text-muted;
        padding: 0 1;
    }
    #title {
        text-style: bold;
        padding: 1 1 0 1;
        color: $accent;
    }
    """

    BINDINGS = [
        *CARRO_SCROLL_BINDINGS,
        Binding("ctrl+s", "save", "Save", show=True),
        Binding("ctrl+q", "quit_form", "Quit", show=True),
        Binding("escape", "quit_form", "Quit", show=False),
        Binding("f2", "pull_obd", "Pull OBD", show=True),
        Binding("ctrl+w", "edit_work_items", "Work items", show=True),
    ]

    def __init__(
        self,
        order: RepairOrder,
        *,
        on_pull_obd: Callable[[RepairOrder], RepairOrder] | None = None,
    ):
        super().__init__()
        self.order = order
        self.on_pull_obd = on_pull_obd
        self._saved: RepairOrder | None = None

    def compose(self) -> ComposeResult:
        o = self.order
        yield Header(show_clock=True)
        ensure_work_items_on_order(o)
        yield Static(
            f"Repair Order  {o.id}    Ctrl+S save · Ctrl+W work items · F2 OBD · Ctrl+Q quit",
            id="title",
        )
        with TouchFriendlyScroll(id="body"):
            yield from self._row("First name", Input(o.first_name, id="first_name", placeholder="First"))
            yield from self._row("Last name", Input(o.last_name, id="last_name", placeholder="Last"))
            yield from self._row("Phone", Input(o.phone, id="phone", placeholder="Phone"))
            yield from self._row("Year", Input(o.year, id="year", placeholder="YYYY"))
            yield from self._row("Make", Input(o.make, id="make", placeholder="Make"))
            yield from self._row("Model", Input(o.model, id="model", placeholder="Model"))
            yield from self._row("VIN", Input(o.vin, id="vin", placeholder="17-char VIN"))
            yield from self._row("Mileage", Input(o.mileage, id="mileage", placeholder="Miles"))
            yield from self._row("Plate", Input(o.plate, id="plate", placeholder="Plate"))
            yield from self._row(
                "Last editor",
                Input(
                    o.technician_name,
                    id="technician_name",
                    placeholder="From login (editable)",
                ),
            )
            yield from self._row(
                "Assigned to",
                Input(
                    o.assigned_to_name,
                    id="assigned_to_name",
                    placeholder="Tech name (whole RO)",
                ),
            )
            with Horizontal(classes="row"):
                yield Label("Status", classes="label")
                yield Select(
                    STATUS_OPTIONS,
                    value=(
                        o.status
                        if o.status
                        in {
                            "open",
                            "assigned",
                            "in_progress",
                            "waiting_parts",
                            "waiting_customer",
                            "done",
                            "billed_out",
                        }
                        else "open"
                    ),
                    id="status",
                    allow_blank=False,
                )
            yield Label("Work items (concerns + diag) — Ctrl+W to edit", classes="label")
            yield Static(
                format_items_for_display(ensure_work_items_on_order(o)),
                id="work_items_list",
            )
            yield Label("OBD snapshot (read/edit)", classes="label")
            yield TextArea(o.obd_snapshot or "", id="obd_snapshot")
            photo_n = len(o.photos)
            yield Static(
                f"Photos attached: {photo_n}  (use menu → Add photos, or: carro photo …)",
                id="hint",
            )
        with Horizontal(id="actions"):
            yield Button("Save (Ctrl+S)", id="btn_save", variant="success")
            yield Button("Work items (Ctrl+W)", id="btn_items", variant="primary")
            yield Button("Pull OBD (F2)", id="btn_obd", variant="primary")
            yield Button("Quit (Ctrl+Q)", id="btn_quit", variant="default")
        yield Footer()

    def _row(self, label: str, widget) -> ComposeResult:
        with Horizontal(classes="row"):
            yield Label(label, classes="label")
            yield widget

    def _read_into_order(self) -> RepairOrder:
        o = self.order
        o.first_name = self.query_one("#first_name", Input).value.strip()
        o.last_name = self.query_one("#last_name", Input).value.strip()
        o.phone = self.query_one("#phone", Input).value.strip()
        o.year = self.query_one("#year", Input).value.strip()
        o.make = self.query_one("#make", Input).value.strip()
        o.model = self.query_one("#model", Input).value.strip()
        o.vin = self.query_one("#vin", Input).value.strip().upper()
        o.mileage = self.query_one("#mileage", Input).value.strip()
        o.plate = self.query_one("#plate", Input).value.strip()
        new_tech_name = self.query_one("#technician_name", Input).value.strip()
        if new_tech_name != (o.technician_name or ""):
            o.technician_name = new_tech_name
            # Name edited by hand — drop stable id unless still matching session
            from carro.core import technicians as techmod

            cur = techmod.current_technician()
            if cur and new_tech_name == cur.name:
                o.technician_id = cur.id
            else:
                o.technician_id = ""
        new_assigned = self.query_one("#assigned_to_name", Input).value.strip()
        if new_assigned != (o.assigned_to_name or ""):
            from carro.core import technicians as techmod
            from carro.core.assignment import assign_ro

            match = next(
                (t for t in techmod.list_technicians() if t.name == new_assigned),
                None,
            )
            assign_ro(
                o,
                tech_id=match.id if match else "",
                tech_name=new_assigned,
                set_status_assigned=bool(new_assigned),
            )
        status = self.query_one("#status", Select).value
        if isinstance(status, str):
            o.status = status
        o.obd_snapshot = self.query_one("#obd_snapshot", TextArea).text
        apply_rollups(o)
        return o

    def action_edit_work_items(self) -> None:
        # Exit to outer loop — nested Textual apps are unreliable.
        self.exit(("work_items", self._read_into_order()))

    def action_save(self) -> None:
        self._saved = self._read_into_order()
        self.notify(f"Saved {self._saved.id}", severity="information")
        self.exit(self._saved)

    def action_quit_form(self) -> None:
        self.exit(None)

    def action_pull_obd(self) -> None:
        if not self.on_pull_obd:
            self.notify("OBD pull not available", severity="warning")
            return
        order = self._read_into_order()
        try:
            updated = self.on_pull_obd(order)
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return
        self.order = updated
        self.query_one("#year", Input).value = updated.year
        self.query_one("#make", Input).value = updated.make
        self.query_one("#vin", Input).value = updated.vin
        self.query_one("#obd_snapshot", TextArea).load_text(updated.obd_snapshot or "")
        self.notify("Pulled OBD / Saved Codes", severity="information")

    @on(Button.Pressed, "#btn_save")
    def _btn_save(self) -> None:
        self.action_save()

    @on(Button.Pressed, "#btn_quit")
    def _btn_quit(self) -> None:
        self.action_quit_form()

    @on(Button.Pressed, "#btn_obd")
    def _btn_obd(self) -> None:
        self.action_pull_obd()

    @on(Button.Pressed, "#btn_items")
    def _btn_items(self) -> None:
        self.action_edit_work_items()


def run_ro_form(
    order: RepairOrder,
    *,
    on_pull_obd: Callable[[RepairOrder], RepairOrder] | None = None,
) -> RepairOrder | None:
    """Open navigable form; returns updated order on save, or None if quit."""
    from carro.core import technicians as techmod
    from carro.core.work_items_form import run_work_items_form

    current = order
    while True:
        result = RepairOrderForm(current, on_pull_obd=on_pull_obd).run()
        if result is None:
            return None
        if isinstance(result, tuple) and result and result[0] == "work_items":
            draft = result[1]
            tech = techmod.current_technician()
            actor = tech.name if tech else (draft.technician_name or "")
            actor_id = tech.id if tech else ""
            updated = run_work_items_form(
                draft, actor=actor, actor_id=actor_id, actor_role="tech"
            )
            current = updated if updated is not None else draft
            continue
        if isinstance(result, RepairOrder):
            return result
        return None
