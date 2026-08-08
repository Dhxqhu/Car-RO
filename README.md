# Car-RO — technician repair-order CLI (links to obdscan)

Write up jobs from the terminal: customer, vehicle, complaint, tech notes, OBD snapshot, photos, and a clean customer PDF. No accounting or billing.

## Install (this machine)

```bash
cd ~/Documents/Car-RO
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
ln -sf "$(pwd)/scripts/carro" ~/.local/bin/carro
cp config.example.toml ~/.config/carro/config.toml   # then edit
carro config init
```

Command name: **`carro`**. Ensure `~/.local/bin` is on your `PATH` (most setups already have this).

## Repair order form

Opening or editing an RO launches a full-screen form (Textual):

- **Tab / Shift+Tab** — move between fields  
- **Ctrl+S** — save  
- **Ctrl+Q** / **Esc** — quit without saving  
- **F2** — pull OBD / Saved Codes into the form  

Complaint and tech notes are multi-line text areas.

```bash
carro                  # interactive menu
carro new --from-obd   # new RO, try autofill from obdscan / Saved Codes
carro list
carro pull-obd RO-…
carro photo add ./pic.jpg --id RO-… --tag intake
carro photo ingest --id RO-… --tag diag   # from inbox_dir
carro pdf RO-…
carro sync             # push to your server + prune local cache
```

## Bring your own server

Car-RO can run **local-only**. For bulk storage on another machine:

1. Copy the `server/` tree to the host.
2. Create a data directory on the disk you want (example placeholder):

   ```bash
   export CARRO_DATA_DIR=/path/to/your/drive/carro
   # Optional: multiple named volumes (add drives later without code changes)
   export CARRO_VOLUMES="primary=/path/to/drive_a/carro,extra=/path/to/drive_b/carro"
   export CARRO_TOKEN="generate-a-long-random-token"
   ```

3. Python venv + deps, then:

   ```bash
   cd ~/carro-server
   .venv/bin/pip install -r requirements.txt
   PYTHONPATH=. .venv/bin/uvicorn carro_server.main:app --host 0.0.0.0 --port 8787
   ```

4. Optional systemd user unit: see `server/carro-server.service`.

5. On the laptop, **never commit** real URLs:

   ```bash
   carro config set server_url http://YOUR_SERVER:8787
   carro config set token YOUR_TOKEN
   carro config set local_keep 20
   carro sync
   ```

### Adding another drive later

On the server (API or by editing `volumes.json` under the data dir):

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"extra","path":"/path/to/new/drive/carro"}' \
  http://YOUR_SERVER:8787/volumes
```

New photos can target a volume; metadata records which volume holds each file.

## Photos (modular)

Default provider is **`local`**: `carro photo add` or drop files in `inbox_dir` then `carro photo ingest`.

Swap providers later via config (`photos.provider`) without changing the RO core. Optional `web_qr` is stubbed for a future Tailscale upload page.

## Layout

```
cli/carro/     # CLI package
server/        # FastAPI storage service
config.example.toml
```

## Privacy

Do not put personal hostnames, LAN IPs, or passwords in this repository. Use `~/.config/carro/config.toml` on each machine.
