"""Open a PDF in the system viewer (CLI + engine GUI)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def open_pdf_viewer(path: Path | str) -> str | None:
    """
    Open path with a local PDF viewer.
    Returns the viewer name used, or None if nothing worked.
    """
    path = Path(path)
    if not path.is_file():
        return None

    if sys.platform.startswith("win"):
        try:
            os_start = getattr(__import__("os"), "startfile", None)
            if callable(os_start):
                os_start(str(path))  # type: ignore[misc]
                return "startfile"
        except OSError:
            pass
        for name in ("cmd",):
            # os.startfile is the normal Windows path; fall through
            break

    if sys.platform == "darwin":
        exe = shutil.which("open")
        if exe:
            try:
                subprocess.Popen(
                    [exe, str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return "open"
            except OSError:
                pass

    viewers = ("zathura", "papers", "xdg-open", "gio")
    for name in viewers:
        exe = shutil.which(name)
        if not exe:
            continue
        cmd = [exe, str(path)] if name != "gio" else [exe, "open", str(path)]
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return name
        except OSError:
            continue
    return None
