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

## Install (easiest: double-click)

1. Download **Source code (zip)** from the latest Release and unzip (example: `Documents\Car-RO-0.1.1` — rename if you like).  
2. Open that unzipped folder in File Explorer.  
3. Double-click **`Install-Car-RO.bat`** at the **top** of the folder (next to `README.md`).  
4. If Windows SmartScreen warns, choose **More info → Run anyway** (this is your own zip from GitHub).  
5. When it finishes, **close that window**, open **Windows Terminal**, and run:

```powershell
carro
```

That `.bat` is the supported path: it finds `scripts\install.ps1` for you and runs it with the right PowerShell flags. You do **not** need to “Open with” PowerShell on the `.ps1`, and you do **not** need to type the script path by hand.

### Optional: run from PowerShell yourself

If you prefer the terminal:

```powershell
cd $env:USERPROFILE\Documents\Car-RO   # or your unzip folder (name may include a version)
.\Install-Car-RO.bat
```

Or call the script directly:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1
```

### If `carro` is not found after install

Close and reopen Windows Terminal (PATH updates), then try `carro` again. Still missing:

```powershell
& "$env:USERPROFILE\Documents\Car-RO\carro.bat"
```

(or the `carro.bat` inside whatever folder you unzipped)

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
| Engine beside GUI | **Gap** | Packaged app only auto-starts the engine if `CARRO_ROOT` / `CARRO_ENGINE_CMD` is set. Dev script is bash-only (`run-gui-tauri.sh`). Need a `.ps1` launcher and/or a real sidecar before “double-click .exe” works offline. |
| Engine spawn paths | **Gap** | `gui/src-tauri/src/lib.rs` tries `python3` and joins `PYTHONPATH` with `:` — on Windows prefer `python` / `.venv\Scripts\python.exe` and `;` path separators. |
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

Advisor workflow (planned): parts order + approval notifications → billing queue (`done`) → enter accounting → **billed out** closes the RO.

Day-one Windows testing can stay on **CLI + `Install-Car-RO.bat`** until the engine sidecar / PowerShell Tauri launcher is wired.
