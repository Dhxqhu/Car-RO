"""Advisor desk action trail — who handled pool work on an RO."""

from __future__ import annotations

from typing import Any

from carro.core.models import now_iso


def normalize_advisor_action(data: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    return {
        "at": str(data.get("at") or "").strip() or now_iso(),
        "action": str(data.get("action") or "").strip(),
        "advisor_id": str(data.get("advisor_id") or "").strip(),
        "advisor_name": str(data.get("advisor_name") or "").strip(),
        "ro_id": str(data.get("ro_id") or "").strip(),
        "work_item_id": str(data.get("work_item_id") or "").strip(),
        "found_issue_id": str(data.get("found_issue_id") or "").strip(),
        "note": str(data.get("note") or "").strip(),
        "detail": str(data.get("detail") or "").strip(),
    }


def normalize_advisor_actions(raw: list[Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not raw:
        return out
    for entry in raw:
        if isinstance(entry, dict) and (entry.get("action") or entry.get("advisor_id")):
            out.append(normalize_advisor_action(entry))
    return out


def append_advisor_action(
    order: Any,
    *,
    action: str,
    advisor_id: str,
    advisor_name: str,
    work_item_id: str = "",
    found_issue_id: str = "",
    note: str = "",
    detail: str = "",
) -> dict[str, Any]:
    """Append a trail entry onto order.advisor_actions (mutates order)."""
    entry = normalize_advisor_action(
        {
            "at": now_iso(),
            "action": action,
            "advisor_id": advisor_id,
            "advisor_name": advisor_name,
            "ro_id": getattr(order, "id", "") or "",
            "work_item_id": work_item_id,
            "found_issue_id": found_issue_id,
            "note": note,
            "detail": detail,
        }
    )
    actions = list(getattr(order, "advisor_actions", None) or [])
    if not isinstance(actions, list):
        actions = []
    actions.append(entry)
    order.advisor_actions = actions
    return entry
