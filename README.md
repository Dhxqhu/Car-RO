# Car-RO

**Technician repair-order notes for people who also like running their own gear.**

Car-RO is a terminal app for documenting diagnostic and repair work — the stuff you wish you’d written down *while you were still under the hood*. It is **not** a DMS, not billing, and not meant to replace your shop’s official RO system. It is a personal / bay-side knowledge base that happens to spit out a clean PDF a service advisor can read.

Built for mechanics and techs who:

- Have a **Linux laptop** (or similar) and are willing to open a terminal — you do **not** need to be a GitHub expert
- Want **searchable history** of past jobs (“what fixed that intermittent wiper on the last Ford?”)
- Want a **typed PDF** for the advisor instead of chicken-scratch on a carbon form
- Want **phone photos** attached to the write-up without fighting AirDrop into a random Downloads folder every time

**Start here:** use a **[Release](https://github.com/Dhxqhu/Car-RO/releases/latest)** (download the zip). That is the supported path for first-time installs. Optional home-lab server / Tailscale comes later — local-only works fine on day one.

### Companion tools & hardware

| | Link |
| --- | --- |
| **obdscan** (CLI OBD companion) | [Releases](https://github.com/Dhxqhu/obdscan/releases/latest) · [repo](https://github.com/Dhxqhu/obdscan) |
| **GODIAG GT327** (ELM327 Bluetooth + DoIP/ENET adapter) | [Amazon](https://www.amazon.com/dp/B0DKXPRLPP) · [Godiag product page](https://www.godiagshop.eu/wholesale/godiag-gt327.html) |

Car-RO can pull VIN / vehicle / DTC context from **obdscan** (and its Saved Codes exports) into a repair order. **obdscan** exists because Linux software for cheap ELM327 / GT327 adapters is scarce — the usual apt GUI (`scantool`) is ancient, and almost nothing uses the GT327’s DoIP ethernet mode. Car-RO is the write-up side of that same bay workflow.

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

### Screenshots

![Car-RO menu with technician login](docs/screenshots/menu.png)

*Main menu after technician PIN login (name on the banner). Demo tech name only.*

![Car-RO technician menu](docs/screenshots/technician.png)

*Menu **`t`**: switch tech, change PIN, manage roster (admin), logout.*

![Car-RO search form](docs/screenshots/search.png)

![Car-RO repair order form](docs/screenshots/ro-form.png)

### Example PDF output

![Sample Car-RO repair order PDF](docs/examples/sample-repair-order.png)

*Example only.* Shop name and logo are placeholders to show how branding appears on a finished PDF — not a claim about any particular workplace. Customer / VIN / plate values in the sample are fictional demo data.

---

## Quick install (workstation)

You need: **Linux** (or **Windows** — see [docs/WINDOWS.md](docs/WINDOWS.md)) and **Python 3.10+**. One install script does the rest.

### Easiest: download a Release (recommended)

1. Open **[the latest Release](https://github.com/Dhxqhu/Car-RO/releases/latest)**  
2. Under **Assets**, download **Source code (zip)**  
3. Unzip it somewhere you keep tools (e.g. `~/Documents/Car-RO`)  
4. In a terminal:

```bash
cd ~/Documents/Car-RO   # or wherever you unzipped (folder name may include a version)
./scripts/install.sh
carro
```

That script will:

1. Create a local Python environment (`.venv`) and install dependencies  
2. Add a `carro` command under `~/.local/bin`  
3. Create `~/.config/carro/config.toml` if missing  
4. Create photo / inbox folders under `~/Documents/Car-RO/`  

If the terminal says `carro: command not found`, add `~/.local/bin` to your PATH — see [Terminal commands](#terminal-commands-carro-and-obdscan) below (copy/paste, one time).

Then:

```bash
carro                  # interactive menu
carro config           # shop name, logo, optional server, …
```

Set your shop name (and optional logo) in the config menu. **Do not** put real tokens, hostnames, or shop secrets into git — they stay in `~/.config/carro/`.

### Add your shop logo (PDF)

The logo shows **top-right** on customer PDFs. You do not need to edit config files by hand.

1. Save your logo as a **PNG** or **JPG** (e.g. into Downloads)  
2. Run either:

```bash
carro logo
# or: carro → c Config → 6 Shop logo
```

3. Pick the file from the list (or choose “I already saved logo.png in Documents/Car-RO/branding/”)  
4. Export a PDF (`carro pdf` or menu **9**) to check it  

Car-RO copies the image to `~/.config/carro/` for you. Change or clear it anytime from the same menu.

### Optional: install with git

If you already use git:

```bash
git clone https://github.com/Dhxqhu/Car-RO.git
cd Car-RO
./scripts/install.sh
```

**Upgrade later:** download the newer Release zip and run `./scripts/install.sh` again (or `git pull` then `./scripts/install.sh` if you cloned).

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

### Terminal commands (`carro` and `obdscan`)

Install puts a launcher in `~/.local/bin`. That only works if that directory is on your `PATH`.

**1. Symlink (Car-RO does this in `./scripts/install.sh`):**

```bash
mkdir -p ~/.local/bin
# from your Car-RO checkout:
ln -sfn "$(pwd)/scripts/carro" ~/.local/bin/carro
```

**2. Same idea for [obdscan](https://github.com/Dhxqhu/obdscan)** (after its venv + deps are set up):

```bash
cd /path/to/obdscan
mkdir -p ~/.local/bin
ln -sfn "$(pwd)/obdscan" ~/.local/bin/obdscan
```

**3. Put `~/.local/bin` on `PATH`** (once per shell config).

bash (`~/.bashrc`):

```bash
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
```

zsh (`~/.zshrc`):

```bash
typeset -U path
path=("$HOME/.local/bin" $path)
```

Then reload (`source ~/.bashrc` / `source ~/.zshrc`) or open a new terminal.

**4. Check:**

```bash
which carro obdscan
carro --help          # or just: carro
obdscan --help
```

If `which` finds nothing, `PATH` is still wrong. If the command runs but Python imports fail, run `./scripts/install.sh` (Car-RO) or `./install.sh` (obdscan) from that project’s folder first.

---

## Daily use

```bash
carro                  # menu
carro new --from-obd   # new RO, try autofill from obdscan / Saved Codes
carro list
carro search ford
carro search --make ford --year 2023 --remote
carro history --vin 1FTEW1EP5PFA00000   # prior jobs for this car (server + local)
carro history --name smith              # fallback when VIN unknown
carro pull-obd RO-…
carro photo add ./pic.jpg --id RO-… --tag intake --note "LH wiper motor"
carro photo shortcut --id RO-… --tag intake  # iOS Share Sheet (setup page + ~7d URL)
carro photo phone --id RO-… --tag intake     # Tailscale QR → Safari
carro pdf RO-…
carro sync             # push to your server + prune local cache
```

### Vehicle history (VIN-first)

Prior work is looked up by **car**, not by person — same vehicle / new owner still finds the trail; multi-car households still work via name fallback.

- Menu **4** — full-screen VIN / name lookup (same style as Search) for stop-ins  
- Menu **5** — history for the **current** RO’s VIN (diag context; excludes the open job)  
- After OBD/VIN autofill — offered when prior ROs exist  
- After the history list: **text** (default diag pack: complaint / notes / OBD), **pdf** (full pack with photos; confirms if about more than 10 pages), **pdf-lite** (same without photos), or **pick** one RO to open / start new from vehicle  
- Packs land in `~/.local/share/carro/history/`

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
| **Tailscale QR upload** | Any phone on your mesh → Safari `/u/<token>` page |
| **iOS Shortcuts** | Share Sheet → POST to the same upload URL (`carro photo shortcut`) |

**Working iPhone flows**

1. RO open → menu **6** → **shortcut** or **phone**  
2. Tailscale on the phone  
3. **Shortcut (recommended for your iPhone):** open the setup page (QR), build *Car-RO Upload* once in Shortcuts, then Photos → Share → that Shortcut  
   **Phone page:** Safari → library or camera → optional notes → Upload  
4. Enter on the PC to refresh; files land in `~/Documents/Car-RO/photos/<RO-id>/` (and on the server if configured)

```bash
carro photo shortcut --id RO-… --tag diag   # ~7-day Share Sheet link + setup page
carro photo phone --id RO-… --tag intake    # short Safari / QR session
```

The empty repo `share/` folder is unused. Branding/logo stay local (`branding/`, `~/.config/carro/logo.png`) and are gitignored where appropriate.

---

## Optional home-lab server

**Full monkey-proof guide (multi-PC):** [docs/SERVER_SETUP.md](docs/SERVER_SETUP.md)  
**Windows bay PCs:** [docs/WINDOWS.md](docs/WINDOWS.md)

Short version — on a Linux box with disk you trust:

```bash
./scripts/install-server.sh
# copy the printed URL + token (“GIVE THIS TO EVERY BAY PC”)
```

On each bay PC:

```bash
./scripts/join-server.sh    # paste URL + token
carro sync
```

Systemd user unit: `server/carro-server.service`. Advanced env: `CARRO_DATA_DIR`, `CARRO_TOKEN`, `CARRO_VOLUMES`.

### Technician login (same shop, multiple PCs)

Bay laptops share one shop Bearer token against **one** carro-server. Technicians pick their **name**, then enter a **4-digit login PIN**; that name is stamped on new ROs and shown on the customer PDF. The **admin PIN** is separate and must **not** match any login PIN.

1. First `carro` menu start → setup wizard (admin PIN + first tech name/login PIN), or Config → **11 Technicians**
2. Later starts: pick your name, then PIN (session lasts ~8 hours, or until logout)
3. Menu **`t`** — switch technician / **change my PIN** / logout
4. Adding a tech (admin): name → **generate PIN** (default) or enter one; PIN is shown once
5. CLI: `carro tech login` · `carro tech logout` · `carro tech whoami` · `carro tech add`

Roster file: `~/.config/carro/technicians.json` (PIN **hashes** only — never commit this). Admin PIN gates add/rename/reset/remove; a logged-in tech can change **their own** login PIN without admin.

When `server_url` is set, the roster **pulls/pushes** on login, after admin edits, and on `carro sync`, so every bay PC shares the same tech list. This is **same-shop multi-PC**, not separate shops on one server.

### Adding another drive later

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"extra","path":"/path/to/new/drive/carro"}' \
  http://YOUR_SERVER:8787/volumes
```

---

## Layout

```
cli/carro/              # CLI package (forms, PDF, OBD hook, photo providers)
server/carro_server     # FastAPI archive + phone upload sessions
scripts/carro           # launcher used by ~/.local/bin/carro
scripts/install.sh      # Linux workstation install
scripts/install.ps1     # Windows workstation install
scripts/install-server.sh
scripts/join-server.sh  # point a bay PC at the shop server
docs/SERVER_SETUP.md    # multi-PC server guide
docs/WINDOWS.md         # Windows bay PC guide
config.example.toml     # copy to ~/.config/carro/config.toml
```

---

## Privacy

This project is aimed at **your** lab and **your** bay notes. Keep real hostnames, LAN IPs, Tailscale names, tokens, customer PII dumps, shop logos, and `technicians.json` / session files out of git. Operator config lives in `~/.config/carro/` only.

---

## Roadmap / brainstorm (photos & iPhone)

The Tailscale QR path stays as the reliable “any phone on the mesh” option. **iOS Shortcuts → upload API** is supported via `carro photo shortcut` (setup page at `/u/<token>/shortcut`). Further ideas:
- **Cloud drop (Dropbox / iCloud Drive / Syncthing)** — phone saves into a watched folder; Car-RO attaches on save
- **AirDrop** — limited on Linux; usually ends as “AirDrop to Mac/nearby then copy,” so not first-class
- **API token UX** — clearer rotation, per-device upload tokens, expiry visible in the config menu

Photo providers stay modular so those experiments don’t break the local / QR paths other techs need.

---

## License / vibe

Personal tooling, shared because other techs in the same hobbyist/home-lab corner of the trade might want the same thing. Fork it, break it, wire it to your stack.
