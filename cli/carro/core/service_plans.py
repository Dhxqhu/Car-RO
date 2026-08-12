"""Per-vehicle service plans: yearly SI recall + custom interval lines."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any

from carro.core.db import LocalStore
from carro.core.history import normalize_vin
from carro.core.models import RepairOrder, now_iso
from carro.core.work_items import WORK_ITEM_TYPE_LABELS, normalize_item_type

INSPECTION_TAGS = ("si_im", "si_only")
CALL_OUTCOMES = ("confirmed", "no_answer", "skip", "veto_next", "veto")
DUE_HORIZON_DAYS = 30


def new_plan_id(existing: list[str], when: datetime | None = None) -> str:
    when = when or datetime.now()
    day = when.strftime("%Y%m%d")
    prefix = f"SP-{day}-"
    seq = 1
    for eid in existing:
        if eid.startswith(prefix):
            try:
                seq = max(seq, int(eid.rsplit("-", 1)[-1]) + 1)
            except ValueError:
                pass
    return f"{prefix}{seq:03d}"


def new_line_id(existing: list[dict[str, Any]]) -> str:
    n = 1
    for line in existing:
        lid = str(line.get("id") or "")
        if lid.upper().startswith("L-"):
            try:
                n = max(n, int(lid.split("-", 1)[1]) + 1)
            except ValueError:
                pass
    return f"L-{n:03d}"


def add_months(day: str, months: int) -> str:
    raw = (day or "").strip()[:10]
    if not raw or months == 0:
        return raw
    d = datetime.strptime(raw, "%Y-%m-%d").date()
    month_i = d.month - 1 + int(months)
    year = d.year + month_i // 12
    month = month_i % 12 + 1
    day_n = min(d.day, monthrange(year, month)[1])
    return date(year, month, day_n).isoformat()


def _today() -> str:
    return datetime.now().date().isoformat()


def _day(raw: object) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    return s[:10]


def _int_months(raw: object, default: int = 12) -> int:
    try:
        n = int(raw or 0)
    except (TypeError, ValueError):
        n = default
    return max(1, n)


def _call_attempts(raw: object) -> int:
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


def _normalize_call(raw: object) -> str:
    st = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if st in ("didnt_answer", "did_not_answer", "noanswer", "no_answer"):
        return "no_answer"
    if st in ("veto_next", "veto_tomorrow", "next_day", "veto_to_next_day"):
        return "veto_next"
    if st in ("veto", "veto_cycle", "veto_completely", "forget"):
        return "veto"
    if st in ("cancelled", "canceled", "skip", "snooze"):
        return "skip"
    if st in ("confirmed", "confirm"):
        return "confirmed"
    return ""


def vehicle_key(data: dict[str, Any] | RepairOrder) -> str:
    if isinstance(data, RepairOrder):
        vin = normalize_vin(data.vin or "")
        year = (data.year or "").strip().lower()
        make = (data.make or "").strip().lower()
        model = (data.model or "").strip().lower()
        phone = (data.phone or "").strip().lower()
        last = (data.last_name or "").strip().lower()
        first = (data.first_name or "").strip().lower()
    else:
        vin = normalize_vin(str(data.get("vin") or ""))
        year = str(data.get("year") or "").strip().lower()
        make = str(data.get("make") or "").strip().lower()
        model = str(data.get("model") or "").strip().lower()
        phone = str(data.get("phone") or "").strip().lower()
        last = str(data.get("last_name") or "").strip().lower()
        first = str(data.get("first_name") or "").strip().lower()
    if vin:
        return f"vin:{vin}"
    return f"veh:{year}|{make}|{model}|{phone}|{last}|{first}"


def normalize_line(data: dict[str, Any] | None, *, existing: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    raw = data if isinstance(data, dict) else {}
    lid = str(raw.get("id") or "").strip() or new_line_id(existing or [])
    tag = normalize_item_type(raw.get("tag"), default="service")
    label = str(raw.get("label") or "").strip() or WORK_ITEM_TYPE_LABELS.get(tag, tag)
    months = _int_months(raw.get("interval_months"), 12)
    last_done = _day(raw.get("last_done_at"))
    next_due = _day(raw.get("next_due"))
    if not next_due:
        anchor = last_done or _today()
        next_due = add_months(anchor, months) if last_done else add_months(_today(), months)
    return {
        "id": lid,
        "label": label,
        "interval_months": months,
        "tag": tag,
        "last_done_at": last_done,
        "next_due": next_due,
        "call_status": _normalize_call(raw.get("call_status")),
        "call_at": str(raw.get("call_at") or "").strip(),
        "call_by": str(raw.get("call_by") or "").strip(),
        "call_by_id": str(raw.get("call_by_id") or "").strip(),
        "call_attempts": _call_attempts(raw.get("call_attempts")),
        "veto_until": _day(raw.get("veto_until")),
        "last_appt_id": str(raw.get("last_appt_id") or "").strip(),
        "last_ro_id": str(raw.get("last_ro_id") or "").strip(),
        "notes": str(raw.get("notes") or "").strip(),
    }


def normalize_plan(data: dict[str, Any] | None) -> dict[str, Any]:
    raw = data if isinstance(data, dict) else {}
    lines_in = raw.get("lines") if isinstance(raw.get("lines"), list) else []
    lines: list[dict[str, Any]] = []
    for entry in lines_in:
        if isinstance(entry, dict):
            lines.append(normalize_line(entry, existing=lines))
    vin = normalize_vin(str(raw.get("vin") or ""))
    out = {
        "id": str(raw.get("id") or "").strip(),
        "first_name": str(raw.get("first_name") or "").strip(),
        "last_name": str(raw.get("last_name") or "").strip(),
        "phone": str(raw.get("phone") or "").strip(),
        "year": str(raw.get("year") or "").strip(),
        "make": str(raw.get("make") or "").strip(),
        "model": str(raw.get("model") or "").strip(),
        "vin": vin,
        "notes": str(raw.get("notes") or "").strip(),
        "enrolled": str(raw.get("enrolled") or "yes").strip().lower() != "no",
        "lines": lines,
        "match_key": "",
        "created_by": str(raw.get("created_by") or "").strip(),
        "created_by_id": str(raw.get("created_by_id") or "").strip(),
        "created": str(raw.get("created") or "").strip(),
        "updated": str(raw.get("updated") or "").strip(),
    }
    out["match_key"] = vehicle_key(out)
    return out


def upsert_plan(
    store: LocalStore,
    data: dict[str, Any],
    *,
    actor: str = "",
    actor_id: str = "",
) -> dict[str, Any]:
    incoming = dict(data or {})
    plan_id = str(incoming.get("id") or "").strip()
    existing = store.get_service_plan(plan_id) if plan_id else None
    if not existing:
        found = find_plan_for_vehicle(store, incoming)
        if found and not plan_id:
            existing = found
    if existing:
        merged = dict(existing)
        for key, val in incoming.items():
            if key == "lines" and val is not None:
                continue
            if val is not None and key != "id":
                merged[key] = val
        if incoming.get("lines") is not None:
            merged["lines"] = incoming["lines"]
        merged["id"] = existing["id"]
    else:
        if not plan_id:
            plan_id = new_plan_id(store.list_service_plan_ids())
        incoming["id"] = plan_id
        incoming["created_by"] = incoming.get("created_by") or actor
        incoming["created_by_id"] = incoming.get("created_by_id") or actor_id
        incoming["created"] = incoming.get("created") or now_iso()
        merged = incoming
    merged["updated"] = now_iso()
    return store.save_service_plan(merged)


def find_plan_for_vehicle(store: LocalStore, data: dict[str, Any] | RepairOrder) -> dict[str, Any] | None:
    key = vehicle_key(data)
    if not key or key in ("vin:", "veh:|||||"):
        return None
    for plan in store.list_service_plans():
        if str(plan.get("match_key") or "") == key:
            return plan
        if key.startswith("vin:"):
            if normalize_vin(str(plan.get("vin") or "")) == key[4:]:
                return plan
    return None


def get_or_create_plan_for_order(
    store: LocalStore,
    order: RepairOrder,
    *,
    actor: str = "",
    actor_id: str = "",
) -> dict[str, Any]:
    found = find_plan_for_vehicle(store, order)
    if found:
        changed = False
        for key in ("first_name", "last_name", "phone", "year", "make", "model", "vin"):
            val = str(getattr(order, key, "") or "").strip()
            if val and not str(found.get(key) or "").strip():
                found[key] = val
                changed = True
        if changed:
            found["updated"] = now_iso()
            return store.save_service_plan(found)
        return found
    return upsert_plan(
        store,
        {
            "first_name": order.first_name,
            "last_name": order.last_name,
            "phone": order.phone,
            "year": order.year,
            "make": order.make,
            "model": order.model,
            "vin": order.vin,
            "lines": [],
        },
        actor=actor,
        actor_id=actor_id,
    )


def upsert_line(
    store: LocalStore,
    plan_id: str,
    line: dict[str, Any],
    *,
    delete: bool = False,
) -> dict[str, Any]:
    plan = store.get_service_plan(plan_id)
    if not plan:
        raise ValueError(f"Service plan not found: {plan_id}")
    lines = list(plan.get("lines") or [])
    lid = str(line.get("id") or "").strip()
    if delete:
        if not lid:
            raise ValueError("line id required to delete")
        plan["lines"] = [ln for ln in lines if str(ln.get("id")) != lid]
        plan["updated"] = now_iso()
        return store.save_service_plan(plan)
    if lid:
        replaced = False
        out: list[dict[str, Any]] = []
        for ln in lines:
            if str(ln.get("id")) == lid:
                merged = dict(ln)
                merged.update({k: v for k, v in line.items() if v is not None})
                out.append(normalize_line(merged, existing=out))
                replaced = True
            else:
                out.append(ln)
        if not replaced:
            out.append(normalize_line(line, existing=out))
        plan["lines"] = out
    else:
        lines.append(normalize_line(line, existing=lines))
        plan["lines"] = lines
    plan["updated"] = now_iso()
    return store.save_service_plan(plan)


def set_line_call(
    store: LocalStore,
    plan_id: str,
    line_id: str,
    outcome: str,
    *,
    actor: str = "",
    actor_id: str = "",
    today: str = "",
) -> dict[str, Any]:
    st = _normalize_call(outcome)
    if st not in CALL_OUTCOMES:
        raise ValueError("outcome must be confirmed, no_answer, skip, veto_next, or veto")
    plan = store.get_service_plan(plan_id)
    if not plan:
        raise ValueError(f"Service plan not found: {plan_id}")
    ts = now_iso()
    today_s = (today or "").strip()[:10] or _today()
    found = False
    lines: list[dict[str, Any]] = []
    for ln in plan.get("lines") or []:
        if str(ln.get("id")) != line_id:
            lines.append(ln)
            continue
        found = True
        ln = dict(ln)
        if st == "no_answer":
            try:
                ln["call_attempts"] = int(ln.get("call_attempts") or 0) + 1
            except (TypeError, ValueError):
                ln["call_attempts"] = 1
        ln["call_status"] = st
        ln["call_at"] = ts
        ln["call_by"] = actor
        ln["call_by_id"] = actor_id
        if st == "veto_next":
            ln["veto_until"] = (datetime.strptime(today_s, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
        else:
            ln["veto_until"] = ""
        if st in ("skip", "veto"):
            due = _day(ln.get("next_due")) or today_s
            months = _int_months(ln.get("interval_months"), 12)
            ln["next_due"] = add_months(due, months)
            if st == "skip":
                ln["call_status"] = ""
        lines.append(normalize_line(ln, existing=lines))
    if not found:
        raise ValueError(f"Plan line not found: {line_id}")
    plan["lines"] = lines
    plan["updated"] = ts
    return store.save_service_plan(plan)


def mark_line_booked(
    store: LocalStore,
    plan_id: str,
    line_id: str,
    appt_id: str,
) -> dict[str, Any] | None:
    plan = store.get_service_plan(plan_id)
    if not plan:
        return None
    lines = []
    hit = False
    for ln in plan.get("lines") or []:
        if str(ln.get("id")) == line_id:
            ln = dict(ln)
            ln["last_appt_id"] = appt_id
            hit = True
        lines.append(ln)
    if not hit:
        return plan
    plan["lines"] = lines
    plan["updated"] = now_iso()
    return store.save_service_plan(plan)


def _line_has_open_booking(store: LocalStore, line: dict[str, Any]) -> bool:
    appt_id = str(line.get("last_appt_id") or "").strip()
    if not appt_id:
        return False
    appt = store.get_appointment(appt_id)
    if not appt:
        return False
    return str(appt.get("status") or "") == "scheduled"


def due_call_list(
    store: LocalStore,
    *,
    today: str = "",
    horizon_days: int = DUE_HORIZON_DAYS,
) -> list[dict[str, Any]]:
    today_s = (today or "").strip()[:10] or _today()
    horizon = (datetime.strptime(today_s, "%Y-%m-%d").date() + timedelta(days=int(horizon_days))).isoformat()
    out: list[dict[str, Any]] = []
    for plan in store.list_service_plans():
        for ln in plan.get("lines") or []:
            due = _day(ln.get("next_due"))
            if not due or due > horizon:
                continue
            if _line_has_open_booking(store, ln):
                continue
            veto_until = _day(ln.get("veto_until"))
            if veto_until and veto_until > today_s:
                continue
            if str(ln.get("call_status") or "") == "veto" and due > today_s:
                continue
            name = f"{plan.get('last_name') or ''}, {plan.get('first_name') or ''}".strip(", ").strip()
            vehicle = " ".join(
                str(x) for x in (plan.get("year"), plan.get("make"), plan.get("model")) if x
            ).strip()
            out.append(
                {
                    "plan_id": plan.get("id"),
                    "line_id": ln.get("id"),
                    "label": ln.get("label") or "",
                    "tag": ln.get("tag") or "service",
                    "interval_months": ln.get("interval_months") or 12,
                    "next_due": due,
                    "last_done_at": ln.get("last_done_at") or "",
                    "overdue": due < today_s,
                    "call_status": ln.get("call_status") or "",
                    "call_attempts": ln.get("call_attempts") or 0,
                    "veto_until": ln.get("veto_until") or "",
                    "called": str(ln.get("call_status") or "") in ("confirmed", "no_answer", "skip"),
                    "phone": plan.get("phone") or "",
                    "first_name": plan.get("first_name") or "",
                    "last_name": plan.get("last_name") or "",
                    "year": plan.get("year") or "",
                    "make": plan.get("make") or "",
                    "model": plan.get("model") or "",
                    "vin": plan.get("vin") or "",
                    "customer": name or "(no name)",
                    "vehicle": vehicle,
                    "notes": ln.get("notes") or "",
                }
            )
    out.sort(key=lambda r: (str(r.get("next_due") or ""), str(r.get("customer") or "")))
    return out


def _roll_line(line: dict[str, Any], *, done_on: str, ro_id: str) -> dict[str, Any]:
    ln = dict(line)
    if str(ln.get("last_ro_id") or "") == ro_id:
        return ln
    day = _day(done_on) or _today()
    months = _int_months(ln.get("interval_months"), 12)
    ln["last_done_at"] = day
    ln["next_due"] = add_months(day, months)
    ln["last_ro_id"] = ro_id
    ln["call_status"] = ""
    ln["call_at"] = ""
    ln["call_attempts"] = 0
    ln["veto_until"] = ""
    ln["last_appt_id"] = ""
    return ln


def apply_service_plan_progress(store: LocalStore, order: RepairOrder) -> None:
    """Roll due dates when SI/plan-linked work is done or the RO is billed."""
    from carro.core.work_items import ensure_work_items_on_order

    ro_billed = (order.status or "").strip().lower() == "billed_out"
    done_at = (order.billed_out_at or order.done_at or now_iso()).strip()
    items = ensure_work_items_on_order(order)
    touched = False
    for item in items:
        status = (item.status or "").strip().lower()
        if status != "done" and not ro_billed:
            continue
        tag = normalize_item_type(item.item_type, default="")
        plan_id = str(getattr(item, "service_plan_id", "") or "").strip()
        line_id = str(getattr(item, "service_plan_line_id", "") or "").strip()
        if plan_id and line_id:
            plan = store.get_service_plan(plan_id)
            if not plan:
                continue
            lines = []
            hit = False
            for ln in plan.get("lines") or []:
                if str(ln.get("id")) == line_id:
                    lines.append(_roll_line(ln, done_on=done_at, ro_id=order.id))
                    hit = True
                else:
                    lines.append(ln)
            if hit:
                plan["lines"] = lines
                plan["updated"] = now_iso()
                store.save_service_plan(plan)
                touched = True
            continue
        if tag not in INSPECTION_TAGS:
            continue
        enroll = str(getattr(item, "service_plan_enroll", "") or "").strip().lower()
        if enroll in ("no", "false", "0"):
            continue
        plan = get_or_create_plan_for_order(store, order)
        lines = list(plan.get("lines") or [])
        target = next((ln for ln in lines if str(ln.get("tag")) == tag), None)
        if target is None:
            target = normalize_line(
                {
                    "label": WORK_ITEM_TYPE_LABELS.get(tag, tag),
                    "tag": tag,
                    "interval_months": 12,
                },
                existing=lines,
            )
            lines.append(target)
        rolled = _roll_line(target, done_on=done_at, ro_id=order.id)
        plan["lines"] = [
            rolled if str(ln.get("id")) == str(rolled.get("id")) else ln for ln in lines
        ]
        plan["updated"] = now_iso()
        store.save_service_plan(plan)
        touched = True
    _ = touched


def stamp_appointment_from_due(due: dict[str, Any], *, scheduled_at: str) -> dict[str, Any]:
    tag = normalize_item_type(due.get("tag"), default="service")
    label = str(due.get("label") or WORK_ITEM_TYPE_LABELS.get(tag, tag))
    return {
        "scheduled_at": scheduled_at,
        "all_day": "T" not in scheduled_at,
        "first_name": due.get("first_name") or "",
        "last_name": due.get("last_name") or "",
        "phone": due.get("phone") or "",
        "year": due.get("year") or "",
        "make": due.get("make") or "",
        "model": due.get("model") or "",
        "vin": due.get("vin") or "",
        "tag": tag,
        "notes": due.get("notes") or label,
        "service_plan_id": due.get("plan_id") or "",
        "service_plan_line_id": due.get("line_id") or "",
    }


def enroll_inspection_plan(
    store: LocalStore,
    vehicle: dict[str, Any] | RepairOrder,
    tag: str,
    *,
    enroll: bool,
    actor: str = "",
    actor_id: str = "",
) -> dict[str, Any] | None:
    """Yearly SI/IM line when the writer enrolls the customer. None if they decline."""
    if not enroll:
        return None
    tag_n = normalize_item_type(tag, default="si_im")
    if tag_n not in INSPECTION_TAGS:
        tag_n = "si_im"
    if isinstance(vehicle, RepairOrder):
        plan = get_or_create_plan_for_order(store, vehicle, actor=actor, actor_id=actor_id)
    else:
        found = find_plan_for_vehicle(store, vehicle)
        if found:
            plan = found
        else:
            plan = upsert_plan(
                store,
                {
                    "first_name": vehicle.get("first_name") or "",
                    "last_name": vehicle.get("last_name") or "",
                    "phone": vehicle.get("phone") or "",
                    "year": vehicle.get("year") or "",
                    "make": vehicle.get("make") or "",
                    "model": vehicle.get("model") or "",
                    "vin": vehicle.get("vin") or "",
                    "lines": [],
                },
                actor=actor,
                actor_id=actor_id,
            )
    lines = list(plan.get("lines") or [])
    target = next((ln for ln in lines if str(ln.get("tag")) == tag_n), None)
    if target is None:
        target = normalize_line(
            {
                "label": WORK_ITEM_TYPE_LABELS.get(tag_n, tag_n),
                "tag": tag_n,
                "interval_months": 12,
            },
            existing=lines,
        )
        lines.append(target)
        plan["lines"] = lines
        plan["updated"] = now_iso()
        plan = store.save_service_plan(plan)
        target = next(ln for ln in plan["lines"] if str(ln.get("tag")) == tag_n)
    return {"plan": plan, "line": target}
