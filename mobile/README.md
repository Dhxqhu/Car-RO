# Car-RO phone PWA

Lighter shop app served by **carro-server** (not the bay Tauri GUI).

```bash
# from repo root
./scripts/build-pwa.sh
```

That writes `server/pwa/`. `install-server.sh` / `update-server.sh` copy it onto the shop box.

Dev against a running server on `:8787`:

```bash
cd mobile
npm install
npm run dev
```

See [docs/SERVER_SETUP.md](../docs/SERVER_SETUP.md) → **Phone app (PWA)**.
