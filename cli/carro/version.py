"""Release identity for Car-RO (app + shop API compatibility).

APP_VERSION comes from the repo-root VERSION file when present.
API_VERSION is the shop-server protocol generation — bump only for
breaking client↔server changes. REQUIRED_SERVER_API is what this
client/engine build needs from carro-server.
"""

from __future__ import annotations

from pathlib import Path

# Shop API protocol generation (integer). Bump only on breaking changes.
API_VERSION = 1

# This client/engine requires the shop server to advertise at least this api_version.
# Stay at 0 until a breaking change ships — then bump in lockstep with server API_VERSION.
REQUIRED_SERVER_API = 0


def _candidate_version_files() -> list[Path]:
    here = Path(__file__).resolve()
    out: list[Path] = []
    # cli/carro/version.py → repo root
    out.append(here.parents[2] / "VERSION")
    # Installed server tree: ~/carro-server/VERSION (cwd or package parent)
    out.append(here.parents[1] / "VERSION")  # cli/VERSION unlikely
    out.append(Path.cwd() / "VERSION")
    # Explicit env override for packaged layouts
    import os

    env = (os.environ.get("CARRO_VERSION_FILE") or "").strip()
    if env:
        out.insert(0, Path(env))
    return out


def read_app_version() -> str:
    for path in _candidate_version_files():
        try:
            if path.is_file():
                # utf-8-sig strips a Windows Notepad BOM if present
                text = path.read_text(encoding="utf-8-sig").strip().splitlines()[0].strip()
                if text:
                    return text
        except OSError:
            continue
    return "0.2.0"


APP_VERSION = read_app_version()


def version_payload() -> dict[str, str | int | bool]:
    return {
        "app_version": APP_VERSION,
        "api_version": API_VERSION,
        "required_server_api": REQUIRED_SERVER_API,
    }
