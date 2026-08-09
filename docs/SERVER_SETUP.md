# Car-RO server setup (same shop, many bay PCs)

This guide is for a **non-developer**. Follow the steps in order.

**Goal:** one always-on **Linux** box holds the shop archive (repair orders + photos). Every bay laptop talks to it using the **same shop token**.

You do **not** need a Windows server. Windows PCs are clients only — see [WINDOWS.md](WINDOWS.md).

---

## Do you need a server?

| Situation | What to do |
| --- | --- |
| One laptop, notes stay on that machine | **Skip this guide.** Local-only is fine. Leave Server URL empty. |
| Several bay PCs, or you want history that survives a dead laptop SSD | **Follow this guide.** |

---

## Two different “secrets” (read this once)

People often mix these up. They are **not** the same thing.

| Secret | Who uses it | What it unlocks |
| --- | --- | --- |
| **Shop API token** | Each **bay PC** (stored in config) | Permission for that PC to sync with the server (read/write the archive) |
| **Technician login PIN** | A **person** at the keyboard | Whose name is stamped on repair orders |

- The **shop token** is like the Wi‑Fi password for the archive: one shared secret for the whole shop.
- The **tech PIN** is like your personal locker code: each technician has their own.
- Phone / Shortcut upload links use a **third**, short-lived token created when you start an upload. Those do **not** replace the shop token.

**Rule of thumb:** the shop token is created on the **server** and **copied** to every bay PC. Do **not** invent a new token on a laptop with “Generate new token” unless you also change the server to match (see [Rotate the shop token](#rotate-the-shop-token-on-purpose)).

---

## What you will end up with

| Piece | Role |
| --- | --- |
| **carro-server** (Linux) | Stores all repair orders + photos |
| **Shop token** (`CARRO_TOKEN`) | One secret every bay PC must use |
| **Server URL** | e.g. `http://homebaseserver:8787` (Tailscale name is best) |
| **Bay PCs** | Run Car-RO (CLI and/or GUI), sync to that URL + token |

```
Bay laptop A ──┐
Bay laptop B ──┼──► carro-server (Linux + disk)
Bay laptop C ──┘
```

Important files on the **server** (never put these in git or a public chat):

| File | What it is |
| --- | --- |
| `~/.config/carro-server.env` | Server settings: data folder + **shop token** |
| `~/carro-data/` (default) | The actual archive on disk |
| `~/.config/systemd/user/carro-server.service` | Keeps the server running |

On each **bay PC**:

| File | What it is |
| --- | --- |
| `~/.config/carro/config.toml` | Client settings: shop name, **server URL**, **same shop token** |

---

## Step 1 — Pick the server computer

- A PC or mini-PC that stays **on** most of the time and has **disk space** for photos  
- **Linux** (Ubuntu / Debian / Fedora / Raspberry Pi OS / etc.)  
- Optional but **strongly recommended:** [Tailscale](https://tailscale.com/download) on the server **and** every bay PC  

Write down where photos should live, e.g. `/home/YOU/carro-data` or `/mnt/bigdisk/carro`.  
Default is fine: `~/carro-data`.

---

## Step 2 — Install Tailscale (recommended)

On the **server** and on **each bay PC**:

1. Install Tailscale from https://tailscale.com/download  
2. Log in with the **same** Tailscale account / tailnet  
3. On the server, note its MagicDNS name (e.g. `homebaseserver` or `homebaseserver.tailXXXX.ts.net`)

If you skip Tailscale, use the server’s LAN IP. That IP often changes when the router restarts — more breakage later.

---

## Step 3 — Install carro-server (this creates the shop token)

On the **server** machine:

1. Download the latest **Source code (zip)** from  
   https://github.com/Dhxqhu/Car-RO/releases/latest  
2. Unzip it (example folder: `~/Car-RO`)  
3. Open a terminal in that folder  

```bash
cd ~/Car-RO    # or wherever you unzipped
chmod +x scripts/install-server.sh
./scripts/install-server.sh
```

When asked **Enable and start carro-server now?** press **Enter** (Yes).

### What just happened?

- The script installed the server under `~/carro-server` (by default).  
- If `~/.config/carro-server.env` did **not** already exist, it **generated a random shop token** and saved it as `CARRO_TOKEN=...`.  
- It printed a big block: **GIVE THIS TO EVERY BAY PC**.  

**Copy the Server URL and Token somewhere safe** (password manager, locked note).  
You will paste them onto every bay laptop in Step 6.

Defaults:

| Setting | Default |
| --- | --- |
| Data directory | `~/carro-data` |
| Port | `8787` |
| Token file | `~/.config/carro-server.env` |

If you run `install-server.sh` again later (updates), it **keeps** the existing token file. It does **not** invent a new token unless you delete or edit that file yourself.

---

## Step 4 — Prove the server is alive

On the **server**:

```bash
curl -s http://127.0.0.1:8787/health
```

You should see JSON (not “connection refused”).

From a **bay PC** on Tailscale (replace the hostname):

```bash
curl -s http://YOUR_SERVER_HOSTNAME:8787/health
```

If that fails: firewall, wrong hostname, Tailscale not logged in, or server not running — see [Troubleshooting](#troubleshooting).

---

## Step 5 — Install Car-RO on each bay PC

### Linux bay PC

```bash
cd ~/Documents/Car-RO   # after unzip from Releases
./scripts/install.sh
carro
```

### Windows bay PC

See [WINDOWS.md](WINDOWS.md) (`scripts/install.ps1`).

You can also use the desktop GUI later; Config stores the **same** URL + token as the CLI.

---

## Step 6 — Point each bay PC at the server (paste the shop token)

Use the **exact** URL and token from Step 3 (or look them up — see [I forgot the shop token](#i-forgot-the-shop-token)).

### Easiest on Linux

From the Car-RO folder on the bay PC:

```bash
./scripts/join-server.sh
```

Paste the URL, then the token, when asked. Then:

```bash
carro sync
```

### By hand (Linux / Windows CLI)

```bash
carro config set server_url http://YOUR_SERVER_HOSTNAME:8787
carro config set token PASTE_THE_TOKEN_HERE
carro sync
```

### CLI menu

`carro` → **`c` Config** → set **Server URL** and **API token** → then menu **`s` Sync**.

### Desktop GUI

Log in as a technician → **Config** → set **Server URL** and **API token** → **Save configuration** → back on Orders, use **Sync**.

### Checklist for every bay PC

- [ ] Same **Server URL** as the other bays  
- [ ] Same **shop token** as the other bays (and as `CARRO_TOKEN` on the server)  
- [ ] Sync succeeds (no “unauthorized” / 401)

**Do not** click **Generate new token** on a bay PC during normal setup. That creates a **different** secret that the server will reject. Generating is only for rare “rotate everything” cases below.

---

## Step 7 — Technicians (shared roster)

1. On **one** bay PC, start `carro` (or the GUI) and finish technician setup (admin PIN + first tech).  
2. That PC pushes the tech list when the server is configured.  
3. On other bay PCs, start Car-RO — they **pull** the same tech list.  
4. Each tech picks their name and enters their **login PIN** (admin PIN is separate and must not match a login PIN).

Details: README → “Technician login”.

---

## Step 8 — Verify checklist

Do this once after setup:

- [ ] `curl` health works from a bay PC  
- [ ] Bay A: create a tiny RO → **Sync**  
- [ ] Bay B: **Sync** / history / search — you can see that RO  
- [ ] Bay B: log in as a tech that exists on the roster  
- [ ] Delete a mistake RO — it should leave both local and server  

---

## I forgot the shop token

On the **server** (SSH or local terminal):

```bash
grep CARRO_TOKEN ~/.config/carro-server.env
```

You should see a line like:

```text
CARRO_TOKEN=abc123_long_random_string
```

Copy everything **after** the `=` (no spaces). Paste that into every bay PC’s Config / `join-server.sh`.

To see the URL you used before, open that same file or re-run:

```bash
cd ~/Car-RO
./scripts/install-server.sh
```

(It keeps the existing token and prints the handoff block again.)

---

## Rotate the shop token (on purpose)

Only do this if the old token leaked, or you want a clean reset of shop access.  
**Every bay PC must get the new token**, or sync will fail with unauthorized.

### 1. On the server — put a new token in the env file

```bash
# Optional: generate a strong random token
python3 -c 'import secrets; print(secrets.token_urlsafe(24))'
```

Edit the env file (nano is fine):

```bash
nano ~/.config/carro-server.env
```

Change the `CARRO_TOKEN=` line to the new value. Save and exit (`Ctrl+O`, Enter, `Ctrl+X` in nano).

Example:

```text
CARRO_DATA_DIR=/home/YOU/carro-data
CARRO_TOKEN=paste_the_new_token_here
```

### 2. On the server — restart so it loads the new token

```bash
systemctl --user restart carro-server
systemctl --user status carro-server
```

Confirm it is **active (running)**.

### 3. On every bay PC — install the new token

**Linux helper:**

```bash
./scripts/join-server.sh
```

(Use the same Server URL; paste the **new** token.)

**Or CLI:**

```bash
carro config set token PASTE_THE_NEW_TOKEN_HERE
carro sync
```

**Or GUI:** Config → paste new API token → Save → Sync.

### 4. Confirm

From a bay PC, Sync should succeed. If you still see **401 / unauthorized**, that PC still has the old token — fix that PC only.

---

## Adding another bay PC later

1. Install Car-RO on the new PC  
2. Run `./scripts/join-server.sh` (or Config URL + token)  
3. `carro sync` (or GUI **Sync**)  
4. Login with an existing tech PIN (or admin adds a new tech on any PC)

No new server install. Keep using the **same** shop token until you rotate it on purpose.

---

## Updating the server after a Car-RO release

On the server:

```bash
cd ~/Car-RO
# update files (git pull, or unzip a new Release over the folder)
./scripts/install-server.sh
# say Yes to restart when prompted
```

Updates **keep** `~/.config/carro-server.env` (your token and data path stay put).

If a bay PC says a URL is **404** (e.g. `/technicians`), the server is still on old code — update + restart.

---

## Day-to-day server commands

Run these **on the server**:

```bash
# Is it running?
systemctl --user status carro-server

# Restart after editing carro-server.env
systemctl --user restart carro-server

# Recent logs if something broke
journalctl --user -u carro-server -n 50 --no-pager

# Look up the shop token
grep CARRO_TOKEN ~/.config/carro-server.env
```

If the server stops when you log out of a graphical session on a headless box:

```bash
loginctl enable-linger $USER
```

(`install-server.sh` tries to enable linger for you.)

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `connection refused` / unreachable | Is `carro-server` running? `systemctl --user status carro-server`. Enable linger: `loginctl enable-linger $USER` |
| Health works on server, not from bay | Tailscale not logged in on both; wrong hostname; firewall blocking port **8787** |
| `401` / unauthorized / “Invalid token” | Token mismatch. On the server: `grep CARRO_TOKEN ~/.config/carro-server.env`. Put **that exact value** on every bay PC. Do not “Generate new token” on the laptop unless you also changed the server. |
| Sync OK but techs missing | Run sync / tech menu **Pull roster**; ensure server was updated for `/technicians` |
| Deleted RO comes back | Server delete failed (old server). Update server, delete again |
| Forgot token | See [I forgot the shop token](#i-forgot-the-shop-token) |
| Generated a token in the GUI and now sync fails | You changed only the **bay** copy. Either paste the server’s `CARRO_TOKEN` back onto the bay, or [rotate](#rotate-the-shop-token-on-purpose) the server to match the new one **and** update every other bay |

---

## Security notes (keep it simple)

- One shop = one shop token. Anyone with that token can read/write the archive.  
- Prefer Tailscale over exposing port 8787 to the whole internet.  
- Do not commit `config.toml`, `carro-server.env`, or `technicians.json` to git.  
- Treat the shop token like a password: password manager is fine; public Discord/Slack is not.
