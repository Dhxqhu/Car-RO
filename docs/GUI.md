# Car-RO desktop GUIs

Two **Tauri 2** / Vite apps for Windows and Linux:

| App | Purpose |
| --- | --- |
| **Tech** (`gui/ui`, `:1420`) | Orders + Scanner workspaces (tech PIN, RO editor, PDF, sync, OBD) |
| **Advisor desk** (`advisor/ui`, `:1422`) | Desk pool, parts, messages, Efficiency, Reports, People, Admin |

## Tech app (Orders + Scanner)

| Workspace | Purpose |
| --- | --- |
| **Orders** | Car-RO repair-order notes (tech PIN, RO editor, PDF, sync) |
| **Scanner** | obdscan GUI (connect, codes, live, saved, adapters) — **no PIN required** |

Same visual system (React + Tailwind, dark/light). One local Python engine serves both apps.

```
gui/ui                → Vite + React + TypeScript
gui/src-tauri         → Tauri shell (Windows + Linux)
engine/carro_engine   → FastAPI: /session, /ros, /config, …
engine/obd_engine     → FastAPI: /obd/* + ElmSession + session.lock
obdscan (sibling)     → CLI + libraries the OBD routes call
```

### Login choices

1. **Technician + PIN** → full app (Orders \| Scanner switcher)  
2. **Open Scanner** → Scanner only, no tech session (Exit returns to login)  
3. **Scanner-only launch** → skip login entirely:

```bash
./scripts/run-gui-dev.sh --scanner
# or open http://127.0.0.1:1420/?mode=scanner
# or VITE_CARRO_MODE=scanner / CARRO_MODE=scanner
```

CLI tools (`carro`, `obdscan`) stay first-class. A future small Python-only Scanner GUI is planned separately; it will share the same adapter lock and Saved Codes paths (see [OBD_HANDOFF.md](OBD_HANDOFF.md)).

## Prerequisites

| Tool | Notes |
| --- | --- |
| Node 20+ | **Required** for both GUIs (Vite). Install LTS from [nodejs.org](https://nodejs.org). On Windows, use a new terminal after install, or `Run-Tech-GUI.bat` / `Run-Advisor-GUI.bat` (they add Node to PATH if Explorer still has the old one). |
| Rust stable | `rustup` — required to **build** Tauri, not to run the browser UI |
| Python 3.10+ | Engine (repo `.venv` from `./scripts/install.sh` or `Install-Car-RO.bat`) |
| obdscan checkout | Required for live Connect. Sibling `../obdscan` or `OBDSCAN_ROOT` |
| Linux packages | WebKitGTK for Tauri (distro-specific; see below) |

Library versions live in:

- `requirements.txt` — Python engine / CLI
- `gui/ui/package.json` — Tech UI
- `advisor/ui/package.json` — Advisor desk UI
- `gui/package.json` — Tauri wrapper

Windows workstation list: [WINDOWS.md — Dependencies](WINDOWS.md#dependencies).

### Linux system packages (Debian/Ubuntu example)

```bash
sudo apt install -y libwebkit2gtk-4.1-dev build-essential curl wget file \
  libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

Fedora / Arch: see [Tauri Linux prerequisites](https://v2.tauri.app/start/prerequisites/).

### Windows

- [WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) (usually already present on Win10/11)
- Visual Studio Build Tools (C++) for Tauri
- **ARM64**: install ARM64 Rust target + ARM64 Python for the engine sidecar

```powershell
rustup target add aarch64-pc-windows-msvc   # on ARM machines
```

## Dev (browser + engine)

Easiest while iterating on UI:

```bash
# from repo root, after ./scripts/install.sh
./scripts/run-gui-dev.sh
```

Opens Vite at http://127.0.0.1:1420 and proxies `/api` → engine `:8788`.

**Advisor desk:**

```bash
./scripts/run-advisor-ui.sh
# Windows: Run-Advisor-GUI.bat / .\scripts\run-advisor-ui.ps1
```

Opens http://127.0.0.1:1422 (same engine on `:8788`).

Or separately:

```bash
export PYTHONPATH="$PWD/cli:$PWD/server:$PWD/engine"
# optional: export OBDSCAN_ROOT="$HOME/Documents/obdscan"
.venv/bin/python -m uvicorn carro_engine.main:app --host 127.0.0.1 --port 8788
cd gui/ui && npm install && npm run dev
```

Log in with an existing technician PIN (set up once via `carro` CLI if needed). Use the header to open **Scanner**.

## Dev (Tauri window)

```bash
export CARRO_ROOT=/path/to/Car-RO
export PYTHONPATH="$CARRO_ROOT/cli:$CARRO_ROOT/server:$CARRO_ROOT/engine"
# optional: export OBDSCAN_ROOT=/path/to/obdscan
cd gui
npm install
npm run tauri:dev
```

With `CARRO_ROOT` set, the shell tries to start the Python engine automatically.

## Production builds

```bash
cd gui
npm install
npm --prefix ui run build

# Linux packages (deb + AppImage)
npm run tauri:build:linux

# On a Windows machine (x64 or ARM64):
npm run tauri:build:windows
```

Artifacts land under `gui/src-tauri/target/release/bundle/`.

Still run or bundle the **engine** beside the app (same Python env / future sidecar). For now, ship the engine via:

```bash
CARRO_ROOT=... PYTHONPATH=... uvicorn carro_engine.main:app --host 127.0.0.1 --port 8788
```

and launch the Tauri binary — or use `scripts/run-gui-dev.sh` for day-to-day.

## Orders features (wired)

### Tech (`gui/ui`)

- Technician login (name + PIN)
- RO list / search / create / edit / delete
- RO editor with **auto-save** (customer/vehicle, bay notes, open work-item draft)
- Work items, timers, parts, found issues, merge, PDF export
- **Intake notes** read-only when advisor left arrival reference
- Part lookup with **supersession** badges
- Sync to carro-server + tech roster sync
- Settings (shop name, logo, server URL, token)
- Add technician (admin PIN)

### Advisor desk (`advisor/ui`)

- Advisor login + desk pool, assigned work, calendar / appointments
- RO editor with **auto-save** and **intake notes** (editable until first work item)
- Work items (SI/IM concern auto-fill), parts, found-issue approve/decline
- **Parts** workspace + **supersessions** catalog
- Messages, efficiency, weekly reports, time cards, people / admin
- Waiter / urgent flags, daily / next-day / long-term queues
- PDF export with synced shop branding

Photos: attach via RO editor, found-issue compose, or CLI photo tools (`carro photo …`).

## Scanner features (CLI parity)

Routes under `/scan/*` + engine under `/obd/*` — same capabilities as the obdscan interactive menu:

| UI | Engine | CLI menu |
| --- | --- | --- |
| Connect | `/obd/health`, `/obd/connect`, `/obd/disconnect` | 1–3 |
| Codes | `/obd/codes`, `/obd/codes/clear`, `/obd/lookup`, `/obd/save` | 4, 5, 13, 17 |
| Live | `/obd/live`, `/obd/pids` | 6–8 |
| Vehicle | `/obd/vehicle`, `/obd/vehicle/live`, `/obd/readiness`, `/obd/freeze` | 10–12 |
| Profiles | `/obd/profiles*` | 9 |
| DoIP | `/obd/doip/*` | 15 |
| Libraries | `/obd/doip/packs` | 16 |
| Raw | `/obd/raw`, `/obd/raw/help` | 14 |
| Saved | `/obd/saved` | (Saved Codes browser) |
| Adapters | `/obd/adapters` (+ default / upsert / USB+BT autosetup) | **c** |

DoIP needs `doipclient` + `udsoncan` (+ `pyserial` for ELM). Flip the GT327 to **ENET / DoIP** for DoIP; ELM Bluetooth uses `session.lock`.

**Handoff + lock contract:** [OBD_HANDOFF.md](OBD_HANDOFF.md).

### Deferred (later)

- Windows `.exe` + engine sidecar packaging  
- Smaller Python-only Scanner GUI  
- Live graph mode / ASCII charts (CLI graph display)

Handoff + lock unit tests: `pytest` (see [OBD_HANDOFF.md](OBD_HANDOFF.md)).

## Theme

Toggle sun/moon in the header. Preference stored in `localStorage` (`carro-theme`). Respects `prefers-color-scheme` on first launch.
