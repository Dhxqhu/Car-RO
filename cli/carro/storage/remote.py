"""Remote sync client for optional carro-server."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from carro.config import load_config
from carro.core.models import RepairOrder
from carro.version import APP_VERSION, REQUIRED_SERVER_API


class ServerTooOldError(RuntimeError):
    """This client/engine build needs a newer carro-server api_version."""


class RemoteClient:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        cfg = load_config()
        self.base = (base_url if base_url is not None else cfg.get("server_url") or "").rstrip("/")
        self.token = token if token is not None else cfg.get("token") or ""
        self._compat_checked = False

    @property
    def enabled(self) -> bool:
        return bool(self.base)

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def health(self) -> dict[str, Any]:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{self.base}/health", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def check_server_compat(self, *, force: bool = False) -> dict[str, Any] | None:
        """
        One-shot guard: if this build requires a newer shop API than the server
        advertises, raise ServerTooOldError. Never nags about newer servers.
        Older servers without api_version are treated as api_version=0.
        Network/auth failures propagate to the caller.
        """
        if not self.enabled:
            return None
        if self._compat_checked and not force:
            return None
        info = self.health()
        self._compat_checked = True
        raw = info.get("api_version")
        try:
            server_api = int(raw) if raw is not None and str(raw).strip() != "" else 0
        except (TypeError, ValueError):
            server_api = 0
        if REQUIRED_SERVER_API > server_api:
            raise ServerTooOldError(
                f"This Car-RO build ({APP_VERSION}) needs shop server api_version "
                f">={REQUIRED_SERVER_API}, but the server reports {server_api}. "
                "Update carro-server first (docs/UPDATING.md), or roll this PC back "
                "to a matching release. Working shops do not need to update."
            )
        return info

    def upsert_ro(
        self,
        order: RepairOrder,
        *,
        actor: str | None = None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        payload = order.to_dict()
        # Who made this change (for notifications — other clients exclude self)
        who = (actor if actor is not None else order.technician_name) or ""
        who_id = (actor_id if actor_id is not None else order.technician_id) or ""
        if who:
            payload["_actor"] = who
        if who_id:
            payload["_actor_id"] = who_id
        with httpx.Client(timeout=30.0) as client:
            r = client.put(
                f"{self.base}/ros/{order.id}",
                headers=self._headers(),
                json=payload,
            )
            r.raise_for_status()
            return r.json()

    def list_ros(self) -> list[dict[str, Any]]:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(f"{self.base}/ros", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def search_ros(
        self, query: str = "", *, timeout: float = 30.0, **filters: str
    ) -> list[dict[str, Any]]:
        params = {k: v for k, v in {"q": query, **filters}.items() if v}
        with httpx.Client(timeout=timeout) as client:
            r = client.get(f"{self.base}/ros", headers=self._headers(), params=params)
            r.raise_for_status()
            return r.json()

    def get_ro(self, ro_id: str, *, timeout: float = 30.0) -> dict[str, Any]:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(f"{self.base}/ros/{ro_id}", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def delete_ro(self, ro_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            r = client.delete(f"{self.base}/ros/{ro_id}", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def create_upload_session(
        self,
        ro_id: str,
        *,
        tag: str = "intake",
        ttl_sec: int | None = None,
        kind: str = "web",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"ro_id": ro_id, "tag": tag, "kind": kind}
        if ttl_sec is not None:
            payload["ttl_sec"] = ttl_sec
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{self.base}/upload-sessions",
                headers=self._headers(),
                json=payload,
            )
            r.raise_for_status()
            return r.json()

    def upload_session_status(self, token: str) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(f"{self.base}/u/{token}/status")
            r.raise_for_status()
            return r.json()

    def upload_photo(
        self,
        ro_id: str,
        path: str,
        *,
        tag: str = "other",
        filename: str | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        from pathlib import Path

        p = Path(path)
        files = {"file": (filename or p.name, p.read_bytes(), "application/octet-stream")}
        data = {"tag": tag, "notes": notes or ""}
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                f"{self.base}/ros/{ro_id}/photos",
                headers=self._headers(),
                files=files,
                data=data,
            )
            r.raise_for_status()
            return r.json()

    def download_photo(
        self,
        ro_id: str,
        relpath: str,
        dest: Path,
        *,
        volume: str | None = None,
    ) -> Path:
        from pathlib import Path as P

        dest = P(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        params = {}
        if volume:
            params["volume"] = volume
        with httpx.Client(timeout=120.0) as client:
            r = client.get(
                f"{self.base}/ros/{ro_id}/photos/{P(relpath).name}",
                headers=self._headers(),
                params=params,
            )
            r.raise_for_status()
            dest.write_bytes(r.content)
        return dest

    def get_technicians(self) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(f"{self.base}/technicians", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def put_technicians(self, roster: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            r = client.put(
                f"{self.base}/technicians",
                headers=self._headers(),
                json=roster,
            )
            r.raise_for_status()
            return r.json()

    def get_advisors(self) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(f"{self.base}/advisors", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def put_advisors(self, roster: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            r = client.put(
                f"{self.base}/advisors",
                headers=self._headers(),
                json=roster,
            )
            r.raise_for_status()
            return r.json()

    def get_suppliers(self) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(f"{self.base}/suppliers", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def put_suppliers(self, roster: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            r = client.put(
                f"{self.base}/suppliers",
                headers=self._headers(),
                json=roster,
            )
            r.raise_for_status()
            return r.json()

    def post_bug_report(self, report: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(
                f"{self.base}/bug-reports",
                headers=self._headers(),
                json=report,
            )
            r.raise_for_status()
            return r.json()

    def list_bug_reports(self, *, limit: int = 50) -> dict[str, Any]:
        with httpx.Client(timeout=20.0) as client:
            r = client.get(
                f"{self.base}/bug-reports",
                headers=self._headers(),
                params={"limit": limit},
            )
            r.raise_for_status()
            return r.json()

    def post_advisor_presence(
        self, *, advisor_id: str, name: str = "", client_host: str = ""
    ) -> dict[str, Any]:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(
                f"{self.base}/advisors/presence",
                headers=self._headers(),
                json={
                    "advisor_id": advisor_id,
                    "name": name,
                    "client_host": client_host,
                },
            )
            r.raise_for_status()
            return r.json()

    def list_advisor_presence(self, *, within_seconds: int = 90) -> dict[str, Any]:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(
                f"{self.base}/advisors/presence",
                headers=self._headers(),
                params={"within_seconds": within_seconds},
            )
            r.raise_for_status()
            return r.json()

    def clear_advisor_presence(self, advisor_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=10.0) as client:
            r = client.delete(
                f"{self.base}/advisors/presence/{advisor_id}",
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    def advisor_recent(self, minutes: int = 120) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{self.base}/advisor/recent",
                headers=self._headers(),
                params={"minutes": minutes},
            )
            r.raise_for_status()
            return r.json()

    def search_parts(
        self,
        *,
        part_number: str = "",
        manufacturer: str = "",
        status: str = "",
        ro_id: str = "",
        q: str = "",
        include_received: bool = False,
        limit: int = 500,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if part_number:
            params["part_number"] = part_number
        if manufacturer:
            params["manufacturer"] = manufacturer
        if status:
            params["status"] = status
        if ro_id:
            params["ro_id"] = ro_id
        if q:
            params["q"] = q
        if include_received:
            params["include_received"] = "true"
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{self.base}/parts",
                headers=self._headers(),
                params=params,
            )
            r.raise_for_status()
            return r.json()

    def parts_usage(
        self, *, year: int | None = None, month: int | None = None, limit: int = 100
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if year is not None:
            params["year"] = year
        if month is not None:
            params["month"] = month
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{self.base}/parts/usage",
                headers=self._headers(),
                params=params,
            )
            r.raise_for_status()
            return r.json()

    def parts_suggest(self, q: str = "", limit: int = 25) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if q:
            params["q"] = q
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{self.base}/parts/suggest",
                headers=self._headers(),
                params=params,
            )
            r.raise_for_status()
            return r.json()

    def list_events(
        self,
        *,
        since: str = "",
        since_id: int = 0,
        ro_id: str = "",
        limit: int = 100,
        exclude_actor: str = "",
        exclude_actor_id: str = "",
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if since:
            params["since"] = since
        if since_id:
            params["since_id"] = since_id
        if ro_id:
            params["ro_id"] = ro_id
        if exclude_actor:
            params["exclude_actor"] = exclude_actor
        if exclude_actor_id:
            params["exclude_actor_id"] = exclude_actor_id
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{self.base}/events",
                headers=self._headers(),
                params=params,
            )
            r.raise_for_status()
            return r.json()

    def list_messages(
        self,
        *,
        for_id: str,
        unread: bool = False,
        limit: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"for_id": for_id, "limit": limit}
        if unread:
            params["unread"] = 1
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{self.base}/messages",
                headers=self._headers(),
                params=params,
            )
            r.raise_for_status()
            return r.json()

    def list_sent_messages(
        self,
        *,
        from_id: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{self.base}/messages/sent",
                headers=self._headers(),
                params={"from_id": from_id, "limit": limit},
            )
            r.raise_for_status()
            return r.json()

    def send_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{self.base}/messages",
                headers=self._headers(),
                json=payload,
            )
            r.raise_for_status()
            return r.json()

    def mark_message_read(self, message_id: int, *, for_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                f"{self.base}/messages/{int(message_id)}/read",
                headers=self._headers(),
                json={"for_id": for_id},
            )
            r.raise_for_status()
            return r.json()

    def mark_messages_delivered(
        self, message_ids: list[int], *, for_id: str
    ) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                f"{self.base}/messages/delivered",
                headers=self._headers(),
                json={"for_id": for_id, "ids": [int(x) for x in message_ids]},
            )
            r.raise_for_status()
            return r.json()

    def renotify_message(self, message_id: int, *, from_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                f"{self.base}/messages/{int(message_id)}/renotify",
                headers=self._headers(),
                json={"from_id": from_id},
            )
            if r.status_code >= 400:
                detail = ""
                try:
                    detail = str(r.json().get("detail") or "")
                except Exception:
                    detail = (r.text or "")[:240]
                raise RuntimeError(detail or f"HTTP {r.status_code}")
            return r.json()

    def _shift_error(self, r: httpx.Response) -> None:
        if r.status_code < 400:
            return
        detail = ""
        try:
            detail = str(r.json().get("detail") or "")
        except Exception:
            detail = (r.text or "")[:240]
        raise RuntimeError(detail or f"HTTP {r.status_code}")

    def list_active_shifts(self) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(f"{self.base}/shifts/active", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def get_open_shift(self, tech_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(
                f"{self.base}/shifts/mine",
                headers=self._headers(),
                params={"tech_id": tech_id},
            )
            r.raise_for_status()
            return r.json()

    def list_shifts(
        self,
        *,
        tech_id: str = "",
        day_from: str = "",
        day_to: str = "",
        limit: int = 500,
    ) -> dict[str, Any]:
        params = {"limit": limit}
        if tech_id:
            params["tech_id"] = tech_id
        if day_from:
            params["day_from"] = day_from
        if day_to:
            params["day_to"] = day_to
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{self.base}/shifts",
                headers=self._headers(),
                params=params,
            )
            r.raise_for_status()
            return r.json()

    def start_shift(
        self,
        *,
        tech_id: str,
        tech_name: str = "",
        started_at: str = "",
        day: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"tech_id": tech_id, "tech_name": tech_name}
        if started_at:
            body["started_at"] = started_at
        if day:
            body["day"] = day
        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                f"{self.base}/shifts/start",
                headers=self._headers(),
                json=body,
            )
            self._shift_error(r)
            return r.json()

    def end_shift(
        self,
        *,
        tech_id: str = "",
        shift_id: int | None = None,
        ended_at: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if tech_id:
            body["tech_id"] = tech_id
        if shift_id is not None:
            body["shift_id"] = shift_id
        if ended_at:
            body["ended_at"] = ended_at
        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                f"{self.base}/shifts/end",
                headers=self._headers(),
                json=body,
            )
            self._shift_error(r)
            return r.json()

    def update_shift(
        self,
        shift_id: int,
        *,
        started_at: str | None = None,
        ended_at: str | None = None,
        clear_end: bool = False,
        day: str | None = None,
        edited_by: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"edited_by": edited_by, "clear_end": clear_end}
        if started_at is not None:
            body["started_at"] = started_at
        if ended_at is not None:
            body["ended_at"] = ended_at
        if day is not None:
            body["day"] = day
        with httpx.Client(timeout=15.0) as client:
            r = client.patch(
                f"{self.base}/shifts/{int(shift_id)}",
                headers=self._headers(),
                json=body,
            )
            self._shift_error(r)
            return r.json()

    def delete_shift(self, shift_id: int) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            r = client.delete(
                f"{self.base}/shifts/{int(shift_id)}",
                headers=self._headers(),
            )
            self._shift_error(r)
            return r.json()

    def get_weekly_report_snapshot(self, week_start: str) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(
                f"{self.base}/reports/weekly",
                headers=self._headers(),
                params={"week_start": week_start},
            )
            r.raise_for_status()
            return r.json()

    def list_weekly_report_archive(self, *, limit: int = 52) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(
                f"{self.base}/reports/weekly/list",
                headers=self._headers(),
                params={"limit": limit},
            )
            r.raise_for_status()
            return r.json()

    def save_weekly_report(
        self,
        week_start: str,
        *,
        week_end: str,
        payload: dict[str, Any],
        created_by: str = "",
        created_by_id: str = "",
    ) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            r = client.put(
                f"{self.base}/reports/weekly/{week_start}",
                headers=self._headers(),
                json={
                    "week_end": week_end,
                    "payload": payload,
                    "created_by": created_by,
                    "created_by_id": created_by_id,
                },
            )
            r.raise_for_status()
            return r.json()
