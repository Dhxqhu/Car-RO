"""Full-screen navigable RO search form (Textual TUI)."""

from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
)


@dataclass
class SearchQuery:
    query: str = ""
    make: str = ""
    model: str = ""
    year: str = ""
    name: str = ""
    vin: str = ""
    plate: str = ""
    status: str = ""
    remote: bool = False
    cancelled: bool = False


STATUS_OPTIONS = [
    ("(any)", ""),
    ("open", "open"),
    ("in_progress", "in_progress"),
    ("done", "done"),
]


class SearchForm(App[SearchQuery]):
    """Tab between search fields; checkbox for server/extended search."""

    CSS = """
    Screen { layout: vertical; }
    #body { height: 1fr; padding: 0 1; }
    .row { height: auto; margin-bottom: 0; }
    .label { width: 18; color: $text-muted; padding-top: 1; }
    Input, Select { width: 1fr; }
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
    #remote_row { padding: 1 0; }
    """

    BINDINGS = [
        Binding("ctrl+s", "submit", "Search", show=True, priority=True),
        Binding("ctrl+j", "submit", "Search", show=True, priority=True),
        Binding("enter", "submit", "Search", show=False),
        Binding("ctrl+q", "cancel", "Cancel", show=True, priority=True),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, *, default_remote: bool = False):
        super().__init__()
        self.default_remote = default_remote

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(
            "Search repair orders    Tab move · Enter / Ctrl+J / Ctrl+S search · Ctrl+Q cancel",
            id="title",
        )
        yield Static(
            "Free text matches name, make, model, VIN, complaint, notes, etc.",
            id="hint",
        )
        with VerticalScroll(id="body"):
            yield from self._row(
                "Free text",
                Input(placeholder="e.g. bronco, smith, P0420…", id="query"),
            )
            yield from self._row("Customer name", Input(placeholder="First or last", id="name"))
            yield from self._row("Make", Input(placeholder="Ford", id="make"))
            yield from self._row("Model", Input(placeholder="Escape", id="model"))
            yield from self._row("Year", Input(placeholder="2023", id="year"))
            yield from self._row("VIN", Input(placeholder="partial OK", id="vin"))
            yield from self._row("Plate", Input(placeholder="Plate", id="plate"))
            with Horizontal(classes="row"):
                yield Label("Status", classes="label")
                yield Select(STATUS_OPTIONS, value="", id="status", allow_blank=False)
            with Horizontal(id="remote_row", classes="row"):
                yield Label("Extended", classes="label")
                yield Checkbox(
                    "Also search server (older ROs past local cache)",
                    value=self.default_remote,
                    id="remote",
                )
        with Horizontal(id="actions"):
            yield Button("Search (Enter / Ctrl+J)", id="btn_search", variant="success")
            yield Button("Clear", id="btn_clear", variant="default")
            yield Button("Cancel (Ctrl+Q)", id="btn_cancel", variant="default")
        yield Footer()

    def _row(self, label: str, widget) -> ComposeResult:
        with Horizontal(classes="row"):
            yield Label(label, classes="label")
            yield widget

    def _read(self) -> SearchQuery:
        status = self.query_one("#status", Select).value
        if not isinstance(status, str):
            status = ""
        return SearchQuery(
            query=self.query_one("#query", Input).value.strip(),
            name=self.query_one("#name", Input).value.strip(),
            make=self.query_one("#make", Input).value.strip(),
            model=self.query_one("#model", Input).value.strip(),
            year=self.query_one("#year", Input).value.strip(),
            vin=self.query_one("#vin", Input).value.strip(),
            plate=self.query_one("#plate", Input).value.strip(),
            status=status,
            remote=self.query_one("#remote", Checkbox).value,
        )

    def action_submit(self) -> None:
        self.exit(self._read())

    def action_cancel(self) -> None:
        q = SearchQuery(cancelled=True)
        self.exit(q)

    @on(Input.Submitted)
    def _input_enter(self) -> None:
        """Plain Enter inside a field also runs search."""
        self.action_submit()

    @on(Button.Pressed, "#btn_search")
    def _btn_search(self) -> None:
        self.action_submit()

    @on(Button.Pressed, "#btn_cancel")
    def _btn_cancel(self) -> None:
        self.action_cancel()

    @on(Button.Pressed, "#btn_clear")
    def _btn_clear(self) -> None:
        for wid in ("query", "name", "make", "model", "year", "vin", "plate"):
            self.query_one(f"#{wid}", Input).value = ""
        self.query_one("#status", Select).value = ""
        self.query_one("#remote", Checkbox).value = self.default_remote
        self.query_one("#query", Input).focus()


def run_search_form(*, default_remote: bool = False) -> SearchQuery:
    return SearchForm(default_remote=default_remote).run() or SearchQuery(cancelled=True)
