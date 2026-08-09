"""Non-interactive USB / Bluetooth adapter auto-setup for the Scanner GUI.

Linux: /dev/ttyUSB* / ttyACM* and rfcomm + bluetoothctl.
Windows: COMx via pyserial; Bluetooth SPP after pairing in Settings.
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any

from obd_engine.session import ensure_obdscan_path, obdscan_root


def _adapters_mod() -> Any:
    ensure_obdscan_path()
    import adapters  # type: ignore

    return adapters


def _platform() -> Any:
    ensure_obdscan_path()
    import platform_ports  # type: ignore

    return platform_ports


def discover() -> dict[str, Any]:
    """List USB serial candidates and Bluetooth devices / COM ports."""
    mod = _adapters_mod()
    plat = _platform()
    usb = plat.list_usb_candidates() or [
        c for c in mod.list_serial_candidates() if c.get("kind") != "bluetooth"
    ]
    bluetooth: list[dict[str, str]]
    if plat.is_windows():
        bluetooth = [
            {
                "addr": "",
                "name": c.get("detail") or "Bluetooth COM",
                "paired": "yes",
                "port": c["path"],
            }
            for c in plat.list_bluetooth_serial_candidates()
        ]
    else:
        bluetooth = list_bluetooth_devices(scan_seconds=6.0)
    return {
        "usb": usb,
        "bluetooth": bluetooth,
        "platform": "windows" if plat.is_windows() else ("linux" if plat.is_linux() else "other"),
        "note": (
            f"{plat.usb_setup_hint()} {plat.bluetooth_setup_hint()} "
            "DoIP uses ethernet separately."
        ),
    }


def list_bluetooth_devices(*, scan_seconds: float = 6.0) -> list[dict[str, str]]:
    """Return [{addr, name, paired}] from bluetoothctl (Linux)."""
    plat = _platform()
    if plat.is_windows():
        return [
            {
                "addr": "",
                "name": c.get("detail") or "Bluetooth COM",
                "paired": "yes",
                "port": c["path"],
            }
            for c in plat.list_bluetooth_serial_candidates()
        ]

    devices: dict[str, dict[str, str]] = {}

    def _ingest(text: str, *, paired: str = "") -> None:
        for line in text.splitlines():
            m = re.match(
                r"Device\s+([0-9A-Fa-f:]{17})\s+(.*)$",
                line.strip(),
            )
            if not m:
                continue
            addr, name = m.group(1).upper(), (m.group(2) or "").strip()
            prev = devices.get(addr, {})
            devices[addr] = {
                "addr": addr,
                "name": name or prev.get("name") or "unknown",
                "paired": paired or prev.get("paired") or "no",
            }

    try:
        paired = subprocess.run(
            ["bluetoothctl", "devices", "Paired"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        _ingest(paired.stdout or "", paired="yes")
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        subprocess.run(
            ["bluetoothctl", "power", "on"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        subprocess.run(
            ["bluetoothctl", "--timeout", str(max(1, int(scan_seconds))), "scan", "on"],
            capture_output=True,
            text=True,
            timeout=scan_seconds + 5,
            check=False,
        )
        listed = subprocess.run(
            ["bluetoothctl", "devices"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        _ingest(listed.stdout or "")
    except (OSError, subprocess.TimeoutExpired):
        pass

    rows = list(devices.values())

    def score(d: dict[str, str]) -> tuple[int, str]:
        blob = f"{d.get('name', '')} {d.get('addr', '')}".upper()
        s = 0
        for token in ("GT327", "GODIAG", "ELM", "OBD", "OBDII", "VGATE", "PLX"):
            if token in blob:
                s += 10
        if d.get("paired") == "yes":
            s += 3
        return (-s, d.get("name", ""))

    rows.sort(key=score)
    return rows


def autosetup_usb(*, port: str | None = None) -> dict[str, Any]:
    """Scan USB serial ports, probe ELM, save first hit as default adapter."""
    mod = _adapters_mod()
    plat = _platform()
    store = mod.load_store()
    if port:
        candidates = [{"path": port, "detail": "manual", "kind": "usb"}]
    else:
        candidates = plat.list_usb_candidates() or [
            c for c in mod.list_serial_candidates() if c.get("kind") != "bluetooth"
        ]
    if not candidates:
        return {
            "ok": False,
            "error": f"No USB serial devices found. {plat.usb_setup_hint()}",
            "tried": [],
        }

    tried: list[dict[str, Any]] = []
    for c in candidates:
        path = c["path"]
        hit = mod.probe_elm(path)
        entry: dict[str, Any] = {"path": path, "detail": c.get("detail", ""), "elm": False}
        if hit:
            baud, banner = hit
            entry.update({"elm": True, "baud": baud, "banner": banner})
            tried.append(entry)
            short = Path(path).name if not plat.is_windows() else path
            aid = mod.upsert_adapter(
                store,
                adapter_id=None,
                label=f"USB ELM ({short})",
                transport="usb_serial",
                port=path,
                baud=baud,
                notes=banner or "",
                make_default=True,
            )
            return {
                "ok": True,
                "adapter_id": aid,
                "port": path,
                "baud": baud,
                "banner": banner,
                "tried": tried,
                "message": f"Saved {aid} → {path} @ {baud} ({banner})",
            }
        tried.append(entry)

    return {
        "ok": False,
        "error": (
            "Found USB ports but none answered ATZ/ATI as an ELM. "
            "Check cable, permissions, and baud."
        ),
        "tried": tried,
    }


def autosetup_bluetooth(
    *,
    bt_addr: str | None = None,
    rfcomm: int = 0,
    scan_seconds: float = 8.0,
) -> dict[str, Any]:
    """
    Discover (or use) a Bluetooth endpoint, prepare the serial path, probe ELM, save.
    Linux: bluetoothctl + rfcomm bind.
    Windows: probe already-paired Bluetooth COM ports.
    """
    mod = _adapters_mod()
    plat = _platform()
    store = mod.load_store()
    root = obdscan_root()
    script_dir = root if root else Path(__file__).resolve().parent

    if plat.is_windows():
        return _autosetup_bluetooth_windows(
            mod=mod,
            plat=plat,
            store=store,
            bt_addr=bt_addr,
            preferred_port=None,
        )

    picked_name = ""
    if bt_addr:
        addr = bt_addr.strip().upper()
    else:
        devices = list_bluetooth_devices(scan_seconds=scan_seconds)
        if not devices:
            return {
                "ok": False,
                "error": (
                    "No Bluetooth devices found. Power the adapter, keep it in BT/ELM mode "
                    "(not ENET), ensure bluetoothctl works, then retry."
                ),
                "devices": [],
            }
        best = devices[0]
        addr = best["addr"]
        picked_name = best.get("name") or ""

    port = f"/dev/rfcomm{int(rfcomm)}"
    adapter = {
        "bt_addr": addr,
        "rfcomm": int(rfcomm),
        "port": port,
        "transport": "bluetooth",
    }
    bind_err = mod.prepare_bluetooth(adapter, script_dir=script_dir)
    time.sleep(0.4)

    baud = 38400
    banner = ""
    elm_ok = False
    if Path(port).exists():
        hit = mod.probe_elm(port, bauds=(38400, 115200, 9600, 57600))
        if hit:
            baud, banner = hit
            elm_ok = True

    label = "GT327 Bluetooth" if "GT327" in picked_name.upper() or not picked_name else f"BT {picked_name}"
    if len(label) > 40:
        label = label[:40]
    aid = mod.upsert_adapter(
        store,
        adapter_id=None,
        label=label,
        transport="bluetooth",
        port=port,
        baud=baud,
        bt_addr=addr,
        rfcomm=int(rfcomm),
        notes=banner
        or ("Flip GT327 to BT; DoIP is ENET" if not elm_ok else banner),
        make_default=True,
    )

    ok = elm_ok or Path(port).exists()
    return {
        "ok": ok,
        "adapter_id": aid,
        "bt_addr": addr,
        "name": picked_name,
        "port": port,
        "baud": baud,
        "banner": banner,
        "elm_ok": elm_ok,
        "bind_error": bind_err,
        "message": (
            f"Saved {aid} → {port} ({addr})"
            + (f" · {banner} @ {baud}" if elm_ok else " · bound; ELM hello not seen yet — try Connect")
        ),
        "warning": bind_err,
    }


def _autosetup_bluetooth_windows(
    *,
    mod: Any,
    plat: Any,
    store: dict[str, Any],
    bt_addr: str | None,
    preferred_port: str | None,
) -> dict[str, Any]:
    candidates = plat.list_bluetooth_serial_candidates()
    if preferred_port:
        candidates = [{"path": preferred_port, "detail": "manual", "kind": "bluetooth"}] + [
            c for c in candidates if c["path"].lower() != preferred_port.lower()
        ]
    if not candidates:
        # Fall back to any COM — user may have paired but description lacks "Bluetooth"
        candidates = [
            c for c in mod.list_serial_candidates() if c["path"].upper().startswith("COM")
        ]
    if not candidates:
        return {
            "ok": False,
            "error": plat.bluetooth_setup_hint(),
            "devices": [],
        }

    tried: list[dict[str, Any]] = []
    for c in candidates:
        path = c["path"]
        adapter = {
            "bt_addr": (bt_addr or "").strip().upper(),
            "rfcomm": 0,
            "port": path,
            "transport": "bluetooth",
        }
        bind_err = mod.prepare_bluetooth(adapter)
        hit = mod.probe_elm(path, bauds=(38400, 115200, 9600, 57600))
        entry: dict[str, Any] = {
            "path": path,
            "detail": c.get("detail", ""),
            "elm": bool(hit),
            "bind_error": bind_err,
        }
        if hit:
            baud, banner = hit
            entry.update({"baud": baud, "banner": banner})
            tried.append(entry)
            aid = mod.upsert_adapter(
                store,
                adapter_id=None,
                label=f"BT ELM ({path})",
                transport="bluetooth",
                port=path,
                baud=baud,
                bt_addr=bt_addr or "",
                rfcomm=0,
                notes=banner or "",
                make_default=True,
            )
            return {
                "ok": True,
                "adapter_id": aid,
                "bt_addr": bt_addr or "",
                "name": c.get("detail") or path,
                "port": path,
                "baud": baud,
                "banner": banner,
                "elm_ok": True,
                "bind_error": bind_err,
                "tried": tried,
                "message": f"Saved {aid} → {path} @ {baud} ({banner})",
                "warning": bind_err,
            }
        tried.append(entry)

    # Save first candidate so Connect can retry even if ATZ failed
    first = candidates[0]["path"]
    aid = mod.upsert_adapter(
        store,
        adapter_id=None,
        label=f"BT ELM ({first})",
        transport="bluetooth",
        port=first,
        baud=38400,
        bt_addr=bt_addr or "",
        rfcomm=0,
        notes="Windows Bluetooth COM — ELM hello not seen yet",
        make_default=True,
    )
    return {
        "ok": True,
        "adapter_id": aid,
        "bt_addr": bt_addr or "",
        "name": "",
        "port": first,
        "baud": 38400,
        "banner": "",
        "elm_ok": False,
        "tried": tried,
        "message": f"Saved {aid} → {first} · ELM hello not seen yet — try Connect",
        "warning": plat.bluetooth_setup_hint(),
    }
