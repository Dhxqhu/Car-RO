"""Build Sun–Sat weekly tech reports from RO time_logs + presence shifts."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from carro.core.models import RepairOrder, now_iso
from carro.core.work_items import _elapsed_minutes, ensure_work_items_on_order


def sunday_on_or_before(d: date | None = None) -> date:
    d = d or date.today()
    return d - timedelta(days=(d.weekday() + 1) % 7)


def week_end_saturday(week_start: date) -> date:
    return week_start + timedelta(days=6)


def parse_week_start(raw: str | None) -> date:
    s = (raw or "").strip()
    if s:
        d = date.fromisoformat(s)
        return sunday_on_or_before(d)
    return sunday_on_or_before(date.today())


def _local_date_from_iso(raw: str) -> date | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.date()
    except ValueError:
        if len(s) >= 10:
            try:
                return date.fromisoformat(s[:10])
            except ValueError:
                return None
        return None


def _sun_index(d: date) -> int:
    return (d.weekday() + 1) % 7


def _empty_days() -> dict[str, dict[str, int]]:
    return {str(i): {"job_minutes": 0, "presence_minutes": 0} for i in range(7)}


def build_weekly_tech_report(
    orders: list[RepairOrder | dict[str, Any]],
    shifts: list[dict[str, Any]] | None = None,
    *,
    week_start: str | date | None = None,
    include_live: bool = True,
) -> dict[str, Any]:
    if isinstance(week_start, date):
        start = sunday_on_or_before(week_start)
    else:
        start = parse_week_start(str(week_start) if week_start else None)
    end = week_end_saturday(start)
    start_s = start.isoformat()
    end_s = end.isoformat()

    techs: dict[str, dict[str, Any]] = {}

    def bucket(tech_id: str, tech_name: str) -> dict[str, Any]:
        tid = (tech_id or "").strip()
        tname = (tech_name or "").strip() or tid or "Unknown"
        key = tid or tname.lower()
        b = techs.setdefault(
            key,
            {
                "tech_id": tid,
                "tech_name": tname,
                "job_minutes": 0,
                "presence_minutes": 0,
                "days": _empty_days(),
                "jobs": {},
            },
        )
        if tname and (not b.get("tech_name") or b["tech_name"] == b.get("tech_id")):
            b["tech_name"] = tname
        return b

    for order in orders:
        if isinstance(order, RepairOrder):
            d = order.to_dict()
            items = ensure_work_items_on_order(order)
            item_dicts = [w.to_dict() for w in items]
        else:
            d = dict(order)
            item_dicts = [it for it in (d.get("work_items") or []) if isinstance(it, dict)]
        customer = (
            f"{d.get('last_name') or ''}, {d.get('first_name') or ''}".strip(", ").strip()
            or "(no customer)"
        )
        vehicle = " ".join(
            str(x) for x in (d.get("year"), d.get("make"), d.get("model")) if x
        ).strip() or "(no vehicle)"
        ro_id = str(d.get("id") or "")

        for it in item_dicts:
            wid = str(it.get("id") or "")
            concern = str(it.get("concern") or "")[:120]
            for entry in it.get("time_log") or []:
                if not isinstance(entry, dict):
                    continue
                try:
                    mins = max(0, int(entry.get("minutes") or 0))
                except (TypeError, ValueError):
                    mins = 0
                if mins <= 0:
                    continue
                if str(it.get("completed_with_id") or "").strip():
                    continue
                day = _local_date_from_iso(str(entry.get("at") or ""))
                if day is None or day < start or day > end:
                    continue
                tid = str(entry.get("tech_id") or "").strip()
                tname = str(entry.get("tech_name") or "").strip() or tid or "Unknown"
                b = bucket(tid, tname)
                idx = str(_sun_index(day))
                b["days"][idx]["job_minutes"] += mins
                b["job_minutes"] += mins
                covers = [
                    str(x).strip()
                    for x in (entry.get("covers_item_ids") or it.get("covers_item_ids") or [])
                    if str(x).strip()
                ]
                jk = f"{ro_id}:{wid}"
                if covers:
                    jk = f"{ro_id}:{wid}+" + "+".join(covers)
                extra = ""
                if covers:
                    extra = " + " + ", ".join(covers)
                job = b["jobs"].setdefault(
                    jk,
                    {
                        "ro_id": ro_id,
                        "item_id": wid,
                        "concern": (concern + extra)[:160],
                        "minutes": 0,
                        "vehicle": vehicle,
                        "customer": customer,
                        "grouped_item_ids": [wid, *covers],
                    },
                )
                job["minutes"] += mins

            if include_live and (it.get("timer_started_at") or "").strip():
                live = _elapsed_minutes(str(it.get("timer_started_at") or ""))
                if live > 0 and start <= date.today() <= end:
                    tid = str(it.get("timer_tech_id") or "").strip()
                    tname = (
                        str(it.get("timer_tech_name") or "").strip() or tid or "Unknown"
                    )
                    b = bucket(tid, tname)
                    idx = str(_sun_index(date.today()))
                    b["days"][idx]["job_minutes"] += live
                    b["job_minutes"] += live
                    jk = f"{ro_id}:{wid}"
                    job = b["jobs"].setdefault(
                        jk,
                        {
                            "ro_id": ro_id,
                            "item_id": wid,
                            "concern": concern,
                            "minutes": 0,
                            "vehicle": vehicle,
                            "customer": customer,
                        },
                    )
                    job["minutes"] += live

    for sh in shifts or []:
        tid = str(sh.get("tech_id") or "").strip()
        if not tid:
            continue
        tname = str(sh.get("tech_name") or "").strip() or tid
        started = _local_date_from_iso(str(sh.get("started_at") or ""))
        day_s = str(sh.get("day") or "").strip()
        try:
            day_d = date.fromisoformat(day_s) if day_s else started
        except ValueError:
            day_d = started
        if day_d is None or day_d < start or day_d > end:
            continue
        st = str(sh.get("started_at") or "")
        en = str(sh.get("ended_at") or "") or ""
        try:
            if st.endswith("Z"):
                st = st[:-1] + "+00:00"
            t0 = datetime.fromisoformat(st).timestamp()
            if en:
                if en.endswith("Z"):
                    en = en[:-1] + "+00:00"
                t1 = datetime.fromisoformat(en).timestamp()
            else:
                t1 = datetime.now(tz=timezone.utc).timestamp()
            mins = max(0, int((t1 - t0) / 60))
        except ValueError:
            mins = 0
        if mins <= 0:
            continue
        b = bucket(tid, tname)
        idx = str(_sun_index(day_d))
        b["days"][idx]["presence_minutes"] += mins
        b["presence_minutes"] += mins

    tech_list: list[dict[str, Any]] = []
    for b in techs.values():
        jobs = sorted(
            list(b["jobs"].values()),
            key=lambda j: -int(j.get("minutes") or 0),
        )
        tech_list.append(
            {
                "tech_id": b["tech_id"],
                "tech_name": b["tech_name"],
                "job_minutes": int(b["job_minutes"]),
                "presence_minutes": int(b["presence_minutes"]),
                "days": b["days"],
                "jobs": jobs,
            }
        )
    tech_list.sort(
        key=lambda t: (
            -int(t.get("job_minutes") or 0),
            -int(t.get("presence_minutes") or 0),
            str(t.get("tech_name") or "").lower(),
        )
    )

    return {
        "week_start": start_s,
        "week_end": end_s,
        "generated_at": now_iso(),
        "techs": tech_list,
        "shop_job_minutes": sum(int(t.get("job_minutes") or 0) for t in tech_list),
        "shop_presence_minutes": sum(
            int(t.get("presence_minutes") or 0) for t in tech_list
        ),
    }


# --- Efficiency (40h baseline, worked vs clocked, utilized vs downtime) ---

BASELINE_DAY_MINUTES = 8 * 60
BASELINE_WEEK_MINUTES = 5 * BASELINE_DAY_MINUTES  # Mon–Fri normal week
WEEKDAY_SUN_INDEXES = {1, 2, 3, 4, 5}  # Mon..Fri in Sun=0 indexing

DOWNTIME_REASON_LABELS = {
    "waiting_parts": "Waiting parts",
    "wrong_parts": "Wrong parts",
    "waiting_customer": "Waiting customer",
    "between_sessions": "Between jobs",
    "found_issue_compose": "Found-issue compose",
    "other": "Other",
    "unaccounted": "Unaccounted",
}


def _parse_dt(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def _clip_segment_minutes(
    started_at: str,
    ended_at: str,
    *,
    week_start: date,
    week_end: date,
    now: datetime | None = None,
) -> tuple[int, dict[str, int]]:
    """
    Minutes of [started_at, ended_at] overlapping the week, plus per-day (Sun-index) split.
    Open-ended segments use `now`.
    """
    t0 = _parse_dt(started_at)
    if t0 is None:
        return 0, {}
    t1 = _parse_dt(ended_at) if (ended_at or "").strip() else (now or datetime.now())
    if t1 is None:
        t1 = now or datetime.now()
    if t1 < t0:
        return 0, {}

    week_lo = datetime.combine(week_start, datetime.min.time())
    week_hi = datetime.combine(week_end, datetime.max.time().replace(microsecond=0))
    lo = max(t0, week_lo)
    hi = min(t1, week_hi)
    if hi <= lo:
        return 0, {}

    by_day: dict[str, int] = {}
    total = 0
    # Walk calendar days covering [lo, hi]
    day = lo.date()
    end_day = hi.date()
    while day <= end_day:
        day_lo = datetime.combine(day, datetime.min.time())
        day_hi = datetime.combine(day, datetime.max.time().replace(microsecond=0))
        seg_lo = max(lo, day_lo)
        seg_hi = min(hi, day_hi)
        if seg_hi > seg_lo:
            mins = max(0, int(round((seg_hi - seg_lo).total_seconds() / 60.0)))
            if (seg_hi - seg_lo).total_seconds() > 0 and mins == 0:
                mins = 1
            if mins > 0:
                idx = str(_sun_index(day))
                by_day[idx] = by_day.get(idx, 0) + mins
                total += mins
        day = day + timedelta(days=1)
    return total, by_day


def _normalize_downtime_reason(raw: str, *, from_stage: bool = False) -> str:
    r = (raw or "").strip().lower()
    if from_stage:
        if r in ("waiting_parts", "waiting_customer"):
            return r
        return "other"
    if r in DOWNTIME_REASON_LABELS and r != "unaccounted":
        return r
    if r in ("waiting_parts", "wrong_parts", "waiting_customer", "between_sessions", "found_issue_compose"):
        return r
    if not r:
        return "between_sessions"
    return "other"


def _empty_eff_days() -> dict[str, dict[str, int]]:
    return {
        str(i): {
            "job_minutes": 0,
            "presence_minutes": 0,
            "downtime_minutes": 0,
            "ot_minutes": 0,
            "baseline_minutes": BASELINE_DAY_MINUTES if i in WEEKDAY_SUN_INDEXES else 0,
        }
        for i in range(7)
    }


def build_weekly_efficiency_report(
    orders: list[RepairOrder | dict[str, Any]],
    shifts: list[dict[str, Any]] | None = None,
    *,
    week_start: str | date | None = None,
    include_live: bool = True,
) -> dict[str, Any]:
    """
    Shop efficiency for a Sun–Sat week.

    - baseline: 5×8h normal week (not a cap)
    - worked (job) vs clocked (presence)
    - utilized (job) vs downtime (presence − job), with tagged reasons + unaccounted
    """
    base = build_weekly_tech_report(
        orders, shifts, week_start=week_start, include_live=include_live
    )
    start = date.fromisoformat(base["week_start"])
    end = date.fromisoformat(base["week_end"])
    now = datetime.now()

    # Map item → tech who did the most wrench work on it this week
    item_owner: dict[str, tuple[str, str]] = {}  # "ro:item" -> (tech_id, tech_name)
    item_owner_mins: dict[str, int] = {}
    for t in base["techs"]:
        tid = str(t.get("tech_id") or "")
        tname = str(t.get("tech_name") or "")
        for j in t.get("jobs") or []:
            jk = f"{j.get('ro_id')}:{j.get('item_id')}"
            mins = int(j.get("minutes") or 0)
            if mins > item_owner_mins.get(jk, -1):
                item_owner_mins[jk] = mins
                item_owner[jk] = (tid, tname)

    # Accumulated tagged downtime minutes by tech key → reason → total
    # and by tech → day → reason
    tagged: dict[str, dict[str, int]] = {}
    tagged_days: dict[str, dict[str, dict[str, int]]] = {}
    shop_tagged: dict[str, int] = {}

    def add_tagged(
        tech_key: str,
        tech_id: str,
        tech_name: str,
        reason: str,
        mins: int,
        by_day: dict[str, int],
    ) -> None:
        if mins <= 0:
            return
        reason = _normalize_downtime_reason(reason)
        shop_tagged[reason] = shop_tagged.get(reason, 0) + mins
        if not tech_key:
            return
        bucket = tagged.setdefault(tech_key, {})
        bucket[reason] = bucket.get(reason, 0) + mins
        day_bucket = tagged_days.setdefault(tech_key, {})
        for idx, dm in by_day.items():
            d = day_bucket.setdefault(idx, {})
            d[reason] = d.get(reason, 0) + dm
        # Ensure tech appears even if no presence yet (rare)
        _ = (tech_id, tech_name)

    def tech_key_for(tid: str, tname: str) -> str:
        tid = (tid or "").strip()
        tname = (tname or "").strip()
        return tid or tname.lower() or ""

    for order in orders:
        if isinstance(order, RepairOrder):
            d = order.to_dict()
            items = ensure_work_items_on_order(order)
            item_dicts = [w.to_dict() for w in items]
        else:
            d = dict(order)
            item_dicts = [it for it in (d.get("work_items") or []) if isinstance(it, dict)]
        ro_id = str(d.get("id") or "")

        for it in item_dicts:
            # Long-term projects skip downtime pressure metrics (shop time is expected).
            if str(it.get("queue_lane") or "").strip().lower() == "long_term":
                continue
            wid = str(it.get("id") or "")
            jk = f"{ro_id}:{wid}"
            owner = item_owner.get(jk)
            tid = owner[0] if owner else ""
            tname = owner[1] if owner else ""
            tkey = tech_key_for(tid, tname)

            for entry in it.get("stage_log") or []:
                if not isinstance(entry, dict):
                    continue
                stage = str(entry.get("stage") or "")
                reason = _normalize_downtime_reason(stage, from_stage=True)
                if reason not in ("waiting_parts", "waiting_customer"):
                    continue
                mins, by_day = _clip_segment_minutes(
                    str(entry.get("started_at") or ""),
                    str(entry.get("ended_at") or ""),
                    week_start=start,
                    week_end=end,
                    now=now,
                )
                add_tagged(tkey, tid, tname, reason, mins, by_day)

            # Live open waiting stage
            if include_live:
                status = str(it.get("status") or "").strip().lower()
                if status in ("waiting_parts", "waiting_customer"):
                    entered = str(it.get("stage_entered_at") or it.get("created") or "")
                    mins, by_day = _clip_segment_minutes(
                        entered,
                        "",
                        week_start=start,
                        week_end=end,
                        now=now,
                    )
                    add_tagged(tkey, tid, tname, status, mins, by_day)

            for entry in it.get("downtime_log") or []:
                if not isinstance(entry, dict):
                    continue
                reason = _normalize_downtime_reason(str(entry.get("reason") or ""))
                mins, by_day = _clip_segment_minutes(
                    str(entry.get("started_at") or ""),
                    str(entry.get("ended_at") or ""),
                    week_start=start,
                    week_end=end,
                    now=now,
                )
                add_tagged(tkey, tid, tname, reason, mins, by_day)

            if include_live and (it.get("downtime_started_at") or "").strip():
                reason = _normalize_downtime_reason(str(it.get("downtime_reason") or ""))
                mins, by_day = _clip_segment_minutes(
                    str(it.get("downtime_started_at") or ""),
                    "",
                    week_start=start,
                    week_end=end,
                    now=now,
                )
                add_tagged(tkey, tid, tname, reason, mins, by_day)

    # Index base techs by key
    tech_rows: list[dict[str, Any]] = []
    for t in base["techs"]:
        tid = str(t.get("tech_id") or "")
        tname = str(t.get("tech_name") or "")
        tkey = tech_key_for(tid, tname)
        presence = int(t.get("presence_minutes") or 0)
        job = int(t.get("job_minutes") or 0)
        utilized = job
        downtime_total = max(0, presence - job)
        reason_raw = dict(tagged.get(tkey) or {})
        tagged_sum = sum(reason_raw.values())
        # Cap attributed to downtime_total so utilized + downtime == presence
        scale = (downtime_total / tagged_sum) if tagged_sum > downtime_total > 0 else 1.0
        if tagged_sum > downtime_total and tagged_sum > 0:
            reason_scaled = {
                k: int(round(v * scale)) for k, v in reason_raw.items() if v > 0
            }
            # Fix rounding drift
            drift = downtime_total - sum(reason_scaled.values())
            if drift != 0 and reason_scaled:
                top = max(reason_scaled, key=reason_scaled.get)
                reason_scaled[top] = max(0, reason_scaled[top] + drift)
            reason_mins = reason_scaled
            attributed = sum(reason_mins.values())
        else:
            reason_mins = {k: v for k, v in reason_raw.items() if v > 0}
            attributed = min(tagged_sum, downtime_total)
        unaccounted = max(0, downtime_total - attributed)
        if unaccounted:
            reason_mins["unaccounted"] = reason_mins.get("unaccounted", 0) + unaccounted

        baseline = BASELINE_WEEK_MINUTES if (presence > 0 or job > 0) else 0
        ot = max(0, presence - BASELINE_WEEK_MINUTES) if presence > 0 else 0
        wrench_rate = (job / presence) if presence > 0 else (1.0 if job > 0 else 0.0)
        baseline_fill = (job / BASELINE_WEEK_MINUTES) if baseline > 0 else 0.0
        utilized_rate = wrench_rate

        days = _empty_eff_days()
        src_days = t.get("days") or {}
        for i in range(7):
            idx = str(i)
            src = src_days.get(idx) or {}
            job_d = int(src.get("job_minutes") or 0)
            pres_d = int(src.get("presence_minutes") or 0)
            dt_d = max(0, pres_d - job_d)
            days[idx]["job_minutes"] = job_d
            days[idx]["presence_minutes"] = pres_d
            days[idx]["downtime_minutes"] = dt_d
            if i in WEEKDAY_SUN_INDEXES:
                days[idx]["ot_minutes"] = max(0, pres_d - BASELINE_DAY_MINUTES)
            else:
                days[idx]["ot_minutes"] = pres_d  # weekend presence is over weekday baseline plan

        reasons_out = [
            {
                "reason": k,
                "label": DOWNTIME_REASON_LABELS.get(k, k.replace("_", " ").title()),
                "minutes": int(v),
            }
            for k, v in sorted(reason_mins.items(), key=lambda kv: -kv[1])
            if int(v) > 0
        ]

        tech_rows.append(
            {
                "tech_id": tid,
                "tech_name": tname,
                "baseline_minutes": baseline,
                "job_minutes": job,
                "presence_minutes": presence,
                "utilized_minutes": utilized,
                "downtime_minutes": downtime_total,
                "attributed_downtime_minutes": attributed,
                "unaccounted_minutes": unaccounted,
                "ot_minutes": ot,
                "worked_vs_clocked_rate": round(wrench_rate, 4),
                "utilized_rate": round(utilized_rate, 4),
                "baseline_fill": round(baseline_fill, 4),
                "downtime_by_reason": reasons_out,
                "days": days,
                "jobs": t.get("jobs") or [],
            }
        )

    tech_rows.sort(
        key=lambda r: (
            -int(r.get("presence_minutes") or 0),
            -int(r.get("job_minutes") or 0),
            str(r.get("tech_name") or "").lower(),
        )
    )

    shop_presence = sum(int(r["presence_minutes"]) for r in tech_rows)
    shop_job = sum(int(r["job_minutes"]) for r in tech_rows)
    shop_downtime = sum(int(r["downtime_minutes"]) for r in tech_rows)
    shop_ot = sum(int(r["ot_minutes"]) for r in tech_rows)
    techs_present = sum(
        1 for r in tech_rows if int(r["presence_minutes"]) > 0 or int(r["job_minutes"]) > 0
    )
    shop_baseline = techs_present * BASELINE_WEEK_MINUTES

    # Shop downtime reasons: rebuild from per-tech (reconciled) so they sum cleanly
    shop_reasons: dict[str, int] = {}
    for r in tech_rows:
        for entry in r.get("downtime_by_reason") or []:
            k = str(entry.get("reason") or "")
            shop_reasons[k] = shop_reasons.get(k, 0) + int(entry.get("minutes") or 0)

    shop_reasons_out = [
        {
            "reason": k,
            "label": DOWNTIME_REASON_LABELS.get(k, k.replace("_", " ").title()),
            "minutes": int(v),
        }
        for k, v in sorted(shop_reasons.items(), key=lambda kv: -kv[1])
        if int(v) > 0
    ]

    return {
        "week_start": base["week_start"],
        "week_end": base["week_end"],
        "generated_at": now_iso(),
        "baseline_day_minutes": BASELINE_DAY_MINUTES,
        "baseline_week_minutes": BASELINE_WEEK_MINUTES,
        "techs": tech_rows,
        "shop": {
            "baseline_minutes": shop_baseline,
            "job_minutes": shop_job,
            "presence_minutes": shop_presence,
            "utilized_minutes": shop_job,
            "downtime_minutes": shop_downtime,
            "ot_minutes": shop_ot,
            "techs_present": techs_present,
            "worked_vs_clocked_rate": round(
                (shop_job / shop_presence) if shop_presence > 0 else 0.0, 4
            ),
            "utilized_rate": round(
                (shop_job / shop_presence) if shop_presence > 0 else 0.0, 4
            ),
            "baseline_fill": round(
                (shop_job / shop_baseline) if shop_baseline > 0 else 0.0, 4
            ),
            "downtime_by_reason": shop_reasons_out,
        },
    }


def previous_closed_week_start(today: date | None = None) -> date:
    """Sunday of the week before the current Sun–Sat week (always closed relative to today)."""
    today = today or date.today()
    return sunday_on_or_before(today) - timedelta(days=7)


def _orders_and_shifts_for_week(
    store: Any,
    week_start: date,
    *,
    remote: Any | None = None,
) -> tuple[list[Any], list[dict[str, Any]]]:
    """Merge local + remote ROs and fetch shifts for the week (best-effort)."""
    from carro.core.models import RepairOrder
    from carro.storage.remote import RemoteClient

    start_s = week_start.isoformat()
    end_s = week_end_saturday(week_start).isoformat()
    by_id: dict[str, RepairOrder] = {}
    for order in store.list_orders():
        by_id[order.id] = order
    client = remote if remote is not None else RemoteClient()
    shifts: list[dict[str, Any]] = []
    if getattr(client, "enabled", False):
        try:
            for raw in client.list_ros():
                try:
                    order = RepairOrder.from_dict(raw)
                except Exception:
                    continue
                local = by_id.get(order.id)
                if local is None or (order.updated or "") >= (local.updated or ""):
                    by_id[order.id] = order
        except Exception:
            pass
        try:
            shifts = list(
                client.list_shifts(day_from=start_s, day_to=end_s, limit=2000).get(
                    "shifts"
                )
                or []
            )
        except Exception:
            shifts = []
    return list(by_id.values()), shifts


def archive_closed_week_if_needed(
    store: Any,
    *,
    remote: Any | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """
    Insert-if-absent archive of the previous closed Sun–Sat week.

    Payload is the tech report (include_live=False) plus nested efficiency.
    Does not overwrite an existing shop snapshot (manual Save may upsert).
    """
    from carro.storage.remote import RemoteClient

    client = remote if remote is not None else RemoteClient()
    if not getattr(client, "enabled", False):
        return {"ok": False, "skipped": "no_server"}

    today = today or date.today()
    week_start = previous_closed_week_start(today)
    week_end = week_end_saturday(week_start)
    if today <= week_end:
        return {
            "ok": True,
            "skipped": "not_closed",
            "week_start": week_start.isoformat(),
        }

    start_s = week_start.isoformat()
    end_s = week_end.isoformat()
    try:
        existing = client.get_weekly_report_snapshot(start_s).get("snapshot")
    except Exception as exc:
        return {"ok": False, "error": f"snapshot check failed: {exc}", "week_start": start_s}
    if existing:
        return {"ok": True, "skipped": "exists", "week_start": start_s}

    orders, shifts = _orders_and_shifts_for_week(store, week_start, remote=client)
    tech = build_weekly_tech_report(
        orders, shifts, week_start=week_start, include_live=False
    )
    efficiency = build_weekly_efficiency_report(
        orders, shifts, week_start=week_start, include_live=False
    )
    payload = dict(tech)
    payload["efficiency"] = efficiency
    try:
        snap = client.save_weekly_report(
            start_s,
            week_end=end_s,
            payload=payload,
            created_by="autosync",
            created_by_id="system",
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc), "week_start": start_s}
    return {
        "ok": True,
        "archived": True,
        "week_start": start_s,
        "week_end": end_s,
        "snapshot": snap.get("snapshot") if isinstance(snap, dict) else snap,
    }
