# Changelog

All notable user-facing changes are listed here. Version numbers match the repo root [`VERSION`](VERSION) file (`app_version` on `/health` and `/version`).

---

## 0.4.0 — 2026-08-17

### RO editor & desk workflow

- **Auto-save** on tech and advisor RO editors — debounced save (~2.5s) for customer/vehicle fields, open bay notes, and in-progress work-item edits; status hint next to Save; browser warning before closing with unsaved changes.
- **Intake notes** (advisor) — top-of-page arrival notes on new ROs (before work items); auto-saved; stays on the RO as a read-only reference after itemizing; visible to techs (internal only, not on customer PDF).
- **SI/IM & SI only** — choosing those work-item types auto-fills the customer concern (“State Inspection and Emissions Testing” / “State Inspection Only”) in the RO editor and calendar appointment flow.

### Parts

- **Part supersessions** — shop catalog linking superseded part numbers to current PNs; syncs to server; badges and lookup hints in RO editors and Parts pages; supersession fields on part lines.

### PDF & branding

- **Declined service on PDF** — declined found issues and declined work items appear under a **Declined Service** section with a liability disclaimer (not mixed with billable work).
- **Shop branding sync** — shop name and logo for customer PDFs can pull from the shared server so all bays print consistent headers after one desk saves branding.

### Server / merge

- RO merge and search index include `intake_notes` and part supersession fields.
- Shop server routes for part supersessions and shop branding (update server before relying on new sync features).

### Docs

- [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) — consolidated install/runtime requirements.
- README front page refreshed with current feature set and this release.

---

## 0.3.3 and earlier

See git history and prior [GitHub Releases](https://github.com/Dhxqhu/Car-RO/releases) for 0.3.x shop messaging, efficiency reports, found issues, daily/next-day queues, dual login, phone PWA, and related server API work.

---

## Upgrade notes (0.4.0)

1. Update **carro-server** on Linux first (`./scripts/update-server.sh`).
2. Update each bay/advisor PC (`./scripts/update-client.sh` or `Update-Car-RO.bat`).
3. Restart local engine + GUIs.
4. Advisor: save shop name/logo once on a configured desk if PDF headers were blank on other bays.
5. Optional: seed part supersession catalog from **Parts → Supersessions** on advisor or engine config.

Full procedure: [docs/UPDATING.md](docs/UPDATING.md).
