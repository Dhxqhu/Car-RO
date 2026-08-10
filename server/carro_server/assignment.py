"""Assigned Work board helpers (dict-only; no cli carro dependency)."""

from __future__ import annotations

from typing import Any


def _tech_key(tech_id: str, tech_name: str) -> str:
    tid = (tech_id or "").strip().lower()
    if tid:
        return f"id:{tid}"
    name = (tech_name or "").strip().lower()
    if name:
        return f"name:{name}"
    return ""


def _matches_tech(tech_id: str, tech_name: str, *, me_id: str, me_name: str) -> bool:
    mid = (me_id or "").strip().lower()
    mname = (me_name or "").strip().lower()
    tid = (tech_id or "").strip().lower()
    tname = (tech_name or "").strip().lower()
    if mid and tid and mid == tid:
        return True
    if mname and tname and mname == tname:
        return True
    return False


def _summarize(d: dict[str, Any]) -> dict[str, Any]:
    items = [it for it in (d.get("work_items") or []) if isinstance(it, dict)]
    return {
        "id": d.get("id") or "",
        "customer": f"{d.get('last_name') or ''}, {d.get('first_name') or ''}".strip(", ").strip()
        or "(no customer)",
        "vehicle": " ".join(
            str(x) for x in (d.get("year"), d.get("make"), d.get("model")) if x
        ).strip()
        or "(no vehicle)",
        "vin": d.get("vin") or "",
        "status": d.get("status") or "open",
        "assigned_to_id": d.get("assigned_to_id") or "",
        "assigned_to_name": d.get("assigned_to_name") or "",
        "assigned_at": d.get("assigned_at") or "",
        "current_tech_id": d.get("current_tech_id") or "",
        "current_tech_name": d.get("current_tech_name") or "",
        "current_since": d.get("current_since") or "",
        "updated": d.get("updated") or d.get("created") or "",
        "work_items": [
            {
                "id": it.get("id") or "",
                "concern": str(it.get("concern") or "")[:120],
                "status": it.get("status") or "open",
                "assigned_to_id": it.get("assigned_to_id") or it.get("notes_by_id") or "",
                "assigned_to_name": it.get("assigned_to_name")
                or it.get("notes_by")
                or "",
                "created_by": it.get("created_by") or "",
                "created_by_role": it.get("created_by_role") or "",
                "notes_by": it.get("notes_by") or "",
            }
            for it in items
        ],
    }


def build_assigned_board(
    orders: list[dict[str, Any]],
    *,
    tech_id: str = "",
    tech_name: str = "",
) -> dict[str, Any]:
    mine: list[dict[str, Any]] = []
    by_tech: dict[str, dict[str, Any]] = {}
    unassigned: list[dict[str, Any]] = []
    now_working: list[dict[str, Any]] = []
    my_current: dict[str, Any] | None = None

    for d in orders:
        if not isinstance(d, dict):
            continue
        summary = _summarize(d)
        ro_aid = str(d.get("assigned_to_id") or "")
        ro_aname = str(d.get("assigned_to_name") or "")
        cur_id = str(d.get("current_tech_id") or "")
        cur_name = str(d.get("current_tech_name") or "")
        item_assignees: list[tuple[str, str]] = []
        for it in d.get("work_items") or []:
            if not isinstance(it, dict):
                continue
            iid = str(it.get("assigned_to_id") or it.get("notes_by_id") or "")
            iname = str(it.get("assigned_to_name") or it.get("notes_by") or "")
            if iid or iname:
                item_assignees.append((iid, iname))

        involves_me = (
            _matches_tech(ro_aid, ro_aname, me_id=tech_id, me_name=tech_name)
            or _matches_tech(cur_id, cur_name, me_id=tech_id, me_name=tech_name)
            or any(
                _matches_tech(iid, iname, me_id=tech_id, me_name=tech_name)
                for iid, iname in item_assignees
            )
        )
        if involves_me:
            mine.append(summary)

        if cur_id or cur_name:
            entry = {
                "tech_id": cur_id,
                "tech_name": cur_name,
                "since": summary.get("current_since") or "",
                "order": summary,
                "is_me": _matches_tech(cur_id, cur_name, me_id=tech_id, me_name=tech_name),
            }
            now_working.append(entry)
            if entry["is_me"]:
                my_current = summary

        tech_slots: list[tuple[str, str, str]] = []
        if ro_aid or ro_aname:
            tech_slots.append((_tech_key(ro_aid, ro_aname), ro_aid, ro_aname))
        for iid, iname in item_assignees:
            tech_slots.append((_tech_key(iid, iname), iid, iname))
        if cur_id or cur_name:
            tech_slots.append((_tech_key(cur_id, cur_name), cur_id, cur_name))

        seen_keys: set[str] = set()
        any_assignee = False
        for key, tid, tname in tech_slots:
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            any_assignee = True
            if _matches_tech(tid, tname, me_id=tech_id, me_name=tech_name):
                continue
            bucket = by_tech.setdefault(
                key,
                {
                    "id": tid,
                    "name": tname or tid or "Unknown",
                    "orders": [],
                    "current": None,
                },
            )
            if not any(o.get("id") == summary["id"] for o in bucket["orders"]):
                bucket["orders"].append(summary)
            if _matches_tech(cur_id, cur_name, me_id=tid, me_name=tname):
                bucket["current"] = summary

        if not any_assignee and str(d.get("status") or "") not in ("done",):
            unassigned.append(summary)

    by_tech_list = sorted(by_tech.values(), key=lambda b: (b.get("name") or "").lower())
    mine.sort(key=lambda o: o.get("updated") or "", reverse=True)
    unassigned.sort(key=lambda o: o.get("updated") or "", reverse=True)
    now_working.sort(key=lambda e: (e.get("tech_name") or "").lower())
    for b in by_tech_list:
        b["orders"].sort(key=lambda o: o.get("updated") or "", reverse=True)

    return {
        "mine": mine,
        "by_tech": by_tech_list,
        "unassigned": unassigned,
        "now_working": now_working,
        "my_current": my_current,
        "tech_id": tech_id,
        "tech_name": tech_name,
    }
