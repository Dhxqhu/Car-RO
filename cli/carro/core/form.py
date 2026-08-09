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

STATUS_OPTIONS = [("open", "open"), ("in_progress", "in_progress"), ("done", "done")]


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
    #complaint, #tech_notes {
        height: 8;
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
        yield Static(
            f"Repair Order  {o.id}    Tab/Shift+Tab move · Ctrl+S save · Ctrl+Q quit · F2 OBD",
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
                "Technician",
                Input(
                    o.technician_name,
                    id="technician_name",
                    placeholder="From login (editable)",
                ),
            )
            with Horizontal(classes="row"):
                yield Label("Status", classes="label")
                yield Select(
                    STATUS_OPTIONS,
                    value=o.status if o.status in {"open", "in_progress", "done"} else "open",
                    id="status",
                    allow_blank=False,
                )
            yield Label("Customer complaint / request", classes="label")
            yield TextArea(o.complaint or "", id="complaint")
            yield Label("Technician notes", classes="label")
            yield TextArea(o.tech_notes or "", id="tech_notes")
            yield Label("OBD snapshot (read/edit)", classes="label")
            yield TextArea(o.obd_snapshot or "", id="obd_snapshot")
            photo_n = len(o.photos)
            yield Static(
                f"Photos attached: {photo_n}  (use menu → Add photos, or: carro photo …)",
                id="hint",
            )
        with Horizontal(id="actions"):
            yield Button("Save (Ctrl+S)", id="btn_save", variant="success")
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
        status = self.query_one("#status", Select).value
        if isinstance(status, str):
            o.status = status
        o.complaint = self.query_one("#complaint", TextArea).text
        o.tech_notes = self.query_one("#tech_notes", TextArea).text
        o.obd_snapshot = self.query_one("#obd_snapshot", TextArea).text
        return o

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


def run_ro_form(
    order: RepairOrder,
    *,
    on_pull_obd: Callable[[RepairOrder], RepairOrder] | None = None,
) -> RepairOrder | None:
    """Open navigable form; returns updated order on save, or None if quit."""
    app = RepairOrderForm(order, on_pull_obd=on_pull_obd)
    return app.run()
