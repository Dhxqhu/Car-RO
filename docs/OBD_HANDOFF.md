# obdscan ↔ Car-RO handoff

Contract for the bay pass-through so VIN / year / make / DTC text land on a repair order without path drift.

## Shared locations

| Role | Path |
| --- | --- |
| Saved DTC reports | `{Documents}/Saved Codes/dtc_YYYYMMDD_HHMMSS[_VIN].txt` |
| Last vehicle cache | `~/.cache/obdscan/last_vehicle.json` |
| Adapter profiles | `~/.config/obdscan/adapters.json` |

`Documents` honors `XDG_DOCUMENTS_DIR` / `~/.config/user-dirs.dirs`, else `~/Documents`.

Defined in:

- **obdscan:** `_documents_dir()`, `SAVED_CODES_DIR`, `LAST_VEHICLE_FILE`
- **Car-RO:** `cli/carro/obd/paths.py` (CLI + engine + GUI must import from here)

## Writers (obdscan)

| Event | Writes |
| --- | --- |
| Vehicle info collect | `last_vehicle.json` (Title Case keys: `VIN`, `Year`, `Make`, …) |
| Menu **17** / `obdscan save` | `dtc_*.txt` **and** refreshes `last_vehicle.json` |

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
| GUI Orders | **Pull OBD** → `POST /ros/{id}/pull-obd` |
| GUI Scanner | `/obd/vehicle`, `/obd/saved` (same paths) |

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

## Not automatic

Live connect inside the GUI engine is still stubbed (`POST /obd/connect` → 501). Until then, scan with **obdscan** CLI (or future Scanner wiring), then **Pull OBD** on the RO.
