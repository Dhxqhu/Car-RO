"""Textual editor for RO work items (itemized concerns + notes + parts)."""

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
    PART_STATUSES,
    WORK_ITEM_STATUSES,
    WORK_ITEM_TYPES,
    WORK_ITEM_TYPE_LABELS,
    add_part,
    ensure_work_items_on_order,
    format_items_for_display,
    part_status_label,
    remove_part,
    remove_work_item,
    set_part_status,
    update_part,
    upsert_work_item,
)

STATUS_OPTIONS = [(s, s) for s in WORK_ITEM_STATUSES]
TYPE_OPTIONS = [(WORK_ITEM_TYPE_LABELS[t], t) for t in WORK_ITEM_TYPES]
PART_STATUS_OPTIONS = [(part_status_label(s), s) for s in PART_STATUSES]


def _format_parts(order: RepairOrder, item_id: str | None) -> str:
    if not item_id:
        return "(load a work item to manage parts)"
    items = ensure_work_items_on_order(order)
    target = next((w for w in items if w.id == item_id), None)
    if not target:
        return "(work item not found)"
    parts = target.parts or []
    if not parts:
        return "(no parts on this item)"
    lines = []
    for i, p in enumerate(parts, 1):
        pn = (p.get("part_number") or "").strip() or "—"
        mfr = (p.get("manufacturer") or "").strip() or "—"
        brand = (p.get("brand") or "").strip()
        desc = (p.get("description") or "—").replace("\n", " ")
        if len(desc) > 40:
            desc = desc[:37] + "…"
        wrong = " · wrong note" if (p.get("wrong_note") or "").strip() else ""
        brand_bit = f" · {brand}" if brand else ""
        lines.append(
            f"  {i}. {p.get('id')} [{part_status_label(p.get('status'))}] "
            f"{desc} · PN {pn}{brand_bit} · {mfr}{wrong}"
        )
    return "\n".join(lines)


class WorkItemsForm(CarroThemeApp[RepairOrder | None]):
    CSS = """
    Screen { layout: vertical; }
    #body { height: 1fr; padding: 0 1; }
    .label { color: $text-muted; margin-top: 1; }
    TextArea { height: 4; width: 1fr; }
    #private_notes { height: 3; }
    #list { color: $text; padding: 1 0; }
    #parts_list { color: $text; padding: 0 0 1 0; }
    #actions { height: auto; dock: bottom; padding: 0 1 1 1; background: $surface; }
    #title { text-style: bold; padding: 1 1 0 1; color: $accent; }
    """

    BINDINGS = [
        *CARRO_SCROLL_BINDINGS,
        Binding("ctrl+s", "done", "Done", show=True),
        Binding("ctrl+q", "cancel", "Cancel", show=True),
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+n", "add_item", "New", show=True),
    ]

    def __init__(
        self,
        order: RepairOrder,
        *,
        actor: str = "",
        actor_id: str = "",
        actor_role: str = "tech",
    ):
        super().__init__()
        self.order = order
        self.actor = actor
        self.actor_id = actor_id
        self.actor_role = actor_role
        self._done = False
        ensure_work_items_on_order(self.order)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(
            f"Work items · {self.order.id} · Ctrl+N new · Ctrl+S done · Esc cancel",
            id="title",
        )
        with TouchFriendlyScroll(id="body"):
            yield Static(format_items_for_display(ensure_work_items_on_order(self.order)), id="list")
            yield Label("Item # (blank = new)", classes="label")
            yield Input(placeholder="1 or WI-001", id="pick")
            yield Label("Type (required for new items)", classes="label")
            yield Select(TYPE_OPTIONS, id="item_type", allow_blank=True, prompt="Choose type…")
            yield Label("Concern / customer request", classes="label")
            yield TextArea("", id="concern")
            yield Label("Diagnosis / tech notes for this item (customer PDF)", classes="label")
            yield TextArea("", id="notes")
            yield Label("Private shop notes (techs only — never on customer PDF)", classes="label")
            yield TextArea("", id="private_notes")
            with Horizontal():
                yield Label("Status", classes="label")
                yield Select(STATUS_OPTIONS, value="open", id="status", allow_blank=False)
            yield Label(
                "Attribution is automatic — concern = who enters it; notes = logged-in tech",
                classes="label",
            )
            yield Label("Quick paste (creates one new item from concern text)", classes="label")
            yield TextArea("", id="quick_paste")
            yield Label("Parts for loaded item", classes="label")
            yield Static(_format_parts(self.order, None), id="parts_list")
            yield Label("Part # (blank = new)", classes="label")
            yield Input(placeholder="1 or PN-001", id="part_pick")
            yield Label("Part description", classes="label")
            yield Input(placeholder="Brake pad set", id="part_desc")
            yield Label("Part number (optional)", classes="label")
            yield Input(placeholder="PN / OEM", id="part_number")
            yield Label("Brand / cross (optional)", classes="label")
            yield Input(placeholder="Denso, Motorcraft…", id="part_brand")
            yield Label("Manufacturer (defaults to vehicle make)", classes="label")
            yield Input(placeholder=self.order.make or "e.g. Ford", id="part_mfr")
            with Horizontal():
                yield Label("Part status", classes="label")
                yield Select(
                    PART_STATUS_OPTIONS,
                    value="new_request",
                    id="part_status",
                    allow_blank=False,
                )
            yield Label("Wrong-part note (when marking received wrong)", classes="label")
            yield Input(placeholder="Wrong size / wrong brand…", id="part_wrong_note")
        with Horizontal(id="actions"):
            yield Button("Load #", id="btn_load", variant="primary")
            yield Button("Save item", id="btn_save_item", variant="success")
            yield Button("New blank", id="btn_add", variant="default")
            yield Button("Delete item", id="btn_del", variant="error")
            yield Button("Load part", id="btn_part_load", variant="primary")
            yield Button("Add/save part", id="btn_part_save", variant="success")
            yield Button("Delete part", id="btn_part_del", variant="error")
            yield Button("Done (Ctrl+S)", id="btn_done", variant="success")
            yield Button("Cancel", id="btn_cancel", variant="default")
        yield Footer()

    def _current_item_id(self) -> str | None:
        return self._resolve_pick()

    def _refresh_list(self) -> None:
        self.query_one("#list", Static).update(
            format_items_for_display(ensure_work_items_on_order(self.order))
        )
        self._refresh_parts()

    def _refresh_parts(self) -> None:
        self.query_one("#parts_list", Static).update(
            _format_parts(self.order, self._current_item_id())
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

    def _resolve_part_pick(self, item_id: str) -> str | None:
        raw = self.query_one("#part_pick", Input).value.strip()
        if not raw:
            return None
        items = ensure_work_items_on_order(self.order)
        target = next((w for w in items if w.id == item_id), None)
        if not target:
            return None
        parts = target.parts or []
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(parts):
                return str(parts[idx - 1].get("id") or "")
            return None
        return raw

    def _selected_type(self) -> str | None:
        val = self.query_one("#item_type", Select).value
        return val if isinstance(val, str) and val in WORK_ITEM_TYPES else None

    def _clear_part_fields(self) -> None:
        self.query_one("#part_pick", Input).value = ""
        self.query_one("#part_desc", Input).value = ""
        self.query_one("#part_number", Input).value = ""
        self.query_one("#part_brand", Input).value = ""
        self.query_one("#part_mfr", Input).value = self.order.make or ""
        self.query_one("#part_status", Select).value = "new_request"
        self.query_one("#part_wrong_note", Input).value = ""

    def _load_pick(self) -> None:
        wid = self._resolve_pick()
        items = ensure_work_items_on_order(self.order)
        target = next((w for w in items if w.id == wid), None) if wid else None
        if not target:
            self.notify("Pick a valid item # or id", severity="warning")
            return
        self.query_one("#pick", Input).value = target.id
        self.query_one("#item_type", Select).value = (
            target.item_type if target.item_type in WORK_ITEM_TYPES else "other"
        )
        self.query_one("#concern", TextArea).load_text(target.concern or "")
        self.query_one("#notes", TextArea).load_text(target.notes or "")
        self.query_one("#private_notes", TextArea).load_text(target.private_notes or "")
        self.query_one("#status", Select).value = (
            target.status if target.status in WORK_ITEM_STATUSES else "open"
        )
        self._clear_part_fields()
        self._refresh_parts()
        self.notify(f"Loaded {target.id}", severity="information")

    def _save_item(self) -> None:
        quick = self.query_one("#quick_paste", TextArea).text.strip()
        item_type = self._selected_type()
        if quick:
            if not item_type:
                self.notify("Choose a type before quick paste", severity="warning")
                return
            try:
                upsert_work_item(
                    self.order,
                    concern=quick,
                    notes="",
                    item_type=item_type,
                    status="open",
                    actor=self.actor,
                    actor_id=self.actor_id,
                    actor_role=self.actor_role,
                    require_item_type=True,
                )
            except ValueError as exc:
                self.notify(str(exc), severity="error")
                return
            self.query_one("#quick_paste", TextArea).load_text("")
            self._refresh_list()
            self.notify("Added item from paste", severity="information")
            return
        wid = self._resolve_pick()
        if not wid and not item_type:
            self.notify("Choose a work item type for new items", severity="warning")
            return
        concern = self.query_one("#concern", TextArea).text
        notes = self.query_one("#notes", TextArea).text
        private_notes = self.query_one("#private_notes", TextArea).text
        status = self.query_one("#status", Select).value
        st = status if isinstance(status, str) else "open"
        try:
            item = upsert_work_item(
                self.order,
                item_id=wid,
                concern=concern,
                notes=notes,
                private_notes=private_notes,
                item_type=item_type,
                status=st,
                actor=self.actor,
                actor_id=self.actor_id,
                actor_role=self.actor_role,
                require_item_type=not wid,
            )
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        self.query_one("#pick", Input).value = item.id
        self._refresh_list()
        self.notify(f"Saved {item.id}", severity="information")

    def _save_part(self) -> None:
        wid = self._resolve_pick()
        if not wid:
            self.notify("Load or save a work item first", severity="warning")
            return
        desc = self.query_one("#part_desc", Input).value.strip()
        pn = self.query_one("#part_number", Input).value.strip()
        brand = self.query_one("#part_brand", Input).value.strip()
        mfr_raw = self.query_one("#part_mfr", Input).value.strip()
        mfr = mfr_raw if mfr_raw else None
        status = self.query_one("#part_status", Select).value
        st = status if isinstance(status, str) else "new_request"
        wrong = self.query_one("#part_wrong_note", Input).value.strip()
        part_id = self._resolve_part_pick(wid)
        try:
            if not part_id:
                if not desc:
                    self.notify("Part description required", severity="warning")
                    return
                part = add_part(
                    self.order,
                    wid,
                    description=desc,
                    part_number=pn,
                    manufacturer=mfr,
                    brand=brand,
                )
                if st != "new_request":
                    set_part_status(
                        self.order,
                        wid,
                        str(part["id"]),
                        st,
                        wrong_note=wrong,
                        actor=self.actor,
                        actor_id=self.actor_id,
                    )
                self.query_one("#part_pick", Input).value = str(part["id"])
                self.notify(f"Added {part['id']}", severity="information")
            else:
                update_part(
                    self.order,
                    wid,
                    part_id,
                    description=desc,
                    part_number=pn,
                    manufacturer=mfr_raw if mfr_raw else (self.order.make or ""),
                    brand=brand,
                )
                set_part_status(
                    self.order,
                    wid,
                    part_id,
                    st,
                    wrong_note=wrong,
                    actor=self.actor,
                    actor_id=self.actor_id,
                )
                self.notify(f"Updated {part_id}", severity="information")
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        self._refresh_list()

    def _load_part(self) -> None:
        wid = self._resolve_pick()
        if not wid:
            self.notify("Load a work item first", severity="warning")
            return
        part_id = self._resolve_part_pick(wid)
        items = ensure_work_items_on_order(self.order)
        target = next((w for w in items if w.id == wid), None)
        if not target or not part_id:
            self.notify("Pick a valid part # or id", severity="warning")
            return
        part = next((p for p in (target.parts or []) if str(p.get("id")) == part_id), None)
        if not part:
            self.notify("Part not found", severity="warning")
            return
        self.query_one("#part_pick", Input).value = str(part.get("id") or "")
        self.query_one("#part_desc", Input).value = str(part.get("description") or "")
        self.query_one("#part_number", Input).value = str(part.get("part_number") or "")
        self.query_one("#part_brand", Input).value = str(part.get("brand") or "")
        self.query_one("#part_mfr", Input).value = str(
            part.get("manufacturer") or self.order.make or ""
        )
        pst = str(part.get("status") or "new_request")
        self.query_one("#part_status", Select).value = (
            pst if pst in PART_STATUSES else "new_request"
        )
        self.query_one("#part_wrong_note", Input).value = ""
        self.notify(f"Loaded {part_id}", severity="information")

    def action_add_item(self) -> None:
        self.query_one("#pick", Input).value = ""
        self.query_one("#item_type", Select).value = Select.BLANK
        self.query_one("#concern", TextArea).load_text("")
        self.query_one("#notes", TextArea).load_text("")
        self.query_one("#private_notes", TextArea).load_text("")
        self.query_one("#status", Select).value = "open"
        self._clear_part_fields()
        self._refresh_parts()
        self.notify("New item — choose type, then Save", severity="information")

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
            self.query_one("#private_notes", TextArea).load_text("")
            self.query_one("#item_type", Select).value = Select.BLANK
            self._clear_part_fields()
            self._refresh_list()
            self.notify(f"Deleted {wid}", severity="information")
        else:
            self.notify("Item not found", severity="warning")

    @on(Button.Pressed, "#btn_part_load")
    def _btn_part_load(self) -> None:
        self._load_part()

    @on(Button.Pressed, "#btn_part_save")
    def _btn_part_save(self) -> None:
        self._save_part()

    @on(Button.Pressed, "#btn_part_del")
    def _btn_part_del(self) -> None:
        wid = self._resolve_pick()
        if not wid:
            self.notify("Load a work item first", severity="warning")
            return
        part_id = self._resolve_part_pick(wid)
        if not part_id:
            self.notify("Load or enter a part id first", severity="warning")
            return
        if remove_part(self.order, wid, part_id):
            self._clear_part_fields()
            self._refresh_list()
            self.notify(f"Deleted {part_id}", severity="information")
        else:
            self.notify("Part not found", severity="warning")

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
    actor_id: str = "",
    actor_role: str = "tech",
) -> RepairOrder | None:
    return WorkItemsForm(
        order, actor=actor, actor_id=actor_id, actor_role=actor_role
    ).run()
