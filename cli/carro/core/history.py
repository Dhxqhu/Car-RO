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


def vehicle_history(
    store: LocalStore,
    *,
    vin: str = "",
    name: str = "",
    exclude_id: str | None = None,
    remote: bool | None = None,
) -> HistoryResult:
    """
    Prior ROs for a vehicle (VIN) or, if none, by customer name.
    Merges local + server when remote is enabled (default: when server_url set).
    Includes billed_out jobs — closing an RO does not remove it from history.
    """
    vin_n = normalize_vin(vin)
    name_q = (name or "").strip()
    if remote is None:
        remote = bool(RemoteClient().enabled)

    if vin_n:
        exact = _collect(store, vin=vin_n, vin_mode="exact", remote=remote)
        exact = _exclude(exact, exclude_id)
        if exact:
            return HistoryResult(
                orders=_sort(exact),
                matched_by="vin_exact",
                vin_query=vin_n,
                name_query=name_q,
            )
        if len(vin_n) >= MIN_PARTIAL_VIN:
            partial = _collect(store, vin=vin_n, vin_mode="partial", remote=remote)
            partial = _exclude(partial, exclude_id)
            if partial:
                return HistoryResult(
                    orders=_sort(partial),
                    matched_by="vin_partial",
                    vin_query=vin_n,
                    name_query=name_q,
                )

    if name_q:
        by_name = _collect(store, name=name_q, remote=remote)
        by_name = _exclude(by_name, exclude_id)
        return HistoryResult(
            orders=_sort(by_name),
            matched_by="name" if by_name else "",
            vin_query=vin_n,
            name_query=name_q,
        )

    return HistoryResult(orders=[], matched_by="", vin_query=vin_n, name_query=name_q)


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


def _collect(
    store: LocalStore,
    *,
    vin: str = "",
    vin_mode: str = "exact",
    name: str = "",
    remote: bool = False,
) -> list[RepairOrder]:
    by_id: dict[str, RepairOrder] = {}

    if vin:
        for o in store.list_orders():
            if _vin_match(o.vin, vin, vin_mode):
                by_id[o.id] = o
    elif name:
        for o in store.search(name=name):
            by_id[o.id] = o

    if remote:
        client = RemoteClient()
        if client.enabled:
            try:
                if vin:
                    # Server search is substring; filter client-side for exact/partial rules
                    raw = client.search_ros(vin=vin)
                    for r in raw:
                        o = RepairOrder.from_dict(r)
                        if _vin_match(o.vin, vin, vin_mode):
                            if o.id not in by_id:
                                store.save(o)
                            by_id[o.id] = store.get(o.id) or o
                elif name:
                    raw = client.search_ros(name=name)
                    for r in raw:
                        o = RepairOrder.from_dict(r)
                        if o.id not in by_id:
                            store.save(o)
                        by_id[o.id] = store.get(o.id) or o
            except Exception:
                pass

    return list(by_id.values())


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
