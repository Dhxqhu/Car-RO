"""Touch / pointer-friendly scrolling for Textual forms.

Many Wayland terminals (Hyprland + Kitty/foot/etc.) turn finger *taps* into
clicks but do not send mouse-wheel events for finger *swipes*. Drag-to-pan
fixes swipe scrolling for search / RO forms.
"""

from __future__ import annotations

from textual import events
from textual.containers import VerticalScroll
from textual.scrollbar import ScrollBar
from textual.widgets import Button


class TouchFriendlyScroll(VerticalScroll):
    """VerticalScroll with a wider scrollbar and drag-to-scroll (touch/mouse)."""

    # Keep default Textual scrollbar thickness (skinnier look)

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._drag_origin_y: int | None = None
        self._scroll_origin_y: float = 0.0
        self._dragging = False

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button != 1:
            return
        # Let real buttons / native scrollbar dragging keep normal behavior
        w = event.widget
        if isinstance(w, (Button, ScrollBar)):
            return
        self._drag_origin_y = event.screen_y
        self._scroll_origin_y = float(self.scroll_y)
        self._dragging = False

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._drag_origin_y is None:
            return
        dy = event.screen_y - self._drag_origin_y
        # Small movements = tap / focus field; start pan after a short drag
        if not self._dragging:
            if abs(dy) < 2:
                return
            self._dragging = True
            self.capture_mouse()
        # Swipe finger up → reveal content below (increase scroll_y)
        self.scroll_to(y=self._scroll_origin_y - dy, animate=False)
        event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self._drag_origin_y is None:
            return
        if self._dragging:
            self.release_mouse()
            event.stop()
        self._drag_origin_y = None
        self._dragging = False
