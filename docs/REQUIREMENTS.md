# Car-RO requirements

What you need to **install**, **run**, and **update** Car-RO on a bay PC, advisor desk, or shop server.

Current release: see repo root [`VERSION`](../VERSION) and [`CHANGELOG.md`](../CHANGELOG.md).

---

## Operating systems

| Role | Supported OS |
| --- | --- |
| **Bay / advisor client** | Linux, Windows 10/11 (x64 or ARM64) |
| **Shop server** (`carro-server`) | **Linux only** |
| **Phone PWA** | Any modern mobile browser on your shop Wi‑Fi or Tailscale mesh |

Windows is a **client only** — do not run the archive server on Windows.

---

## Python

| Component | Minimum | Notes |
| --- | --- | --- |
| **CLI + local engine** | Python **3.10+** | Installed into repo `.venv` by `./scripts/install.sh` or `Install-Car-RO.bat` |
| **Shop server** | Python **3.10+** | `./scripts/install-server.sh` |

Python packages (workstation / engine):

```text
rich>=13.0
reportlab>=4.0
httpx>=0.27
fastapi>=0.110
uvicorn[standard]>=0.27
python-multipart>=0.0.9
qrcode>=7.4
Pillow>=10.0
textual>=0.80
```

Shop server adds (`server/requirements.txt`):

```text
fastapi>=0.110
uvicorn[standard]>=0.27
python-multipart>=0.0.9
pywebpush>=2.0
cryptography>=42.0
```

---

## Node.js (desktop GUIs + phone PWA build)

| Use | Minimum |
| --- | --- |
| **Tech GUI** (`gui/ui`, port 1420) | Node.js **20+** (LTS) |
| **Advisor GUI** (`advisor/ui`, port 1422) | Node.js **20+** (LTS) |
| **Server PWA build** (optional on Linux server) | Node.js **20+** when running `./scripts/build-pwa.sh` |

UI dependencies live in `gui/ui/package.json` and `advisor/ui/package.json`. Launchers run `npm install` on first start.

---

## Rust + system packages (optional Tauri window)

Only needed to **build** the native `.exe` / `.deb` / AppImage — **not** required to run the GUI in a browser.

| Platform | Extra |
| --- | --- |
| **Linux** | WebKitGTK 4.1 dev packages, build tools — see [GUI.md](GUI.md) |
| **Windows** | WebView2 (usually preinstalled), Visual Studio C++ Build Tools for Tauri |

---

## OBD / Scanner (optional)

| Tool | Purpose |
| --- | --- |
| **[obdscan](https://github.com/Dhxqhu/obdscan)** | CLI + libraries for ELM327 / GODIAG GT327 scan path |
| **doipclient**, **udsoncan**, **pyserial** | DoIP / ENET mode on GT327 (optional extras) |

Car-RO Scanner workspace calls the local **obd_engine** on the same machine as the Car-RO engine (`:8788`).

---

## Network & ports (typical shop)

| Service | Default port | Who connects |
| --- | --- | --- |
| **carro-server** | `8787` | All bay PCs, phone PWA, upload sessions |
| **Local engine** | `8788` | Tech + Advisor GUIs on that PC only |
| **Tech Vite dev** | `1420` | Browser / Tauri tech app |
| **Advisor Vite dev** | `1422` | Browser / Tauri advisor app |

Tailscale (or LAN DNS) is recommended when bays and server are not on the same subnet.

---

## Disk & config (operator data — never commit)

| Path | Contents |
| --- | --- |
| `~/.config/carro/` (Windows: `%USERPROFILE%\.config\carro\`) | `config.toml`, tech/advisor rosters, part supersession catalog, shop logo copy |
| `~/.local/share/carro/` | Local SQLite RO cache |
| `~/Documents/Car-RO/` (configurable) | Photos, inbox, branding folder |
| Server `CARRO_DATA_DIR` | Shop archive DB + photo volumes |

---

## Browser support (GUIs)

Use a current **Chrome**, **Edge**, or **Firefox**. The apps target evergreen browsers with ES modules and modern CSS (Tailwind v4).

---

## Compatibility fields

When checking versions after an update:

| Field | Where | Meaning |
| --- | --- | --- |
| `app_version` | `VERSION`, `/health`, `/version` | Human release number |
| `api_version` | Shop server `/version` | Shop API generation |
| `required_server_api` | Client/engine | Minimum server API this build needs |

See [UPDATING.md](UPDATING.md) for safe server-first upgrade order.

---

## What is *not* required

- GitHub account (only for downloading releases or cloning)
- A DMS or billing system
- Windows Server
- Cloud hosting (server is self-hosted on your Linux box)
