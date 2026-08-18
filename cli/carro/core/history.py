"""Vehicle repair history: VIN-first, customer name fallback."""

from __future__ import annotations

import re
from dataclasses import dataclass

from carro.core.db import LocalStore
from carro.core.models import RepairOrder
from carro.storage.remote import RemoteClient

# Partial VIN only if at least this many chars (e.g. serial section)
MIN_PARTIAL_VIN = 8


def normalize_vin(vin: str) -> str:
    """Uppercase, strip spaces/dashes; keep alphanumerics."""
    raw = (vin or "").strip().upper()
    return re.sub(r"[^A-Z0-9]", "", raw)


@dataclass
class HistoryResult:
    orders: list[RepairOrder]
    matched_by: str  # "vin_exact" | "vin_partial" | "name" | ""
    vin_query: str = ""
    name_query: str = ""
    remote_ok: bool = True
    note: str = ""


def vehicle_history(
    store: LocalStore,
    *,
    vin: str = "",
    name: str = "",
    exclude_id: str | None = None,
    remote: bool | None = None,
    unique_cars: bool = False,
) -> HistoryResult:
    """
    Prior ROs for a vehicle (VIN) or, if none, by customer name/phone.
    Merges local + server when remote is enabled (default: when server_url set).
    If the shop server is unreachable, returns local-cache matches only (no error).
    Includes billed_out jobs — closing an RO does not remove it from history.
    """
    vin_n = normalize_vin(vin)
    name_q = (name or "").strip()
    want_remote = bool(RemoteClient().enabled) if remote is None else bool(remote)
    remote_ok = True
    note = ""

    def finish(
        orders: list[RepairOrder], matched_by: str, *, rem_ok: bool, rem_note: str
    ) -> HistoryResult:
        n = rem_note
        if want_remote and not rem_ok:
            if orders:
                n = (
                    rem_note
                    or "Shop server unreachable — showing jobs already on this bay."
                )
            else:
                n = (
                    "Shop server unreachable and no matching jobs on this bay. "
                    "Blank RO still works; sync when you're back online for full archive."
                )
        ranked = _sort(orders)
        if unique_cars:
            ranked = latest_orders_per_car(ranked)
        return HistoryResult(
            orders=ranked,
            matched_by=matched_by,
            vin_query=vin_n,
            name_query=name_q,
            remote_ok=rem_ok if want_remote else True,
            note=n,
        )

    if vin_n:
        exact, rem_ok, rem_note = _collect(
            store, vin=vin_n, vin_mode="exact", remote=want_remote
        )
        remote_ok = rem_ok
        note = rem_note
        exact = _exclude(exact, exclude_id)
        if exact:
            return finish(exact, "vin_exact", rem_ok=remote_ok, rem_note=note)
        if len(vin_n) >= MIN_PARTIAL_VIN:
            partial, rem_ok2, rem_note2 = _collect(
                store, vin=vin_n, vin_mode="partial", remote=want_remote
            )
            remote_ok = remote_ok and rem_ok2
            note = note or rem_note2
            partial = _exclude(partial, exclude_id)
            if partial:
                return finish(partial, "vin_partial", rem_ok=remote_ok, rem_note=note)

    if name_q:
        by_name, rem_ok, rem_note = _collect(
            store, name=name_q, remote=want_remote
        )
        # Keep VIN-era remote failure if name search skipped remote or also failed
        if want_remote and vin_n:
            remote_ok = remote_ok and rem_ok
            note = note or rem_note
        else:
            remote_ok = rem_ok if want_remote else True
            note = rem_note
        by_name = _exclude(by_name, exclude_id)
        return finish(
            by_name,
            "name" if by_name else "",
            rem_ok=remote_ok,
            rem_note=note,
        )

    return finish([], "", rem_ok=remote_ok, rem_note=note)


def _exclude(orders: list[RepairOrder], exclude_id: str | None) -> list[RepairOrder]:
    if not exclude_id:
        return orders
    return [o for o in orders if o.id != exclude_id]


def _sort(orders: list[RepairOrder]) -> list[RepairOrder]:
    return sorted(
        orders,
        key=lambda o: (o.updated or o.created or "", o.id),
        reverse=True,
    )


def _normalize_plate(plate: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (plate or "").strip().upper())


def car_identity_key(order: RepairOrder) -> str:
    """Stable key for one physical car. VIN first, then plate, then vehicle + customer."""
    vin = normalize_vin(getattr(order, "vin", "") or "")
    if vin:
        return f"vin:{vin}"
    plate = _normalize_plate(getattr(order, "plate", "") or "")
    if plate:
        return f"plate:{plate}"
    year = str(getattr(order, "year", "") or "").strip().lower()
    make = str(getattr(order, "make", "") or "").strip().lower()
    model = str(getattr(order, "model", "") or "").strip().lower()
    if year or make or model:
        last = str(getattr(order, "last_name", "") or "").strip().lower()
        first = str(getattr(order, "first_name", "") or "").strip().lower()
        return f"veh:{year}|{make}|{model}|{last}|{first}"
    return f"ro:{getattr(order, 'id', '')}"


def latest_orders_per_car(orders: list[RepairOrder]) -> list[RepairOrder]:
    """Keep the newest RO for each car so lookup lists stay readable."""
    seen: dict[str, RepairOrder] = {}
    out: list[RepairOrder] = []
    for order in _sort(orders):
        key = car_identity_key(order)
        if key in seen:
            continue
        seen[key] = order
        out.append(order)
    return out


# Short timeouts — bay laptops often hit Wi-Fi gaps on road tests
_HISTORY_REMOTE_TIMEOUT = 5.0


def _collect(
    store: LocalStore,
    *,
    vin: str = "",
    vin_mode: str = "exact",
    name: str = "",
    remote: bool = False,
) -> tuple[list[RepairOrder], bool, str]:
    """Return (orders, remote_ok, note). Always includes local hits first."""
    by_id: dict[str, RepairOrder] = {}

    if vin:
        for o in store.list_orders():
            if _vin_match(o.vin, vin, vin_mode):
                by_id[o.id] = o
    elif name:
        # Free-text matches name + phone (name= filter alone skips phone)
        for o in store.search(query=name):
            by_id[o.id] = o
        for o in store.search(name=name):
            by_id[o.id] = o

    remote_ok = True
    note = ""
    if remote:
        client = RemoteClient()
        if client.enabled:
            try:
                if vin:
                    raw = client.search_ros(vin=vin, timeout=_HISTORY_REMOTE_TIMEOUT)
                    for r in raw:
                        o = RepairOrder.from_dict(r)
                        if _vin_match(o.vin, vin, vin_mode):
                            if o.id not in by_id:
                                store.save(o, mark_pending_sync=False)
                            by_id[o.id] = store.get(o.id) or o
                elif name:
                    # Free-text `q` matches phone; `name=` is last/first name filters
                    raw = client.search_ros(
                        name, name=name, timeout=_HISTORY_REMOTE_TIMEOUT
                    )
                    for r in raw:
                        o = RepairOrder.from_dict(r)
                        if o.id not in by_id:
                            store.save(o, mark_pending_sync=False)
                        by_id[o.id] = store.get(o.id) or o
            except Exception:
                remote_ok = False
                note = "Shop server unreachable — showing jobs already on this bay."

    return list(by_id.values()), remote_ok, note


def _vin_match(order_vin: str, query: str, mode: str) -> bool:
    ov = normalize_vin(order_vin)
    if not ov or not query:
        return False
    if mode == "exact":
        return ov == query
    # partial: query contained in VIN (e.g. last 8)
    return query in ov


def vehicle_fields_from(order: RepairOrder) -> dict[str, str]:
    """Fields to copy into a new RO for the same car (no customer/notes)."""
    out = {}
    for key in ("year", "make", "model", "vin", "plate", "mileage"):
        val = (getattr(order, key, "") or "").strip()
        if val:
            out[key] = val
    # Prefer normalized VIN
    if out.get("vin"):
        out["vin"] = normalize_vin(out["vin"])
    return out


def customer_vehicle_fields_from(order: RepairOrder) -> dict[str, str]:
    """
    Prefill a new visit from a prior RO: customer + vehicle identity.
    Skips mileage, complaint, notes, and work items (fresh job).
    """
    out: dict[str, str] = {}
    for key in ("first_name", "last_name", "phone", "year", "make", "model", "vin", "plate"):
        val = (getattr(order, key, "") or "").strip()
        if val:
            out[key] = val
    if out.get("vin"):
        out["vin"] = normalize_vin(out["vin"])
    return out
