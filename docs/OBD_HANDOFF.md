# obdscan ↔ Car-RO handoff

Contract for the bay pass-through so VIN / year / make / DTC text land on a repair order without path drift.

## Shared locations

| Role | Path |
| --- | --- |
| Saved DTC reports | `{Documents}/Saved Codes/dtc_YYYYMMDD_HHMMSS[_VIN].txt` |
| Last vehicle cache | `~/.cache/obdscan/last_vehicle.json` |
| Adapter profiles | `~/.config/obdscan/adapters.json` |
| Adapter session lock | `~/.cache/obdscan/session.lock` |

`Documents` honors `XDG_DOCUMENTS_DIR` / `~/.config/user-dirs.dirs`, else `~/Documents`.

Defined in:

- **obdscan:** `_documents_dir()`, `SAVED_CODES_DIR`, `LAST_VEHICLE_FILE`, `session_lock.py`
- **Car-RO:** `cli/carro/obd/paths.py`, `cli/carro/obd/session_lock.py` (keep lockstep with obdscan)

## Adapter ownership (`session.lock`)

Only one living process may hold the ELM serial port at a time.

| Field | Meaning |
| --- | --- |
| `pid` | Process that opened the adapter |
| `owner` | `obdscan-cli` · `carro-engine` · `obdscan-gui` (future) |
| `port` | Serial path, e.g. `/dev/rfcomm0` |
| `started_at` | UTC ISO timestamp |

Rules:

1. Before open → if lock exists and PID is alive → refuse (`Adapter in use by …`)
2. If lock exists and PID is dead → treat as stale and replace
3. On successful open → write lock; on disconnect / process exit → release if we own it

CLI (`obdscan`) and Car-RO engine (`POST /obd/connect`) both use this. A future small Python-only Scanner GUI should use the same helper and owner tag `obdscan-gui`.

## Writers (obdscan)

| Event | Writes |
| --- | --- |
| Vehicle info collect | `last_vehicle.json` (Title Case keys: `VIN`, `Year`, `Make`, …) |
| Menu **17** / `obdscan save` | `dtc_*.txt` **and** refreshes `last_vehicle.json` |
| Connect | `session.lock` |

## Readers (Car-RO)

`carro.obd.provider.pull_vehicle_fields(prefer_vin=…)`:

1. Load `last_vehicle.json` if useful  
2. Load newest `dtc_*.txt` (VIN in filename preferred when `prefer_vin` set)  
3. Pick the best by freshness; VIN match beats a newer unrelated car  
4. Fall back to `obdscan info` subprocess  
5. Enrich missing year/make from VIN WMI / year code  

Surfaces:

| Surface | How |
| --- | --- |
| CLI form | **F2** / menu pull |
| CLI | `carro pull-obd`, `carro new --from-obd` |
| GUI Orders | **Pull OBD** → `POST /ros/{id}/pull-obd` (tech login required) |
| GUI Scanner | `/obd/vehicle`, `/obd/saved`, `/obd/connect` (no PIN required) |

## Field mapping onto RO

| Source | RO field |
| --- | --- |
| `VIN` / `vin` | `vin` |
| `Year` / `year` | `year` |
| `Make` / `make` | `make` |
| Full report / cache text | `obd_snapshot` |

Model / plate / mileage are **not** inferred — leave blank for the tech.

## Gotchas that are handled

- Older `dtc_*.txt` files without Year/Make lines → VIN enrichment fills them  
- Empty or corrupt `last_vehicle.json` → ignored, fall through to Saved Codes  
- RO already has a VIN → prefer a report for that VIN over the chronologically newest other car  
- Snapshot length capped (~12k chars) so large DTC lists still fit notes/PDF  
- CLI and GUI fighting rfcomm → `session.lock` returns a clear busy error  

## Tests

```bash
# from Car-RO repo root, after ./scripts/install.sh
.venv/bin/pip install -e '.[dev]'   # once — pulls pytest
.venv/bin/pytest -q
```

Covers Saved Codes / `last_vehicle` priority, VIN preference, enrich, XDG Documents, and `session.lock` busy/stale rules. No dongle required.

## Deferred (later work)

- Windows packaging / engine sidecar beside the `.exe`
- Smaller Python-only Scanner GUI (reuse lock + these paths)
