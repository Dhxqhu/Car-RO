"""Full-screen vehicle history lookup form (Textual TUI)."""

from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from carro.core.touch_scroll import TouchFriendlyScroll
from textual.widgets import Button, Footer, Header, Input, Label, Static

from carro.core.textual_theme import CARRO_SCROLL_BINDINGS, CarroThemeApp


@dataclass
class HistoryQuery:
    vin: str = ""
    name: str = ""
    cancelled: bool = False


class HistoryForm(CarroThemeApp[HistoryQuery]):
    """VIN-first history lookup; name is fallback when VIN is empty or yields nothing."""

    CSS = """
    Screen { layout: vertical; }
    #body { height: 1fr; padding: 0 1; }
    .row { height: auto; margin-bottom: 0; }
    .label { width: 18; color: $text-muted; padding-top: 1; }
    Input { width: 1fr; }
    #actions {
        height: auto;
        dock: bottom;
        padding: 0 1 1 1;
        background: $surface;
    }
    #title {
        text-style: bold;
        padding: 1 1 0 1;
        color: $accent;
    }
    #hint { color: $text-muted; padding: 0 1 1 1; }
    """

    BINDINGS = [
        *CARRO_SCROLL_BINDINGS,
        Binding("ctrl+s", "submit", "Lookup", show=True, priority=True),
        Binding("ctrl+j", "submit", "Lookup", show=True, priority=True),
        Binding("enter", "submit", "Lookup", show=False),
        Binding("ctrl+q", "cancel", "Cancel", show=True, priority=True),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, *, default_vin: str = "", default_name: str = ""):
        super().__init__()
        self.default_vin = default_vin
        self.default_name = default_name

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(
            "Vehicle history    Tab move · Enter / Ctrl+J / Ctrl+S lookup · Ctrl+Q cancel",
            id="title",
        )
        yield Static(
            "VIN is preferred (exact, then partial). Name is used only if VIN is blank "
            "or finds nothing. Server archive is included when configured.",
            id="hint",
        )
        with TouchFriendlyScroll(id="body"):
            yield from self._row(
                "VIN",
                Input(
                    self.default_vin,
                    placeholder="Full VIN or last 8+ characters",
                    id="vin",
                ),
            )
            yield from self._row(
                "Customer name",
                Input(
                    self.default_name,
                    placeholder="Fallback if no VIN / no VIN hits",
                    id="name",
                ),
            )
        with Horizontal(id="actions"):
            yield Button("Lookup (Enter / Ctrl+J)", id="btn_go", variant="success")
            yield Button("Clear", id="btn_clear", variant="default")
            yield Button("Cancel (Ctrl+Q)", id="btn_cancel", variant="default")
        yield Footer()

    def _row(self, label: str, widget) -> ComposeResult:
        with Horizontal(classes="row"):
            yield Label(label, classes="label")
            yield widget

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#vin", Input).focus()

    def _read(self) -> HistoryQuery:
        return HistoryQuery(
            vin=self.query_one("#vin", Input).value.strip(),
            name=self.query_one("#name", Input).value.strip(),
        )

    def action_submit(self) -> None:
        self.exit(self._read())

    def action_cancel(self) -> None:
        self.exit(HistoryQuery(cancelled=True))

    @on(Input.Submitted)
    def _input_enter(self) -> None:
        self.action_submit()

    @on(Button.Pressed, "#btn_go")
    def _btn_go(self) -> None:
        self.action_submit()

    @on(Button.Pressed, "#btn_cancel")
    def _btn_cancel(self) -> None:
        self.action_cancel()

    @on(Button.Pressed, "#btn_clear")
    def _btn_clear(self) -> None:
        self.query_one("#vin", Input).value = ""
        self.query_one("#name", Input).value = ""
        self.query_one("#vin", Input).focus()


def run_history_form(*, default_vin: str = "", default_name: str = "") -> HistoryQuery:
    return (
        HistoryForm(default_vin=default_vin, default_name=default_name).run()
        or HistoryQuery(cancelled=True)
    )
