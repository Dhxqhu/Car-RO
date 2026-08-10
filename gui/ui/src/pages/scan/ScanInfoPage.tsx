import { useEffect, useMemo, useState } from "react";
import { ScaffoldNote } from "@/components/ScaffoldNote";
import { Button } from "@/components/ui/button";
import { obdApi } from "@/lib/obdApi";
import { formatLabel, formatStatus } from "@/lib/utils";

const PRIMARY_KEYS = ["vin", "year", "make"] as const;

function labelFor(key: string): string {
  if (key === "vin") return "VIN";
  if (key === "mil") return "MIL";
  if (key === "wmi") return "WMI";
  return formatLabel(key);
}

function formatObdSource(source: string | null): string {
  if (!source) return "—";
  if (source === "live") return "Live adapter";
  if (source === "cache" || source === "saved") return "Saved codes";
  return formatLabel(source);
}

export function ScanInfoPage() {
  const [vehicle, setVehicle] = useState<Record<string, unknown> | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [readiness, setReadiness] = useState<{
    ok: boolean;
    mil?: boolean;
    dtc_count?: number;
    ignition?: string;
    monitors: { name: string; status: string }[];
  } | null>(null);
  const [freeze, setFreeze] = useState<{
    dtc_raw: string;
    samples: { name: string; pid: string; value: string }[];
  } | null>(null);

  const loadCache = () =>
    obdApi
      .vehicle()
      .then((r) => {
        setVehicle(r.vehicle);
        setSource(r.source);
        setNote(r.note ?? null);
      })
      .catch((e: Error) => setErr(e.message));

  useEffect(() => {
    void loadCache();
  }, []);

  const { fields, snapshot } = useMemo(() => {
    if (!vehicle) return { fields: [] as [string, string][], snapshot: "" };
    const snapRaw = vehicle.obd_snapshot;
    const snapshot =
      typeof snapRaw === "string" ? snapRaw : snapRaw != null ? String(snapRaw) : "";
    const seen = new Set<string>(["obd_snapshot"]);
    const fields: [string, string][] = [];
    for (const key of PRIMARY_KEYS) {
      const v = vehicle[key];
      if (v != null && String(v).trim() !== "") {
        fields.push([key, String(v)]);
        seen.add(key);
      }
    }
    for (const [k, v] of Object.entries(vehicle)) {
      if (seen.has(k) || v == null || String(v).trim() === "") continue;
      fields.push([k, String(v)]);
    }
    return { fields, snapshot };
  }, [vehicle]);

  return (
    <div className="space-y-4">
      <ScaffoldNote>
        Vehicle info (menu 10), readiness / MIL (11), freeze frame (12). Cache loads offline;
        live actions need Connect.
      </ScaffoldNote>

      <div className="flex flex-wrap gap-2">
        <Button
          disabled={busy}
          onClick={() => {
            setBusy(true);
            setErr(null);
            void obdApi
              .vehicleLive()
              .then((r) => {
                setVehicle(r.vehicle);
                setSource(r.source);
                setNote(null);
              })
              .catch((e: Error) => setErr(e.message))
              .finally(() => setBusy(false));
          }}
        >
          Refresh live
        </Button>
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            setErr(null);
            void obdApi
              .readiness()
              .then(setReadiness)
              .catch((e: Error) => setErr(e.message))
              .finally(() => setBusy(false));
          }}
        >
          Readiness / MIL
        </Button>
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            setErr(null);
            void obdApi
              .freeze()
              .then(setFreeze)
              .catch((e: Error) => setErr(e.message))
              .finally(() => setBusy(false));
          }}
        >
          Freeze frame
        </Button>
        <Button variant="ghost" disabled={busy} onClick={() => void loadCache()}>
          Reload cache
        </Button>
      </div>

      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {note && !vehicle ? <p className="text-sm text-muted">{note}</p> : null}

      {vehicle ? (
        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-surface p-4">
            <div className="text-xs text-muted">Source: {formatObdSource(source)}</div>
            {fields.length > 0 ? (
              <dl className="mt-3 space-y-2">
                {fields.map(([k, v]) => (
                  <div
                    key={k}
                    className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-sm"
                  >
                    <dt className="text-muted">{labelFor(k)}</dt>
                    <dd className="font-mono text-fg">{v}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="mt-3 text-sm text-muted">No structured vehicle fields.</p>
            )}
          </div>
          {snapshot ? (
            <div className="rounded-xl border border-border bg-surface p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-muted">
                OBD snapshot
              </div>
              <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs leading-relaxed text-fg">
                {snapshot}
              </pre>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted">
          No cached vehicle yet.
        </div>
      )}

      {readiness ? (
        <div className="rounded-xl border border-border bg-surface p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-muted">
            Readiness / MIL
          </div>
          {!readiness.ok ? (
            <p className="mt-2 text-sm text-muted">No readiness data (need ECU).</p>
          ) : (
            <>
              <p className="mt-2 text-sm">
                MIL:{" "}
                <span className={readiness.mil ? "text-danger" : "text-accent"}>
                  {readiness.mil ? "On" : "Off"}
                </span>{" "}
                · DTC count: {readiness.dtc_count}
                {readiness.ignition
                  ? ` · Ignition: ${formatLabel(readiness.ignition)}`
                  : ""}
              </p>
              <ul className="mt-3 space-y-1 text-sm">
                {readiness.monitors.map((m) => (
                  <li key={m.name} className="flex justify-between gap-3">
                    <span className="text-muted">{m.name}</span>
                    <span>{formatStatus(m.status)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      ) : null}

      {freeze ? (
        <div className="rounded-xl border border-border bg-surface p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-muted">
            Freeze frame
          </div>
          <pre className="mt-2 max-h-32 overflow-auto text-xs text-muted">{freeze.dtc_raw}</pre>
          <ul className="mt-3 space-y-1 text-sm">
            {freeze.samples.map((s) => (
              <li key={s.name} className="flex justify-between gap-3">
                <span className="text-muted">
                  {s.name} ({s.pid})
                </span>
                <span className="font-mono">{s.value}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
