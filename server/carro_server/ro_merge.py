"""Amend concurrent RO writes so a stale PUT cannot drop notes or rows.

Shop server stores each RO as one JSON document. Clients may push a full
copy after editing offline or from a cached screen. When the client's
``_base_updated`` still matches the shop row, the PUT is authoritative
(intentional deletes and field clears stand). Otherwise this module folds
the incoming document into the shop copy:

* free-text is kept / appended, never replaced by a shorter stale string
* lists (work items, photos, parts, logs) are unioned by id
* empty incoming values do not clear shop data
* status only moves forward

No carro.core dependency — safe to import from carro-server alone.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

META_KEYS = ("_actor", "_actor_id", "_base_updated")

TEXT_AMEND_RO = ("complaint", "tech_notes", "obd_snapshot")
IDENTITY_RO = (
    "first_name",
    "last_name",
    "phone",
    "year",
    "make",
    "model",
    "vin",
    "mileage",
    "plate",
)
BOOL_OR_RO = ("waiter", "urgent")
STAMP_EARLIEST = ("created", "started_at")
STAMP_LATEST = (
    "done_at",
    "billed_out_at",
    "canceled_at",
    "no_call_no_show_at",
    "waiting_since",
    "parts_requested_at",
    "approval_requested_at",
    "assigned_at",
    "current_since",
)
PERSON_KEEP = (
    "technician_id",
    "technician_name",
    "assigned_to_id",
    "assigned_to_name",
    "current_tech_id",
    "current_tech_name",
    "current_item_id",
    "parts_requested_by",
    "parts_requested_by_id",
    "approval_requested_by",
    "approval_requested_by_id",
)

TEXT_AMEND_ITEM = ("concern", "notes", "private_notes")
TEXT_AMEND_FI = ("description", "notes")
TEXT_AMEND_PHOTO = ("notes",)
TEXT_AMEND_PART = ("description", "part_number", "oem_part_number", "wrong_note")

RO_STATUS_RANK = {
    "open": 0,
    "assigned": 1,
    "in_progress": 2,
    "waiting_parts": 3,
    "waiting_customer": 3,
    "done": 4,
    "billed_out": 5,
    "canceled": 5,
    "no_call_no_show": 5,
}
WI_STATUS_RANK = {
    "open": 0,
    "in_progress": 1,
    "waiting_parts": 2,
    "waiting_customer": 2,
    "done": 3,
    "declined": 3,
}
PART_STATUS_RANK = {
    "new_request": 0,
    "ordered": 1,
    "received": 2,
    "received_wrong": 3,
}

AMEND_MARK = "\n\n---\n"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return False
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return str(value).strip() == ""


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _strip_meta(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if k not in META_KEYS}


def _bases_match(base_updated: str, server_updated: str) -> bool:
    b = (base_updated or "").strip()
    s = (server_updated or "").strip()
    return bool(b) and bool(s) and b == s


def merge_text(server: Any, incoming: Any, *, actor: str = "") -> str:
    """Keep both distinct note bodies; prefer a string that already contains the other."""
    s = _s(server)
    i = _s(incoming)
    s_st, i_st = s.strip(), i.strip()
    if s == i or s_st == i_st:
        return s if s_st else i
    if not s_st:
        return i
    if not i_st:
        return s
    if i_st in s:
        return s
    if s_st in i:
        return i
    who = (actor or "").strip() or "another editor"
    block = f"[{who}] {i_st}"
    if block in s or i_st in s:
        return s
    return s.rstrip() + AMEND_MARK + block


def _forward_status(server: Any, incoming: Any, ranks: dict[str, int]) -> str:
    s = _s(server).strip().lower()
    i = _s(incoming).strip().lower()
    if not i:
        return s
    if not s:
        return i
    rs = ranks.get(s, 0)
    ri = ranks.get(i, 0)
    if ri > rs:
        return i
    if rs > ri:
        return s
    # Same rank (e.g. waiting_parts vs waiting_customer): keep incoming — it is
    # the writer's intent; shop copy is not "ahead".
    return i if i in ranks else s


def _max_int(*vals: Any) -> int:
    best = 0
    for v in vals:
        try:
            best = max(best, int(v or 0))
        except (TypeError, ValueError):
            continue
    return best


def _later_stamp(a: Any, b: Any) -> str:
    sa, sb = _s(a).strip(), _s(b).strip()
    if not sa:
        return sb
    if not sb:
        return sa
    return sa if sa >= sb else sb


def _earlier_stamp(a: Any, b: Any) -> str:
    sa, sb = _s(a).strip(), _s(b).strip()
    if not sa:
        return sb
    if not sb:
        return sa
    return sa if sa <= sb else sb


def _keep_nonempty(server: Any, incoming: Any) -> Any:
    if _blank(incoming):
        return server
    if _blank(server):
        return incoming
    return incoming


def _merge_identity(
    server: Any, incoming: Any, *, field: str, actor: str
) -> tuple[str, str | None]:
    s, i = _s(server).strip(), _s(incoming).strip()
    if s == i:
        return s, None
    if not i:
        return s, None
    if not s:
        return i, None
    who = (actor or "another editor").strip()
    # VIN/plate/phone: never shrink a more complete value.
    if field in ("vin", "plate", "phone"):
        if len(i) > len(s):
            return i, f"{field}: kept {i!r}; shop had {s!r}"
        if len(s) > len(i):
            return s, f"{field}: kept {s!r}; also entered {i!r} by {who}"
        return i, f"{field}: now {i!r}; was {s!r}"
    # Other identity: this PUT is someone saving the form. Keep both in the trail.
    return i, f"{field}: now {i!r}; was {s!r} ({who})"


def _append_sync_note(out: dict[str, Any], detail: str, actor: str) -> None:
    if not detail:
        return
    actions = [
        a
        for a in (out.get("advisor_actions") or [])
        if isinstance(a, dict)
    ]
    actions.append(
        {
            "at": _now(),
            "action": "sync_amend",
            "advisor_id": "",
            "advisor_name": (actor or "").strip(),
            "ro_id": _s(out.get("id")),
            "work_item_id": "",
            "found_issue_id": "",
            "note": "",
            "detail": detail[:240],
        }
    )
    out["advisor_actions"] = actions


def _row_id(row: dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = _s(row.get(k)).strip()
        if v:
            return v
    return ""


def _fingerprint(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    return "|".join(_s(row.get(k)).strip() for k in keys)


def _union_rows(
    server_rows: list[Any],
    incoming_rows: list[Any],
    *,
    id_key: str = "id",
    fingerprint: tuple[str, ...] | None = None,
    merge_row: Any | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    index: dict[str, int] = {}

    def _key(row: dict[str, Any]) -> str:
        if fingerprint:
            fp = _fingerprint(row, fingerprint)
            if fp.strip("|"):
                return "fp:" + fp
        rid = _row_id(row, id_key)
        return "id:" + rid if rid else ""

    for raw in server_rows or []:
        if not isinstance(raw, dict):
            continue
        k = _key(raw)
        if k and k in index:
            continue
        out.append(dict(raw))
        if k:
            index[k] = len(out) - 1
    for raw in incoming_rows or []:
        if not isinstance(raw, dict):
            continue
        k = _key(raw)
        if k and k in index:
            if merge_row:
                out[index[k]] = merge_row(out[index[k]], raw)
            continue
        if k:
            index[k] = len(out)
        out.append(dict(raw) if not merge_row else dict(raw))
    return out


def _merge_part(server: dict[str, Any], incoming: dict[str, Any], *, actor: str) -> dict[str, Any]:
    out = dict(server)
    for key in TEXT_AMEND_PART:
        out[key] = merge_text(server.get(key), incoming.get(key), actor=actor)
    for key in (
        "manufacturer",
        "brand",
        "supplier",
        "requested_at",
        "ordered_at",
        "received_at",
        "updated_at",
    ):
        out[key] = _keep_nonempty(server.get(key), incoming.get(key))
    out["status"] = _forward_status(
        server.get("status"), incoming.get("status"), PART_STATUS_RANK
    )
    out["wrong_count"] = _max_int(server.get("wrong_count"), incoming.get("wrong_count"))
    if incoming.get("id"):
        out["id"] = incoming.get("id") or server.get("id")
    return out


def _merge_found_issue(
    server: dict[str, Any], incoming: dict[str, Any], *, actor: str
) -> dict[str, Any]:
    out = dict(server)
    for key in TEXT_AMEND_FI:
        out[key] = merge_text(server.get(key), incoming.get(key), actor=actor)
    fi_rank = {"draft": 0, "pending": 1, "converted": 2, "declined": 2}
    out["status"] = _forward_status(server.get("status"), incoming.get("status"), fi_rank)
    for key in (
        "kind",
        "decline_reason",
        "found_by",
        "found_by_id",
        "found_at",
        "resolved_by",
        "resolved_by_id",
        "resolved_at",
        "work_item_id",
        "source_work_item_id",
        "updated",
    ):
        out[key] = _keep_nonempty(server.get(key), incoming.get(key))
    out["compose_downtime_minutes"] = _max_int(
        server.get("compose_downtime_minutes"),
        incoming.get("compose_downtime_minutes"),
    )
    out["photos"] = _union_rows(
        list(server.get("photos") or []),
        list(incoming.get("photos") or []),
        id_key="id",
    )
    return out


def _merge_photo(
    server: dict[str, Any], incoming: dict[str, Any], *, actor: str
) -> dict[str, Any]:
    out = dict(server)
    for key, val in incoming.items():
        if key in TEXT_AMEND_PHOTO:
            out[key] = merge_text(server.get(key), val, actor=actor)
        elif key == "id":
            out[key] = server.get("id") or val
        elif _blank(out.get(key)) and not _blank(val):
            out[key] = val
        elif key == "remote" and (val is True or server.get("remote") is True):
            out[key] = True
    return out


def _merge_work_item(
    server: dict[str, Any], incoming: dict[str, Any], *, actor: str
) -> dict[str, Any]:
    out = dict(server)
    for key in TEXT_AMEND_ITEM:
        out[key] = merge_text(server.get(key), incoming.get(key), actor=actor)
    out["status"] = _forward_status(
        server.get("status"), incoming.get("status"), WI_STATUS_RANK
    )
    out["item_type"] = _keep_nonempty(server.get("item_type"), incoming.get("item_type"))
    try:
        sp = int(server.get("priority") or 0)
        ip = int(incoming.get("priority") or 0)
        out["priority"] = ip if ip else sp
    except (TypeError, ValueError):
        out["priority"] = server.get("priority") or incoming.get("priority") or 0
    try:
        st = int(server.get("car_turn") or 0)
        it = int(incoming.get("car_turn") or 0)
        out["car_turn"] = it if it else st
    except (TypeError, ValueError):
        out["car_turn"] = server.get("car_turn") or incoming.get("car_turn") or 0
    for key in (
        "created_by",
        "created_by_id",
        "created_by_role",
        "notes_by",
        "notes_by_id",
        "notes_by_role",
        "assigned_to_id",
        "assigned_to_name",
        "assigned_at",
        "wait_requested_by",
        "wait_requested_by_id",
        "wait_kind",
        "queue_lane",
        "pending_queue_lane",
        "queue_day",
        "worked_first_at",
        "worked_last_at",
        "timer_started_at",
        "timer_tech_id",
        "timer_tech_name",
        "stage_entered_at",
        "downtime_started_at",
        "downtime_reason",
        "updated_by",
        "updated_by_role",
        "created",
        "updated",
        "time_group_id",
        "completed_with_id",
    ):
        out[key] = _keep_nonempty(server.get(key), incoming.get(key))
    # Prefer an open timer if either side has one.
    if _s(incoming.get("timer_started_at")).strip() and not _s(
        server.get("timer_started_at")
    ).strip():
        out["timer_started_at"] = incoming.get("timer_started_at")
        out["timer_tech_id"] = incoming.get("timer_tech_id") or out.get("timer_tech_id")
        out["timer_tech_name"] = incoming.get("timer_tech_name") or out.get(
            "timer_tech_name"
        )
    out["due_eod"] = bool(server.get("due_eod") or incoming.get("due_eod"))
    out["worked_minutes"] = _max_int(
        server.get("worked_minutes"), incoming.get("worked_minutes")
    )
    out["downtime_minutes"] = _max_int(
        server.get("downtime_minutes"), incoming.get("downtime_minutes")
    )
    stot: dict[str, int] = {}
    for src in (server.get("stage_totals"), incoming.get("stage_totals")):
        if isinstance(src, dict):
            for k, v in src.items():
                stot[k] = _max_int(stot.get(k), v)
    if stot:
        out["stage_totals"] = stot
    nd_s = server.get("next_day_request") if isinstance(server.get("next_day_request"), dict) else {}
    nd_i = incoming.get("next_day_request") if isinstance(incoming.get("next_day_request"), dict) else {}
    out["next_day_request"] = nd_i if nd_i else nd_s
    ids_s = [str(x) for x in (server.get("linked_photo_ids") or []) if str(x).strip()]
    ids_i = [str(x) for x in (incoming.get("linked_photo_ids") or []) if str(x).strip()]
    seen: set[str] = set()
    linked: list[str] = []
    for pid in ids_s + ids_i:
        if pid not in seen:
            seen.add(pid)
            linked.append(pid)
    out["linked_photo_ids"] = linked
    covers: list[str] = []
    cseen: set[str] = set()
    for src in (server.get("covers_item_ids"), incoming.get("covers_item_ids")):
        if not isinstance(src, list):
            continue
        for cid in src:
            s = str(cid).strip()
            if s and s not in cseen:
                cseen.add(s)
                covers.append(s)
    if covers:
        out["covers_item_ids"] = covers
    snap_s = server.get("merge_snapshot") if isinstance(server.get("merge_snapshot"), dict) else {}
    snap_i = incoming.get("merge_snapshot") if isinstance(incoming.get("merge_snapshot"), dict) else {}
    out["merge_snapshot"] = snap_i or snap_s
    out["parts"] = _union_rows(
        list(server.get("parts") or []),
        list(incoming.get("parts") or []),
        id_key="id",
        merge_row=lambda a, b: _merge_part(a, b, actor=actor),
    )
    out["time_log"] = _union_rows(
        list(server.get("time_log") or []),
        list(incoming.get("time_log") or []),
        fingerprint=("at", "tech_id", "minutes", "source", "note"),
    )
    out["stage_log"] = _union_rows(
        list(server.get("stage_log") or []),
        list(incoming.get("stage_log") or []),
        fingerprint=("stage", "started_at", "ended_at"),
    )
    out["downtime_log"] = _union_rows(
        list(server.get("downtime_log") or []),
        list(incoming.get("downtime_log") or []),
        fingerprint=("reason", "started_at", "ended_at"),
    )
    return out


def _heuristic_merge(
    server: dict[str, Any], incoming: dict[str, Any], *, actor: str
) -> dict[str, Any]:
    out = dict(server)
    out["id"] = _s(incoming.get("id") or server.get("id"))

    for key in TEXT_AMEND_RO:
        out[key] = merge_text(server.get(key), incoming.get(key), actor=actor)

    for key in IDENTITY_RO:
        kept, note = _merge_identity(
            server.get(key), incoming.get(key), field=key, actor=actor
        )
        out[key] = kept
        if note:
            _append_sync_note(out, note, actor)

    for key in BOOL_OR_RO:
        out[key] = bool(server.get(key) or incoming.get(key))

    out["status"] = _forward_status(
        server.get("status"), incoming.get("status"), RO_STATUS_RANK
    )

    for key in STAMP_EARLIEST:
        out[key] = _earlier_stamp(server.get(key), incoming.get(key))
    for key in STAMP_LATEST:
        out[key] = _later_stamp(server.get(key), incoming.get(key))

    for key in PERSON_KEEP:
        out[key] = _keep_nonempty(server.get(key), incoming.get(key))
    # Current bay tech: later current_since wins when both set.
    if (
        not _blank(incoming.get("current_tech_id") or incoming.get("current_tech_name"))
        and not _blank(server.get("current_tech_id") or server.get("current_tech_name"))
        and _s(incoming.get("current_since")) > _s(server.get("current_since"))
    ):
        out["current_tech_id"] = incoming.get("current_tech_id")
        out["current_tech_name"] = incoming.get("current_tech_name")
        out["current_since"] = incoming.get("current_since")
        out["current_item_id"] = incoming.get("current_item_id") or out.get(
            "current_item_id"
        )

    out["work_items"] = _union_rows(
        list(server.get("work_items") or []),
        list(incoming.get("work_items") or []),
        id_key="id",
        merge_row=lambda a, b: _merge_work_item(a, b, actor=actor),
    )
    out["found_issues"] = _union_rows(
        list(server.get("found_issues") or []),
        list(incoming.get("found_issues") or []),
        id_key="id",
        merge_row=lambda a, b: _merge_found_issue(a, b, actor=actor),
    )
    out["photos"] = _union_rows(
        list(server.get("photos") or []),
        list(incoming.get("photos") or []),
        id_key="id",
        merge_row=lambda a, b: _merge_photo(a, b, actor=actor),
    )
    out["advisor_actions"] = _union_rows(
        list(out.get("advisor_actions") or server.get("advisor_actions") or []),
        list(incoming.get("advisor_actions") or []),
        fingerprint=("at", "action", "advisor_id", "work_item_id", "found_issue_id", "detail"),
    )

    # Any other scalar keys incoming introduced (forward-compat).
    for key, val in incoming.items():
        if key in META_KEYS or key in out:
            continue
        if _blank(out.get(key)) and not _blank(val):
            out[key] = val

    out["updated"] = _later_stamp(server.get("updated"), incoming.get("updated")) or _now()
    return _strip_meta(out)


def merge_repair_order(
    *,
    server: dict[str, Any] | None,
    incoming: dict[str, Any],
    base_updated: str = "",
    actor: str = "",
) -> dict[str, Any]:
    """
    Return the document to store.

    * No shop copy → create from incoming.
    * ``base_updated`` matches shop ``updated`` → incoming is based on current;
      take it as-is (deletes and clears are intentional).
    * Otherwise heuristic amend (offline race / stale editor).
    """
    incoming = _strip_meta(dict(incoming or {}))
    if not server:
        return incoming
    server = _strip_meta(dict(server))
    if _bases_match(base_updated, _s(server.get("updated"))):
        return incoming
    return _heuristic_merge(server, incoming, actor=actor)
