"""Advisor phone-book appointments (thin records until converted to an RO)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from carro.core.db import LocalStore
from carro.core.models import RepairOrder, now_iso
from carro.core.work_items import WORK_ITEM_TYPES, normalize_item_type

APPT_STATUSES = ("scheduled", "canceled", "no_show", "converted")
ARCHIVE_STATUSES = ("canceled", "no_show")
CONFIRM_STATUSES = ("", "confirmed", "canceled", "no_answer")


def new_appointment_id(existing: list[str], when: datetime | None = None) -> str:
    when = when or datetime.now()
    day = when.strftime("%Y%m%d")
    prefix = f"APPT-{day}-"
    seq = 1
    for eid in existing:
        if eid.startswith(prefix):
            try:
                seq = max(seq, int(eid.rsplit("-", 1)[-1]) + 1)
            except ValueError:
                pass
    return f"{prefix}{seq:03d}"


def normalize_appointment(data: dict[str, Any] | None) -> dict[str, Any]:
    raw = data if isinstance(data, dict) else {}
    status = str(raw.get("status") or "scheduled").strip().lower()
    if status not in APPT_STATUSES:
        status = "scheduled"
    tag = normalize_item_type(raw.get("tag"), default="other")
    scheduled = str(raw.get("scheduled_at") or "").strip()
    all_day = bool(raw.get("all_day"))
    if scheduled and "T" not in scheduled and len(scheduled) >= 10:
        all_day = True
        scheduled = scheduled[:10]
    out = {
        "id": str(raw.get("id") or "").strip(),
        "scheduled_at": scheduled,
        "all_day": all_day,
        "first_name": str(raw.get("first_name") or "").strip(),
        "last_name": str(raw.get("last_name") or "").strip(),
        "phone": str(raw.get("phone") or "").strip(),
        "year": str(raw.get("year") or "").strip(),
        "make": str(raw.get("make") or "").strip(),
        "model": str(raw.get("model") or "").strip(),
        "vin": str(raw.get("vin") or "").strip(),
        "notes": str(raw.get("notes") or "").strip(),
        "tag": tag,
        "requested_tech_id": str(raw.get("requested_tech_id") or "").strip(),
        "requested_tech_name": str(raw.get("requested_tech_name") or "").strip(),
        "status": status,
        "converted_ro_id": str(raw.get("converted_ro_id") or "").strip(),
        "prior_ro_id": str(raw.get("prior_ro_id") or "").strip(),
        "service_plan_id": str(raw.get("service_plan_id") or "").strip(),
        "service_plan_line_id": str(raw.get("service_plan_line_id") or "").strip(),
        "service_plan_enroll": str(raw.get("service_plan_enroll") or "").strip().lower(),
        "waiter": bool(raw.get("waiter")),
        "urgent": bool(raw.get("urgent")),
        "confirm_veto_until": str(raw.get("confirm_veto_until") or "").strip()[:10],
        "canceled_at": str(raw.get("canceled_at") or "").strip(),
        "no_show_at": str(raw.get("no_show_at") or "").strip(),
        "confirm_status": _normalize_confirm(raw.get("confirm_status")),
        "confirm_at": str(raw.get("confirm_at") or "").strip(),
        "confirm_by": str(raw.get("confirm_by") or "").strip(),
        "confirm_by_id": str(raw.get("confirm_by_id") or "").strip(),
        "confirm_attempts": _confirm_attempts(raw.get("confirm_attempts")),
        "created_by": str(raw.get("created_by") or "").strip(),
        "created_by_id": str(raw.get("created_by_id") or "").strip(),
        "created": str(raw.get("created") or "").strip(),
        "updated": str(raw.get("updated") or "").strip(),
    }
    return out


def _normalize_confirm(raw: object) -> str:
    st = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if st in ("didnt_answer", "did_not_answer", "noanswer", "no_answer"):
        return "no_answer"
    if st in ("cancelled", "canceled"):
        return "canceled"
    if st in ("confirmed", "confirm"):
        return "confirmed"
    if st in ("veto_next", "veto_tomorrow", "next_day"):
        return "veto_next"
    if st in ("veto", "veto_cycle", "veto_completely"):
        return "veto"
    return ""


def _confirm_attempts(raw: object) -> int:
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


def appointment_label(appt: dict[str, Any]) -> str:
    name = f"{appt.get('last_name') or ''}, {appt.get('first_name') or ''}".strip(", ").strip()
    vehicle = " ".join(
        str(x) for x in (appt.get("year"), appt.get("make"), appt.get("model")) if x
    ).strip()
    bits = [b for b in (name or "(no name)", vehicle) if b]
    return " · ".join(bits)


def upsert_appointment(
    store: LocalStore,
    data: dict[str, Any],
    *,
    actor: str = "",
    actor_id: str = "",
) -> dict[str, Any]:
    incoming = dict(data or {})
    appt_id = str(incoming.get("id") or "").strip()
    existing = store.get_appointment(appt_id) if appt_id else None
    if existing:
        merged = dict(existing)
        merged.update({k: v for k, v in incoming.items() if v is not None})
        merged["id"] = existing["id"]
        if not (merged.get("created_by") or "").strip():
            merged["created_by"] = actor
            merged["created_by_id"] = actor_id
    else:
        if not appt_id:
            appt_id = new_appointment_id(store.list_appointment_ids())
        incoming["id"] = appt_id
        incoming["created_by"] = incoming.get("created_by") or actor
        incoming["created_by_id"] = incoming.get("created_by_id") or actor_id
        incoming["created"] = incoming.get("created") or now_iso()
        merged = incoming
    if not str(merged.get("scheduled_at") or "").strip():
        raise ValueError("scheduled_at required")
    merged["updated"] = now_iso()
    saved = store.save_appointment(merged)
    tag = str(saved.get("tag") or "")
    enroll_raw = str(saved.get("service_plan_enroll") or "").strip().lower()
    if (
        enroll_raw in ("yes", "true", "1")
        and tag in ("si_im", "si_only")
        and not str(saved.get("service_plan_id") or "").strip()
    ):
        from carro.core.service_plans import enroll_inspection_plan

        enrolled = enroll_inspection_plan(
            store,
            saved,
            tag,
            enroll=True,
            actor=actor,
            actor_id=actor_id,
        )
        if enrolled:
            saved["service_plan_id"] = enrolled["plan"]["id"]
            saved["service_plan_line_id"] = enrolled["line"]["id"]
            saved = store.save_appointment(saved)
    plan_id = str(saved.get("service_plan_id") or "").strip()
    line_id = str(saved.get("service_plan_line_id") or "").strip()
    if plan_id and line_id and saved.get("status") == "scheduled":
        from carro.core.service_plans import mark_line_booked

        mark_line_booked(store, plan_id, line_id, saved["id"])
    return saved


def archive_appointment(
    store: LocalStore,
    appt_id: str,
    *,
    status: str,
) -> dict[str, Any]:
    st = (status or "").strip().lower()
    if st not in ARCHIVE_STATUSES:
        raise ValueError("status must be canceled or no_show")
    appt = store.get_appointment(appt_id)
    if not appt:
        raise ValueError(f"Appointment not found: {appt_id}")
    if appt.get("status") == "converted":
        raise ValueError("Converted appointments cannot be archived")
    appt["status"] = st
    ts = now_iso()
    if st == "canceled":
        appt["canceled_at"] = ts
        appt["no_show_at"] = ""
    else:
        appt["no_show_at"] = ts
        appt["canceled_at"] = ""
    appt["updated"] = ts
    return store.save_appointment(appt)


def restore_appointment(store: LocalStore, appt_id: str) -> dict[str, Any]:
    appt = store.get_appointment(appt_id)
    if not appt:
        raise ValueError(f"Appointment not found: {appt_id}")
    if appt.get("status") == "converted":
        raise ValueError("Converted appointments cannot be restored to the calendar")
    appt["status"] = "scheduled"
    appt["canceled_at"] = ""
    appt["no_show_at"] = ""
    appt["confirm_status"] = ""
    appt["confirm_at"] = ""
    appt["confirm_by"] = ""
    appt["confirm_by_id"] = ""
    appt["confirm_veto_until"] = ""
    appt["updated"] = now_iso()
    return store.save_appointment(appt)


def set_confirm_call(
    store: LocalStore,
    appt_id: str,
    outcome: str,
    *,
    actor: str = "",
    actor_id: str = "",
    today: str = "",
) -> dict[str, Any]:
    """Day-before call: confirmed, canceled, no_answer, or veto (didn't call)."""
    st = _normalize_confirm(outcome)
    if st not in ("confirmed", "canceled", "no_answer", "veto_next", "veto"):
        raise ValueError("outcome must be confirmed, canceled, no_answer, veto_next, or veto")
    appt = store.get_appointment(appt_id)
    if not appt:
        raise ValueError(f"Appointment not found: {appt_id}")
    if appt.get("status") == "converted":
        raise ValueError("Converted appointments cannot be confirmed")
    ts = now_iso()
    today_s = (today or "").strip()[:10] or _local_today()
    if st == "no_answer":
        appt["confirm_attempts"] = _confirm_attempts(appt.get("confirm_attempts")) + 1
        if appt.get("status") == "canceled":
            appt["status"] = "scheduled"
            appt["canceled_at"] = ""
    else:
        appt["confirm_attempts"] = _confirm_attempts(appt.get("confirm_attempts"))
    appt["confirm_status"] = st
    appt["confirm_at"] = ts
    appt["confirm_by"] = actor
    appt["confirm_by_id"] = actor_id
    if st == "veto_next":
        appt["confirm_veto_until"] = _next_day(today_s)
    else:
        appt["confirm_veto_until"] = ""
    appt["updated"] = ts
    store.save_appointment(appt)
    if st == "canceled":
        return archive_appointment(store, appt_id, status="canceled")
    if appt.get("status") != "scheduled":
        appt["status"] = "scheduled"
        appt["canceled_at"] = ""
        appt["no_show_at"] = ""
        store.save_appointment(appt)
    return store.get_appointment(appt_id) or appt


def convert_appointment_to_ro(
    store: LocalStore,
    appt_id: str,
    *,
    actor: str = "",
    actor_id: str = "",
) -> tuple[dict[str, Any], RepairOrder]:
    appt = store.get_appointment(appt_id)
    if not appt:
        raise ValueError(f"Appointment not found: {appt_id}")
    if appt.get("status") == "converted" and (appt.get("converted_ro_id") or "").strip():
        existing = store.get(str(appt["converted_ro_id"]))
        if existing:
            return appt, existing
    fields: dict[str, Any] = {}
    prior_id = str(appt.get("prior_ro_id") or "").strip()
    if prior_id:
        prior = store.get(prior_id)
        if prior:
            from carro.core.history import customer_vehicle_fields_from

            fields.update(customer_vehicle_fields_from(prior))
    for key in ("first_name", "last_name", "phone", "year", "make", "model", "vin"):
        val = str(appt.get(key) or "").strip()
        if val:
            fields[key] = val
    order = store.create(**fields)
    from carro.core.work_items import apply_rollups, ensure_work_items_on_order, upsert_work_item

    tag = normalize_item_type(appt.get("tag"), default="other")
    concern = str(appt.get("notes") or "").strip() or f"{tag} appointment"
    tech_id = str(appt.get("requested_tech_id") or "").strip()
    tech_name = str(appt.get("requested_tech_name") or "").strip()
    item = upsert_work_item(
        order,
        concern=concern,
        item_type=tag,
        actor=actor,
        actor_id=actor_id,
        actor_role="advisor",
        assign_to_id=tech_id or None,
        assign_to_name=tech_name or None,
        allow_manual_assign=True,
    )
    plan_id = str(appt.get("service_plan_id") or "").strip()
    line_id = str(appt.get("service_plan_line_id") or "").strip()
    enroll = str(appt.get("service_plan_enroll") or "").strip().lower()
    if plan_id or line_id or enroll:
        item.service_plan_id = plan_id
        item.service_plan_line_id = line_id
        item.service_plan_enroll = enroll
        for row in order.work_items or []:
            if isinstance(row, dict) and row.get("id") == item.id:
                row["service_plan_id"] = plan_id
                row["service_plan_line_id"] = line_id
                row["service_plan_enroll"] = enroll
    if tech_id or tech_name:
        from carro.core.assignment import assign_work_item

        items = ensure_work_items_on_order(order)
        target_id = item.id if item else (items[0].id if items else "")
        if target_id:
            assign_work_item(
                order,
                target_id,
                tech_id=tech_id,
                tech_name=tech_name,
                store=store,
            )
    apply_rollups(order)
    if bool(appt.get("waiter")) or bool(appt.get("urgent")):
        from carro.core.queue_lanes import set_ro_flags

        set_ro_flags(
            order,
            waiter=bool(appt.get("waiter")),
            urgent=bool(appt.get("urgent")),
        )
    store.save(order)
    appt["status"] = "converted"
    appt["converted_ro_id"] = order.id
    appt["updated"] = now_iso()
    store.save_appointment(appt)
    return appt, order


def _iso_day(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        if "T" in s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00") if s.endswith("Z") else s)
            return dt.date().isoformat()
    except ValueError:
        pass
    return s[:10]


def parts_events_in_range(
    store: LocalStore,
    start: str,
    end: str,
) -> list[dict[str, Any]]:
    start_s = (start or "").strip()[:10]
    end_s = (end or "").strip()[:10]
    events: list[dict[str, Any]] = []
    for order in store.list_orders():
        customer = order.customer_label()
        vehicle = order.vehicle_label()
        for it in order.work_items or []:
            if not isinstance(it, dict):
                continue
            item_id = str(it.get("id") or "")
            for part in it.get("parts") or []:
                if not isinstance(part, dict):
                    continue
                part_id = str(part.get("id") or "")
                desc = str(part.get("description") or part.get("part_number") or part_id)
                for kind, key in (("ordered", "ordered_at"), ("received", "received_at")):
                    at = str(part.get(key) or "").strip()
                    if not at:
                        continue
                    day = _iso_day(at)
                    if start_s and day < start_s:
                        continue
                    if end_s and day > end_s:
                        continue
                    events.append(
                        {
                            "kind": kind,
                            "at": at,
                            "day": day,
                            "ro_id": order.id,
                            "item_id": item_id,
                            "part_id": part_id,
                            "description": desc,
                            "customer": customer,
                            "vehicle": vehicle,
                        }
                    )
    events.sort(key=lambda e: (str(e.get("at") or ""), str(e.get("ro_id") or "")))
    return events


def _local_today() -> str:
    return datetime.now().date().isoformat()


def _next_day(day: str) -> str:
    d = datetime.strptime((day or "")[:10], "%Y-%m-%d").date()
    return (d + timedelta(days=1)).isoformat()


def confirm_call_list(store: LocalStore, *, today: str = "") -> dict[str, Any]:
    """Tomorrow's bookings (day-before calls) plus today's still-open calls."""
    today_s = (today or "").strip()[:10] or _local_today()
    tomorrow = _next_day(today_s)
    scheduled = store.list_appointments(statuses=["scheduled"])

    def _on_call_list(a: dict[str, Any]) -> bool:
        st = str(a.get("confirm_status") or "")
        if st in ("confirmed", "canceled", "veto"):
            return False
        until = str(a.get("confirm_veto_until") or "")[:10]
        if until and until > today_s:
            return False
        return True

    for_tomorrow = [
        a
        for a in scheduled
        if str(a.get("scheduled_at") or "")[:10] == tomorrow and _on_call_list(a)
    ]
    for_today = [
        a
        for a in scheduled
        if str(a.get("scheduled_at") or "")[:10] == today_s and _on_call_list(a)
    ]
    for_tomorrow.sort(key=lambda a: str(a.get("scheduled_at") or ""))
    for_today.sort(key=lambda a: str(a.get("scheduled_at") or ""))
    return {
        "today": today_s,
        "tomorrow": tomorrow,
        "tomorrow_calls": for_tomorrow,
        "today_open": for_today,
    }


def calendar_payload(
    store: LocalStore,
    *,
    start: str,
    end: str,
) -> dict[str, Any]:
    scheduled = store.list_appointments_in_range(
        start, end, statuses=["scheduled"]
    )
    archived = store.list_appointments(statuses=list(ARCHIVE_STATUSES))
    converted = store.list_appointments_in_range(
        start, end, statuses=["converted"]
    )
    calls = confirm_call_list(store)
    from carro.core.service_plans import due_call_list

    return {
        "start": (start or "")[:10],
        "end": (end or "")[:10],
        "appointments": scheduled,
        "converted": converted,
        "canceled": [a for a in archived if a.get("status") == "canceled"],
        "no_show": [a for a in archived if a.get("status") == "no_show"],
        "parts": parts_events_in_range(store, start, end),
        "tags": list(WORK_ITEM_TYPES),
        "due_calls": due_call_list(store),
        **calls,
    }
