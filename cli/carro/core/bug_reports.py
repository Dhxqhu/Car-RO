"""Local + shop bug reports for documenting user-facing issues."""

from __future__ import annotations

import json
import platform
import uuid
from pathlib import Path
from typing import Any

from carro.config import CONFIG_DIR, load_config
from carro.core.models import now_iso
from carro.version import version_payload

BUG_REPORTS_FILE = CONFIG_DIR / "bug_reports.jsonl"
SEVERITIES = ("low", "medium", "high")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def normalize_severity(raw: object, *, default: str = "medium") -> str:
    st = str(raw or "").strip().lower()
    return st if st in SEVERITIES else default


def build_report(
    *,
    title: str,
    description: str,
    severity: str = "medium",
    steps: str = "",
    client: str = "",
    reporter_role: str = "",
    reporter_id: str = "",
    reporter_name: str = "",
) -> dict[str, Any]:
    title_clean = (title or "").strip()
    desc_clean = (description or "").strip()
    if not title_clean:
        raise ValueError("Title required")
    if not desc_clean:
        raise ValueError("Description required")
    cfg = load_config()
    return {
        "id": f"bug-{uuid.uuid4().hex[:12]}",
        "created_at": now_iso(),
        "title": title_clean[:200],
        "description": desc_clean[:8000],
        "steps": (steps or "").strip()[:4000],
        "severity": normalize_severity(severity),
        "client": (client or "").strip()[:40],
        "reporter_role": (reporter_role or "").strip()[:40],
        "reporter_id": (reporter_id or "").strip()[:80],
        "reporter_name": (reporter_name or "").strip()[:120],
        "shop_name": str(cfg.get("shop_name") or "").strip(),
        "server_url": str(cfg.get("server_url") or "").strip(),
        "hostname": platform.node() or "",
        **{k: v for k, v in version_payload().items()},
        "synced": False,
        "sync_error": "",
    }


def append_local(report: dict[str, Any]) -> dict[str, Any]:
    _ensure_parent(BUG_REPORTS_FILE)
    line = json.dumps(report, ensure_ascii=False) + "\n"
    with BUG_REPORTS_FILE.open("a", encoding="utf-8") as f:
        f.write(line)
    return report


def list_local(*, limit: int = 50) -> list[dict[str, Any]]:
    if not BUG_REPORTS_FILE.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        text = BUG_REPORTS_FILE.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict):
            rows.append(raw)
    rows.reverse()
    lim = max(1, min(int(limit or 50), 200))
    return rows[:lim]


def mark_synced(report_id: str, *, synced: bool, sync_error: str = "") -> None:
    rid = (report_id or "").strip()
    if not rid or not BUG_REPORTS_FILE.is_file():
        return
    try:
        text = BUG_REPORTS_FILE.read_text(encoding="utf-8")
    except OSError:
        return
    out_lines: list[str] = []
    changed = False
    for line in text.splitlines():
        raw_line = line.strip()
        if not raw_line:
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError:
            out_lines.append(raw_line)
            continue
        if isinstance(row, dict) and str(row.get("id") or "") == rid:
            row["synced"] = bool(synced)
            row["sync_error"] = (sync_error or "").strip()[:400]
            changed = True
            out_lines.append(json.dumps(row, ensure_ascii=False))
        else:
            out_lines.append(json.dumps(row, ensure_ascii=False) if isinstance(row, dict) else raw_line)
    if changed:
        _ensure_parent(BUG_REPORTS_FILE)
        BUG_REPORTS_FILE.write_text("\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")


def try_push_remote(report: dict[str, Any]) -> str:
    """
    Best-effort push to shop server.
    Returns: synced | skipped | error:...
    """
    try:
        from carro.storage.remote import RemoteClient

        remote = RemoteClient()
        if not remote.enabled:
            return "skipped"
        remote.post_bug_report(report)
        mark_synced(str(report.get("id") or ""), synced=True, sync_error="")
        return "synced"
    except Exception as exc:
        err = str(exc)[:300]
        mark_synced(str(report.get("id") or ""), synced=False, sync_error=err)
        return f"error: {err}"


def submit_report(
    *,
    title: str,
    description: str,
    severity: str = "medium",
    steps: str = "",
    client: str = "",
    reporter_role: str = "",
    reporter_id: str = "",
    reporter_name: str = "",
) -> dict[str, Any]:
    report = build_report(
        title=title,
        description=description,
        severity=severity,
        steps=steps,
        client=client,
        reporter_role=reporter_role,
        reporter_id=reporter_id,
        reporter_name=reporter_name,
    )
    append_local(report)
    sync_status = try_push_remote(report)
    report["sync_status"] = sync_status
    report["synced"] = sync_status == "synced"
    if sync_status.startswith("error:"):
        report["sync_error"] = sync_status[6:].strip()
    return report
