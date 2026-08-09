"""Persist Textual TUI theme across Car-RO forms."""

from __future__ import annotations

from typing import TypeVar

from textual.app import App
from textual.binding import Binding
from textual.containers import VerticalScroll

from carro.config import load_config, save_config

DEFAULT_THEME = "ansi-dark"

T = TypeVar("T")


def get_textual_theme() -> str:
    cfg = load_config()
    raw = str(cfg.get("textual_theme") or DEFAULT_THEME).strip()
    return raw or DEFAULT_THEME


def set_textual_theme(name: str) -> None:
    name = (name or DEFAULT_THEME).strip() or DEFAULT_THEME
    cfg = load_config()
    if str(cfg.get("textual_theme") or "") == name:
        return
    cfg["textual_theme"] = name
    save_config(cfg)


# Include in each form's BINDINGS — subclass BINDINGS replace the parent list.
CARRO_SCROLL_BINDINGS = [
    Binding("pageup", "carro_page_up", "Page up", show=False),
    Binding("pagedown", "carro_page_down", "Page down", show=False),
]


class CarroThemeApp(App[T]):
    """Textual App that loads/saves theme from ~/.config/carro/config.toml."""

    # Stronger wheel / trackpad steps (helps when the terminal maps touch oddly)
    scroll_sensitivity_y = 2.5

    def on_mount(self) -> None:
        self.theme = get_textual_theme()
        self._carro_theme_ready = True

    def watch_theme(self, theme: str) -> None:
        if getattr(self, "_carro_theme_ready", False):
            set_textual_theme(theme)

    def _carro_body_scroll(self) -> VerticalScroll | None:
        try:
            return self.query_one("#body", VerticalScroll)
        except Exception:
            return None

    def action_carro_page_up(self) -> None:
        body = self._carro_body_scroll()
        if body is not None:
            body.scroll_page_up(animate=False)

    def action_carro_page_down(self) -> None:
        body = self._carro_body_scroll()
        if body is not None:
            body.scroll_page_down(animate=False)
