# Updating a live Car-RO shop (manual, opt-in)

**You do not have to update.** If the shop is working, leave it on that build. Updates are only for when you want newer features or fixes.

There is **no** auto-update and **no** “new version available” nag on bay or advisor PCs.

| Role | OS | How to update |
| --- | --- | --- |
| Shop **server** (`carro-server`) | **Linux only** | `./scripts/update-server.sh` |
| Bay / advisor **client** | Linux | `./scripts/update-client.sh` |
| Bay / advisor **client** | Windows | `Update-Car-RO.bat` or `.\scripts\update-client.ps1` |

---

## Order of operations (when you choose to update)

1. Put the new release on the machine (git pull, or copy/unzip the new tree over the existing checkout).
2. **Update carro-server first** on the Linux home-lab host.
3. Confirm health (see below).
4. Update each **bay** and **advisor** PC when convenient (Linux or Windows; can stagger). Older clients usually keep working if the shop API is compatible.
5. Restart the local engine + GUI on each updated PC.
6. Smoke test: login, sync, open one RO / desk pool.

---

## Server (Linux)

On the machine that runs **carro-server** (after the new code is in your Car-RO checkout):

```bash
./scripts/update-server.sh
```

This:

- Refreshes `~/carro-server` from `server/`
- Builds the phone PWA when Node/npm is available (`./scripts/build-pwa.sh`)
- Installs Python deps
- Restarts the user systemd unit
- **Keeps** `~/.config/carro-server.env` (shop token) and the data dir (`CARRO_DATA_DIR` / volumes)

Check:

```bash
curl -s http://127.0.0.1:8787/health
curl -s http://127.0.0.1:8787/version
```

You should see `app_version` and `api_version` in the JSON.

First-time install is still `./scripts/install-server.sh` (see [SERVER_SETUP.md](SERVER_SETUP.md)).

---

## Bay / advisor PCs

### Linux

```bash
./scripts/update-client.sh
# restart GUI if it was open:
./scripts/run-gui-dev.sh          # tech → :1420
./scripts/run-advisor-ui.sh       # advisor → :1422
```

### Windows

- Double-click **`Update-Car-RO.bat`**, or in PowerShell from the Car-RO folder:

```powershell
.\scripts\update-client.ps1
```

Then restart:

- Tech: **`Run-Tech-GUI.bat`** (or `.\scripts\run-gui-dev.ps1`) → http://127.0.0.1:1420  
- Advisor: **`Run-Advisor-GUI.bat`** (or `.\scripts\run-advisor-ui.ps1`) → http://127.0.0.1:1422  

Config stays at `%USERPROFILE%\.config\carro\config.toml` (same layout as Linux `~/.config/carro/`).

Join shop server (first time or new PC): **`Join-Server.bat`** / `.\scripts\join-server.ps1` (Linux: `./scripts/join-server.sh`).

---

## Compatibility (server too old for this PC)

Each build has:

| Field | Meaning |
| --- | --- |
| `app_version` | Human release (from repo `VERSION`) |
| `api_version` | Shop protocol generation on **carro-server** |
| `required_server_api` | What this client/engine needs |

If you update a **client** before the **server**, and this build needs a newer `api_version` than the server reports, sync shows a **one-time clear error**: update the server or roll that PC back. It will **not** repeatedly nag you to upgrade a working shop.

Older servers that do not yet advertise `api_version` are treated as `0`. This release ships `api_version: 1` on updated servers but keeps client `required_server_api` at `0` so existing shops are not blocked. Bump `REQUIRED_SERVER_API` in code **only** for breaking client↔server changes (and update the server first).

---

## Schema / data safety

Shop DB changes are **additive** (`CREATE TABLE IF NOT EXISTS`, guarded `ALTER TABLE … ADD COLUMN`). Update scripts never wipe the archive or photo volumes.

Destructive migrations (if ever needed) require a major `VERSION` bump and an explicit backup step called out in the release notes.

---

## Version checks

**Linux / macOS-style shell**

```bash
carro --version
curl -s http://SERVER:8787/version
curl -s http://127.0.0.1:8788/version   # local engine, when running
```

**Windows (PowerShell)**

```powershell
carro --version
Invoke-RestMethod http://SERVER:8787/version
Invoke-RestMethod http://127.0.0.1:8788/version
```
