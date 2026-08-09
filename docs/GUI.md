# Car-RO desktop GUI (Orders + Scanner)

One **Tauri 2** desktop app for Windows and Linux with two workspaces:

| Workspace | Purpose |
| --- | --- |
| **Orders** | Car-RO repair-order notes (login, RO editor, PDF, sync) |
| **Scanner** | obdscan GUI scaffold (connect, codes, live, saved, adapters) |

Same visual system (React + Tailwind, dark/light). One local Python engine serves both.

```
gui/ui                → Vite + React + TypeScript
gui/src-tauri         → Tauri shell (Windows + Linux)
engine/carro_engine   → FastAPI: /session, /ros, /config, …
engine/obd_engine     → FastAPI: /obd/* (scaffold; ElmSession wiring later)
obdscan (sibling)     → CLI + libraries the OBD routes will call
```

Header switcher: **Orders** | **Scanner**. CLI tools (`carro`, `obdscan`) stay first-class; the GUI is the bay-friendly front end, not a replacement.

## Prerequisites

| Tool | Notes |
| --- | --- |
| Node 20+ | UI |
| Rust stable | `rustup` — required to build Tauri |
| Python 3.10+ | Engine (repo `.venv` from `./scripts/install.sh`) |
| obdscan checkout | Optional for scaffold; required later for live bus. Sibling `../obdscan` or `OBDSCAN_ROOT` |
| Linux packages | WebKitGTK for Tauri (distro-specific; see below) |

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

- Technician login (name + PIN)
- RO list / search / create / edit / delete
- PDF export (path returned; opens via OS later)
- Sync to carro-server + tech roster sync
- Settings (shop name, server URL, token)
- Add technician (admin PIN)

Photos: metadata count on RO; attach still via CLI photo tools in this pass.

## Scanner features (framework)

Routes under `/scan/*` + engine under `/obd/*`:

| UI | Engine | Status |
| --- | --- | --- |
| Connect | `GET /obd/health`, `POST /obd/connect` | Scaffold (connect returns 501 until ElmSession is owned by the engine) |
| Codes / Live | `/obd/codes`, `/obd/live` | Stub pages |
| Vehicle | `GET /obd/vehicle` | Reads `~/.cache/obdscan/last_vehicle.json` |
| Saved | `GET /obd/saved` | Lists `Documents/Saved Codes` (shared with Car-RO autofill) |
| Adapters | `GET /obd/adapters` | Reads `~/.config/obdscan/adapters.json` |

Next implementation pass: hold an `ElmSession` (and optional DoIP) inside `obd_engine`, mirror CLI modules, and “Send to RO” from a saved scan.

**Handoff contract** (paths, writers, pull priority): [OBD_HANDOFF.md](OBD_HANDOFF.md).

## Theme

Toggle sun/moon in the header. Preference stored in `localStorage` (`carro-theme`). Respects `prefers-color-scheme` on first launch.
