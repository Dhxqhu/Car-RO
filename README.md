# Car-RO

**Technician repair-order notes for people who also like running their own gear.**

Car-RO is a terminal app for documenting diagnostic and repair work — the stuff you wish you’d written down *while you were still under the hood*. It is **not** a DMS, not billing, and not meant to replace your shop’s official RO system. It is a personal / bay-side knowledge base that happens to spit out a clean PDF a service advisor can read.

Built for mechanics and techs who:

- Keep a home-lab server (or a spare NAS / mini PC) and are comfortable with Linux, Tailscale, systemd, and open source tools
- Want **searchable history** of past jobs (“what fixed that intermittent wiper on the last Ford?”)
- Want a **typed PDF** for the advisor instead of chicken-scratch on a carbon form
- Want **phone photos** attached to the write-up without fighting AirDrop into a random Downloads folder every time

### Companion tools & hardware

| | Link |
| --- | --- |
| **obdscan** (CLI OBD companion) | [github.com/Dhxqhu/obdscan](https://github.com/Dhxqhu/obdscan) |
| **GODIAG GT327** (ELM327 Bluetooth + DoIP/ENET adapter) | [Amazon](https://www.amazon.com/dp/B0DKXPRLPP) · [Godiag product page](https://www.godiagshop.eu/wholesale/godiag-gt327.html) |

Car-RO can pull VIN / vehicle / DTC context from **obdscan** (and its Saved Codes exports) into a repair order. **obdscan** is written around cheap ELM327-class dongles such as the **GT327**, including the adapter’s DoIP ethernet mode for enhanced OEM packs.

---

## Why it exists

As a tech you already know the loop:

1. Fix something clever.
2. Forget the exact symptom / part / gotcha six months later.
3. Burn time rediscovering it on the next similar car.

Car-RO is the habit-forming middle step: open a job, dump complaint + notes + OBD snapshot + photos, export a PDF, sync to your box at home. Future-you (and your bay) get a trail.

---

## What you get

| Piece | What it does |
| --- | --- |
| **CLI (`carro`)** | Interactive menu + full-screen forms for new / edit / search |
| **Local SQLite** | Fast cache of recent ROs on the laptop |
| **Customer PDF** | Shop header/logo, boxed complaint & tech notes, OBD block, photos + captions |
| **Optional server** | Bulk storage on *your* disk(s), multi-volume aware |
| **Photo ingress** | Modular: local files, inbox drop, Tailscale QR upload from phone |

Local-only works fine. The server is for people who want history that outlives a laptop SSD and who already mesh their devices with something like Tailscale.

### Example PDF output

![Sample Car-RO repair order PDF](docs/examples/sample-repair-order.png)

*Example only.* Shop name and logo are placeholders to show how branding appears on a finished PDF — not a claim about any particular workplace. Customer / VIN / plate values in the sample are fictional demo data.

---

## Quick install (workstation)

Requirements: Linux (or similar), Python **3.10+**, `~/.local/bin` on your `PATH`.

```bash
git clone https://github.com/Dhxqhu/Car-RO.git
cd Car-RO
./scripts/install.sh
```

That will:

1. Create `.venv` and install Python deps  
2. Symlink `carro` into `~/.local/bin`  
3. Copy `config.example.toml` → `~/.config/carro/config.toml` if missing  
4. Create photo / inbox dirs under `~/Documents/Car-RO/`  

Then:

```bash
carro                  # interactive menu
carro config           # edit shop name, server URL, local keep limits, …
```

Set your shop name and optional logo path in the config menu (or edit the toml). **Do not commit** real tokens, hostnames, or shop secrets into git — they stay in `~/.config/carro/`.

### Manual install (same steps as the script)

```bash
cd /path/to/Car-RO
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
mkdir -p ~/.local/bin ~/.config/carro
ln -sfn "$(pwd)/scripts/carro" ~/.local/bin/carro
test -f ~/.config/carro/config.toml || cp config.example.toml ~/.config/carro/config.toml
carro config init   # optional: ensure token placeholder / dirs
```

---

## Daily use

```bash
carro                  # menu
carro new --from-obd   # new RO, try autofill from obdscan / Saved Codes
carro list
carro search ford
carro search --make ford --year 2023 --remote
carro pull-obd RO-…
carro photo add ./pic.jpg --id RO-… --tag intake --note "LH wiper motor"
carro photo phone --id RO-… --tag intake   # Tailscale QR → iPhone
carro pdf RO-…
carro sync             # push to your server + prune local cache
```

### Forms (Textual)

- **Tab / Shift+Tab** — fields  
- **Ctrl+S** — save  
- **Ctrl+Q** / **Esc** — quit without saving  
- **F2** — pull OBD / Saved Codes  
- Search submit: **Ctrl+J** (or Enter in a field)

### Config menu highlights

- **Local RO keep** / **Local photo keep** — how much history stays on *this* machine  
  - Use **`auto`** to size from free disk on the photos volume  
  - Older ROs can stay in metadata while photo files are pruned; server still holds bulk if configured  

---

## Photos (modular on purpose)

Photo intake is a **provider** interface so different shops / devices can plug in without rewriting the RO core.

| Path | Good for |
| --- | --- |
| **Local file / inbox** | Android, camera SD card, anything you can copy to the PC |
| **Tailscale QR upload** | iPhone (or any phone) on your mesh → short-lived `/u/<token>` page, optional notes per upload |
| **Future providers** | See roadmap — AirDrop-adjacent, shared folder, cloud drop, etc. |

**Working iPhone flow today**

1. RO open → menu **6 → phone** (or `carro photo phone --id …`)  
2. Tailscale on the phone  
3. Scan QR → Safari → optional **Notes** → take/choose photos → Upload  
4. Enter on the PC to refresh; files land in `~/Documents/Car-RO/photos/<RO-id>/` (and on the server if configured)

The empty repo `share/` folder is unused. Branding/logo stay local (`branding/`, `~/.config/carro/logo.png`) and are gitignored where appropriate.

---

## Optional home-lab server

Run this on a box with disk you trust. Laptop keeps a hot cache; server keeps the archive.

```bash
# on the server host, from a clone or copied server/ tree
./scripts/install-server.sh
# or follow the printed env vars / systemd unit
```

Typical env:

```bash
export CARRO_DATA_DIR=/path/to/your/drive/carro
# Optional extra volumes later:
# export CARRO_VOLUMES="primary=/path/to/a/carro,extra=/path/to/b/carro"
export CARRO_TOKEN="generate-a-long-random-token"
```

Then point the laptop at it (Tailscale MagicDNS recommended):

```bash
carro config    # set Server URL + token, or:
carro config set server_url http://YOUR_SERVER:8787
carro config set token YOUR_TOKEN
carro sync
```

Systemd user unit template: `server/carro-server.service`.

### Adding another drive later

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"extra","path":"/path/to/new/drive/carro"}' \
  http://YOUR_SERVER:8787/volumes
```

---

## Layout

```
cli/carro/          # CLI package (forms, PDF, OBD hook, photo providers)
server/carro_server # FastAPI archive + phone upload sessions
scripts/carro       # launcher used by ~/.local/bin/carro
scripts/install.sh  # workstation install
scripts/install-server.sh
config.example.toml # copy to ~/.config/carro/config.toml
```

---

## Privacy

This project is aimed at **your** lab and **your** bay notes. Keep real hostnames, LAN IPs, Tailscale names, tokens, customer PII dumps, and shop logos out of git. Operator config lives in `~/.config/carro/config.toml` only.

---

## Roadmap / brainstorm (photos & iPhone)

The Tailscale QR path works and stays as the reliable “any phone on the mesh” option. For a **more refined personal iPhone** workflow we still want to explore (not committed yet):

- **Shared folder / inbox watch** — Files app → Tailscale or SMB drop into `inbox_dir`, then `carro photo ingest`
- **Cloud drop (Dropbox / iCloud Drive / Syncthing)** — phone saves into a watched folder; Car-RO attaches on save
- **Shortcuts / share sheet** — iOS Shortcut posts multipart to the existing upload token URL (same API, less Safari tapping)
- **AirDrop** — limited on Linux; usually ends as “AirDrop to Mac/nearby then copy,” so probably not first-class unless a sidecar exists
- **API token UX** — clearer rotation, per-device upload tokens, expiry visible in the config menu

Photo providers stay modular so those experiments don’t break the local / QR paths other techs need.

---

## License / vibe

Personal tooling, shared because other techs in the same hobbyist/home-lab corner of the trade might want the same thing. Fork it, break it, wire it to your stack.
