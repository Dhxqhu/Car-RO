# Car-RO on Windows (bay PC client)

Car-RO’s main UI is a **terminal app** (same menus and forms as Linux).  
**ARM Windows** (Snapdragon / Windows on Arm) works if you install **Python for ARM64**.

A full mouse GUI and a Windows `.exe` server are **not** required for day-one use.  
The **server stays on Linux**; this PC is only a client.

---

## What you need

1. Windows 10/11 (x64 or ARM64)  
2. [Python 3.10+](https://www.python.org/downloads/) — during setup, check **“Add python.exe to PATH”**  
3. [Windows Terminal](https://aka.ms/terminal) (recommended)  
4. Car-RO zip from [Releases](https://github.com/Dhxqhu/Car-RO/releases/latest) — use the **latest** release (not an old tag)

---

## Install (easiest: double-click the `.bat`)

Use **`Install-Car-RO.bat`**, not `scripts\install.ps1`.  
Double-clicking a `.ps1` often opens “How do you want to open this file?” and **PowerShell is not in the list** — that is normal on Windows. Do not hunt for PowerShell in that menu.

1. Download **Source code (zip)** from the latest Release and unzip (example: `Documents\Car-RO-0.1.2` — rename if you like).  
2. Open that unzipped folder in File Explorer.  
3. Double-click **`Install-Car-RO.bat`** at the **top** of the folder (next to `README.md`).  
4. If Windows SmartScreen warns, choose **More info → Run anyway** (this is your own zip from GitHub).  
5. When it finishes, **close that window**, open **Windows Terminal**, and run:

```powershell
carro
```

### Fallback: install from PowerShell (copy the folder path)

Use this if the `.bat` is blocked, or if you prefer the terminal (same steps that work when `.ps1` is not “Open with” friendly):

1. Unzip the Release zip.  
2. In File Explorer, open the unzipped Car-RO folder (the one that contains `Install-Car-RO.bat` and a `scripts` folder).  
3. Click the address bar at the top → **Ctrl+C** to copy the full path.  
4. Open **Windows Terminal** or **PowerShell** (Start menu → type `powershell` → Enter).  
5. Paste:

```powershell
cd "PASTE_THE_PATH_HERE"
```

(Example: `cd "C:\Users\You\Downloads\Car-RO-0.1.2"`)

6. Allow scripts for this window only, then run the installer:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1
```

Or run the bat from that same folder:

```powershell
.\Install-Car-RO.bat
```

7. Close and reopen the terminal, then:

```powershell
carro
```

### If `carro` is not found after install

Close and reopen Windows Terminal (PATH updates), then try `carro` again. Still missing:

```powershell
.\carro.bat
```

(from inside the unzipped folder), or:

```powershell
& "$env:LOCALAPPDATA\Car-RO\bin\carro.bat"
```

---

## Join the shop server

After the Linux server is set up ([SERVER_SETUP.md](SERVER_SETUP.md) — start there if this is your first time):

```powershell
carro config set server_url http://YOUR_SERVER:8787
carro config set token PASTE_TOKEN_HERE
carro sync
```

Or: `carro` → **`c` Config** → Server URL + API token.

Use the **same** URL and **same shop token** as every other bay PC.  
Get the token from the server install handoff block, or on the server run:

```bash
grep CARRO_TOKEN ~/.config/carro-server.env
```

Do **not** invent a new token on this PC during normal setup. “Generate new token” only changes this laptop; the server will reject it until you also update `CARRO_TOKEN` on the server and every other bay (see **Rotate the shop token** in [SERVER_SETUP.md](SERVER_SETUP.md)).

---

## Day-to-day

| Goal | Command / menu |
| --- | --- |
| Open Car-RO | `carro` |
| Sync | menu **`s`** or `carro sync` |
| Delete mistake RO | menu **`d`** |
| Switch tech | menu **`t`** |

Textual forms need a real terminal (Windows Terminal). The old `cmd.exe` window may look broken.

---

## ARM notes

- Install the **ARM64** Python build on ARM devices (not the x64 emulation build, unless you know you need it).  
- If pip wheels fail for a dependency, say so in an issue with the error text — most of Car-RO’s deps are pure Python / widely wheeled.  

---

## Scanner / OBD adapters (USB + Bluetooth)

Serial paths differ by OS; Car-RO and [obdscan](https://github.com/Dhxqhu/obdscan) share `platform_ports.py`:

| | Linux | Windows |
| --- | --- | --- |
| USB ELM | `/dev/ttyUSB*` or `/dev/ttyACM*` | `COMx` (Device Manager → Ports) |
| Bluetooth ELM | `/dev/rfcomm*` after `rfcomm` bind | Pair in **Settings → Bluetooth**, then use the **Standard Serial over Bluetooth link (COMx)** |
| DoIP / ENET | Normal ethernet / IP | Same — not a COM/rfcomm path |

Override anytime with `OBD_PORT` (e.g. `COM5` or `/dev/ttyUSB0`). In the Scanner GUI, **Adapters → Auto-setup** picks the right style for the host OS.

---

## Later ideas (not required yet)

- One-click `carro.exe` via PyInstaller (Release asset)  
- A separate Windows GUI shell  

Those can wait until the terminal client feels solid on your machines.

---

## Roadmap notes (next sessions)

### Advisor app + shared Windows installer

When packaging for Windows, plan **one installer** that covers both products:

- Installer choice: **Technician** (default) vs **Advisor**
- Tech app = current Car-RO bay client (this repo)
- Advisor app = separate application (not started yet) that assigns work / watches the shop; talks to the same `carro-server`

Today’s **`Install-Car-RO.bat`** is the Technician path only. Keep that as the default when a combined installer lands.

### Quick audit before a Windows GUI build smoke-test

These are the likely hiccups — fix or expect them before relying on an MSI/NSIS build:

| Area | Status | Note |
| --- | --- | --- |
| CLI install | Ready | Double-click `Install-Car-RO.bat` → `scripts/install.ps1` |
| Serial / BT adapters | Ready | COM ports via shared `platform_ports` (see above) |
| PDF open | Ready | Uses `os.startfile` on Windows |
| Tauri targets | Configured | `msi` + `nsis` in `gui/src-tauri/tauri.conf.json`; WebView2 bootstrapper download |
| Engine beside GUI | Dev ready | `Run-Tech-GUI.bat` / `scripts\run-gui-dev.ps1`, `Run-Advisor-GUI.bat` / `scripts\run-advisor-ui.ps1`, `Run-Tech-GUI-Tauri.bat` / `scripts\run-gui-tauri.ps1` start engine + UI. Both apps **join one healthy engine** (default `:8788`, falls back in-band, warns on ephemeral). Packaged `.exe` still needs a sidecar / `CARRO_ENGINE_CMD` for offline double-click. |
| Engine spawn paths | Ready | Tauri shells try `CARRO_ENGINE_CMD`, then `.venv` python, then `python`/`py` (Windows) or `python3` (Linux); `PYTHONPATH` uses `;` on Windows and `:` elsewhere. |
| Config / data dirs | Works, atypical | Still `~/.config/carro` and `~/.local/share/carro` (fine under the user profile, but not `%APPDATA%`). Photos use `Documents\Car-RO\…`. |
| Shop server | Redeploy | Tech notifications + Assigned board need a server that has `/events` and `/assigned`. Older servers soft-fail events (no crash) but won’t show live team updates. |

### Advisor handoff (status + events)

Tech app emits shop-server events the future advisor app will consume:

| Tech action | RO status | Event type |
| --- | --- | --- |
| Request parts (advisor) | `waiting_parts` | `ro_parts_requested` |
| Push for customer approval | `waiting_customer` | `ro_approval_requested` |
| Mark done | `done` | `ro_ready_to_bill` |
| Mark billed out | `billed_out` | `ro_billed_out` |

Advisor desk (separate app on `:1422`): parts / approvals / bill-out from the desk pool, **Efficiency**, **Time cards**, **Reports**, punches (**Set time** when clocking a tech in), Admin (staff PINs + shop admin PIN). Tech app: **Edit punch** on your own day start/end requires the shop admin PIN. Same-PC dual login is supported (tech + advisor sessions share one engine).

Day-one Windows GUI testing (after `Install-Car-RO.bat`):

- Tech Vite UI: double-click **`Run-Tech-GUI.bat`** (or `.\scripts\run-gui-dev.ps1`) → http://127.0.0.1:1420
- Advisor desk: double-click **`Run-Advisor-GUI.bat`** (or `.\scripts\run-advisor-ui.ps1`) → http://127.0.0.1:1422
- Tech Tauri: **`Run-Tech-GUI-Tauri.bat`** (needs Rust/WebView2 toolchain)

Join shop server: **`Join-Server.bat`** / `.\scripts\join-server.ps1`.

Techs can take a bay laptop **home** over **Tailscale** (shop tailnet + each tech’s own account). See [SERVER_SETUP.md — Take a bay laptop home](SERVER_SETUP.md#take-a-bay-laptop-home-tailscale).

### Updating this PC later (opt-in)

Working shops do **not** need to update. When you want new features:

1. Update **carro-server on Linux first** (`./scripts/update-server.sh`) — see [UPDATING.md](UPDATING.md).
2. On this Windows PC: double-click **`Update-Car-RO.bat`** (or `.\scripts\update-client.ps1`).
3. Restart **`Run-Tech-GUI.bat`** / **`Run-Advisor-GUI.bat`**.

No auto-update prompts. Config and shop token stay in `%USERPROFILE%\.config\carro\config.toml`.

Packaged `.exe` sidecar install is still a later step; use the launchers above for desk/bay smoke tests.
