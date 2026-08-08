"""Remote sync client for optional carro-server."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from carro.config import load_config
from carro.core.models import RepairOrder


class RemoteClient:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        cfg = load_config()
        self.base = (base_url if base_url is not None else cfg.get("server_url") or "").rstrip("/")
        self.token = token if token is not None else cfg.get("token") or ""

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

    def upsert_ro(self, order: RepairOrder) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            r = client.put(
                f"{self.base}/ros/{order.id}",
                headers=self._headers(),
                json=order.to_dict(),
            )
            r.raise_for_status()
            return r.json()

    def list_ros(self) -> list[dict[str, Any]]:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(f"{self.base}/ros", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def search_ros(self, query: str = "", **filters: str) -> list[dict[str, Any]]:
        params = {k: v for k, v in {"q": query, **filters}.items() if v}
        with httpx.Client(timeout=30.0) as client:
            r = client.get(f"{self.base}/ros", headers=self._headers(), params=params)
            r.raise_for_status()
            return r.json()

    def get_ro(self, ro_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(f"{self.base}/ros/{ro_id}", headers=self._headers())
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
