"""Who should get a phone push for a shop event."""

from __future__ import annotations

from typing import Any, Iterable

# Same personal set as the tech desk bell.
TECH_PUSH_TYPES = frozenset(
    {
        "item_assigned",
        "ro_assigned",
        "item_due_eod",
        "item_wait_cleared",
        "item_ready_for_work",
        "next_day_approved",
        "next_day_declined",
        "shop_message",
    }
)

# Advisors get high-signal desk pings, not every status tick.
ADVISOR_PUSH_TYPES = frozenset(
    {
        "shop_message",
        "found_issue_created",
        "ro_approval_requested",
        "next_day_requested",
        "ro_ready_to_bill",
        "item_assigned",
        "ro_assigned",
        "item_due_eod",
    }
)

EVENT_LABELS = {
    "item_assigned": "Assigned to you",
    "ro_assigned": "RO assigned",
    "item_due_eod": "Needs done by end of day",
    "item_wait_cleared": "Ready for work",
    "item_ready_for_work": "Ready for work",
    "next_day_approved": "Next-day approved",
    "next_day_declined": "Next-day declined",
    "next_day_requested": "Next-day requested",
    "shop_message": "Shop message",
    "found_issue_created": "Found issue reported",
    "ro_approval_requested": "Customer approval requested",
    "ro_ready_to_bill": "Ready to bill",
}


def event_label(event_type: str) -> str:
    return EVENT_LABELS.get(event_type) or event_type.replace("_", " ").title()


def roster_people(technicians: dict, advisors: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for t in technicians.get("technicians") or []:
        if not isinstance(t, dict):
            continue
        pid = str(t.get("id") or "").strip()
        if not pid:
            continue
        rows.append(
            {
                "id": pid,
                "name": str(t.get("name") or pid).strip(),
                "role": "technician",
            }
        )
    for a in advisors.get("advisors") or []:
        if not isinstance(a, dict):
            continue
        pid = str(a.get("id") or "").strip()
        if not pid:
            continue
        rows.append(
            {
                "id": pid,
                "name": str(a.get("name") or pid).strip(),
                "role": "advisor",
            }
        )
    return rows


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _ids_matching_assignee(payload: dict, summary: str, people: Iterable[dict[str, str]]) -> set[str]:
    want_id = _norm(
        payload.get("assigned_to_id")
        or payload.get("assignee_id")
        or payload.get("to_id")
        or payload.get("requested_by_id")
        or payload.get("by_id")
    )
    want_name = _norm(payload.get("assigned_to_name") or payload.get("to_name"))
    summary_n = _norm(summary)
    found: set[str] = set()
    for p in people:
        pid = str(p.get("id") or "")
        name = str(p.get("name") or "")
        if want_id and _norm(pid) == want_id:
            found.add(pid)
            continue
        if want_name and _norm(name) == want_name:
            found.add(pid)
            continue
        if summary_n and _norm(name) and (
            summary_n == _norm(name)
            or f"· {_norm(name)} ·" in summary_n
            or summary_n.startswith(f"{_norm(name)} ·")
        ):
            found.add(pid)
    return found


def recipients_for_event(
    ev: dict[str, Any],
    *,
    actor_id: str = "",
    actor_name: str = "",
    people: list[dict[str, str]],
) -> list[str]:
    """Person ids who should get a phone push for this event (never the actor)."""
    etype = str(ev.get("type") or "")
    payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
    actor_id_n = _norm(actor_id or payload.get("actor_id") or payload.get("from_id"))
    actor_name_n = _norm(actor_name or ev.get("actor"))
    out: set[str] = set()

    def skip_self(pid: str, name: str) -> bool:
        if actor_id_n and _norm(pid) == actor_id_n:
            return True
        if actor_name_n and _norm(name) == actor_name_n:
            return True
        return False

    if etype == "shop_message":
        to_id = str(payload.get("to_id") or "").strip()
        if to_id and _norm(to_id) != actor_id_n:
            out.add(to_id)
        return sorted(out)

    if etype in TECH_PUSH_TYPES:
        out |= _ids_matching_assignee(payload, str(ev.get("summary") or ""), people)

    if etype in ADVISOR_PUSH_TYPES:
        for p in people:
            if p.get("role") == "advisor" and not skip_self(p["id"], p["name"]):
                out.add(p["id"])

    cleaned: set[str] = set()
    by_id = {p["id"]: p for p in people}
    for pid in out:
        person = by_id.get(pid)
        if person and skip_self(pid, person["name"]):
            continue
        if actor_id_n and _norm(pid) == actor_id_n:
            continue
        cleaned.add(pid)
    return sorted(cleaned)


def push_url(ev: dict[str, Any]) -> str:
    if str(ev.get("type") or "") == "shop_message":
        return "/messages"
    ro_id = str(ev.get("ro_id") or "").strip()
    if ro_id and ro_id not in ("_message", "_shift"):
        return f"/ro/{ro_id}"
    return "/"


def push_body(ev: dict[str, Any]) -> str:
    bits = [str(ev.get("ro_id") or "").strip(), str(ev.get("summary") or "").strip()]
    text = " · ".join(b for b in bits if b and b not in ("_message", "_shift"))
    text = text.replace("\n", " ").strip()
    if len(text) > 80:
        text = text[:79] + "…"
    return text or event_label(str(ev.get("type") or ""))
