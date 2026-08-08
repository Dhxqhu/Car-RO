"""Persist Textual TUI theme across Car-RO forms."""

from __future__ import annotations

from typing import TypeVar

from textual.app import App

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


class CarroThemeApp(App[T]):
    """Textual App that loads/saves theme from ~/.config/carro/config.toml."""

    def on_mount(self) -> None:
        self.theme = get_textual_theme()
        self._carro_theme_ready = True

    def watch_theme(self, theme: str) -> None:
        if getattr(self, "_carro_theme_ready", False):
            set_textual_theme(theme)
