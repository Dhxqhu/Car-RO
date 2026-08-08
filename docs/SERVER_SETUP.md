# Car-RO server setup (same shop, many bay PCs)

This guide is for a **non-developer**. Follow the steps in order.  
Goal: one always-on **Linux** box holds the archive; every bay laptop talks to it with the **same token**.

You do **not** need a Windows server. Windows PCs are clients only (see [WINDOWS.md](WINDOWS.md)).

---

## What you will end up with

| Piece | Role |
| --- | --- |
| **carro-server** (Linux) | Stores all repair orders + photos |
| **Shop token** | One secret password every bay PC uses |
| **Server URL** | e.g. `http://homebaseserver:8787` (Tailscale name is best) |
| **Bay PCs** | Run `carro`, sync to that URL + token |

```
Bay laptop A ──┐
Bay laptop B ──┼──► carro-server (Linux + disk)
Bay laptop C ──┘
```

---

## Step 1 — Pick the server computer

- A PC or mini-PC that stays **on** and has **disk space** for photos  
- **Linux** (Ubuntu / Debian / Fedora / etc.)  
- Optional but strongly recommended: [Tailscale](https://tailscale.com/download) on the server **and** every bay PC (so you get a stable name like `homebaseserver` instead of fighting Wi‑Fi IPs)

Write down the disk folder you want for data, e.g. `/home/YOU/carro-data` or `/mnt/bigdisk/carro`.

---

## Step 2 — Install Tailscale (recommended)

On the **server** and on **each bay PC**:

1. Install Tailscale from https://tailscale.com/download  
2. Log in with the same Tailscale account / tailnet  
3. On the server, note its MagicDNS name (e.g. `homebaseserver` or `homebaseserver.tailXXXX.ts.net`)

If you skip Tailscale, use the server’s LAN IP (changes more often — more breakage).

---

## Step 3 — Get Car-RO onto the server

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

The script prints a big block: **GIVE THIS TO EVERY BAY PC**.  
Copy the **Server URL** and **Token** somewhere safe (phone notes, password manager).  
Do **not** put them in git or a public chat.

Default data dir: `~/carro-data`  
Default port: `8787`  
Env file (token lives here): `~/.config/carro-server.env`

---

## Step 4 — Quick check that the server is alive

On the **server**:

```bash
curl -s http://127.0.0.1:8787/health
```

You should see JSON (not “connection refused”).

From a **bay PC** on Tailscale (replace hostname):

```bash
curl -s http://YOUR_SERVER_HOSTNAME:8787/health
```

If that fails: firewall, wrong hostname, or server not running — see [Troubleshooting](#troubleshooting).

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

---

## Step 6 — Point each bay PC at the server

**Easiest (Linux):** from the Car-RO folder:

```bash
./scripts/join-server.sh
```

Paste the **URL** and **token** from the server install output.

**Or** by hand:

```bash
carro config set server_url http://YOUR_SERVER_HOSTNAME:8787
carro config set token PASTE_THE_TOKEN_HERE
carro sync
```

Or: `carro` → **`c` Config** → set **Server URL** and **API token** → then menu **`s` Sync**.

Do this on **every** bay laptop with the **same** URL and **same** token.

---

## Step 7 — Technicians (shared roster)

1. On **one** bay PC, start `carro` and finish the technician setup (admin PIN + first tech).  
2. That PC pushes the tech list when the server is configured.  
3. On other bay PCs, start `carro` — they **pull** the same tech list.  
4. Each tech picks their name and enters their **login PIN** (admin PIN is separate).

Details: README → “Technician login”.

---

## Step 8 — Verify checklist

Do this once after setup:

- [ ] `curl` health works from a bay PC  
- [ ] Bay A: create a tiny RO → menu **`s` Sync**  
- [ ] Bay B: menu **`s` Sync** or search with server — you can see that RO (or pull it)  
- [ ] Bay B: log in as a tech that exists on the roster  
- [ ] Delete a mistake RO with menu **`d`** — it should leave both local and server  

---

## Adding another bay PC later

1. Install Car-RO on the new PC  
2. Run `./scripts/join-server.sh` (or Config URL + token)  
3. `carro sync`  
4. Login with an existing tech PIN (or admin adds a new tech on any PC)

No new server install. Same token forever (until you rotate it on purpose).

---

## Updating the server after a Car-RO release

On the server:

```bash
cd ~/Car-RO
# update files (git pull, or unzip a new Release over the folder)
./scripts/install-server.sh
# say Yes to restart when prompted
```

If a bay PC says a URL is **404** (e.g. `/technicians`), the server is still on old code — update + restart.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `connection refused` / unreachable | Is `carro-server` running? `systemctl --user status carro-server` on the server. Enable linger: `loginctl enable-linger $USER` |
| Health works on server, not from bay | Tailscale not logged in on both; wrong hostname; firewall blocking port **8787** |
| `401` / unauthorized | Token mismatch — copy `CARRO_TOKEN` from `~/.config/carro-server.env` onto every bay PC |
| Sync seems OK but techs missing | Run sync / tech menu **Pull roster**; ensure server was updated for `/technicians` |
| Deleted RO comes back | Server delete failed (old server). Update server, delete again, or delete on server host |
| Forgot token | On server: `grep CARRO_TOKEN ~/.config/carro-server.env` |

Useful commands on the **server**:

```bash
systemctl --user status carro-server
systemctl --user restart carro-server
journalctl --user -u carro-server -n 50 --no-pager
```

---

## Security notes (keep it simple)

- One shop = one token. Anyone with the token can read/write the archive.  
- Prefer Tailscale over exposing port 8787 to the whole internet.  
- Do not commit `config.toml`, `carro-server.env`, or `technicians.json` to git.  
