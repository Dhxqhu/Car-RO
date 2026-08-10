"""Release identity for carro-server (mirrors cli/carro/version.py)."""

from __future__ import annotations

import os
from pathlib import Path

API_VERSION = 1


def _candidate_version_files() -> list[Path]:
    here = Path(__file__).resolve()
    out: list[Path] = []
    env = (os.environ.get("CARRO_VERSION_FILE") or "").strip()
    if env:
        out.append(Path(env))
    # ~/carro-server/VERSION (package is carro_server/ under install dir)
    out.append(here.parents[1] / "VERSION")
    # Monorepo: server/../VERSION
    out.append(here.parents[2] / "VERSION")
    out.append(Path.cwd() / "VERSION")
    return out


def read_app_version() -> str:
    for path in _candidate_version_files():
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8-sig").strip().splitlines()[0].strip()
                if text:
                    return text
        except OSError:
            continue
    return "0.2.0"


APP_VERSION = read_app_version()


def version_payload() -> dict[str, str | int]:
    return {
        "app_version": APP_VERSION,
        "api_version": API_VERSION,
    }
