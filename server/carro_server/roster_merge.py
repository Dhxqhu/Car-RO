"""Merge shop rosters so a leftover bay file cannot delete live people."""

from __future__ import annotations


def merge_person_rows(existing: list, incoming: list, *, replace: bool) -> list:
    """Upsert by id. Default merge keeps shop people a stale PUT omitted."""
    incoming_rows = [t for t in incoming if isinstance(t, dict)]
    if replace:
        return incoming_rows
    by_id: dict[str, dict] = {}
    order: list[str] = []
    for item in list(existing) + incoming_rows:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or "").strip()
        if not pid:
            continue
        if pid not in by_id:
            order.append(pid)
        by_id[pid] = item
    return [by_id[i] for i in order]
