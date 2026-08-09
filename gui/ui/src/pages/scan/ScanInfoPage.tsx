import { useEffect, useState } from "react";
import { ScaffoldNote } from "@/components/ScaffoldNote";
import { obdApi } from "@/lib/obdApi";

export function ScanInfoPage() {
  const [vehicle, setVehicle] = useState<Record<string, unknown> | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    obdApi
      .vehicle()
      .then((r) => {
        setVehicle(r.vehicle);
        setSource(r.source);
        setNote(r.note ?? null);
      })
      .catch((e: Error) => setErr(e.message));
  }, []);

  return (
    <div className="space-y-4">
      <ScaffoldNote>
        Shows cached vehicle info today; live Mode 09 / VIN read after connect is wired.
      </ScaffoldNote>
      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {note && !vehicle ? <p className="text-sm text-muted">{note}</p> : null}
      {vehicle ? (
        <div className="rounded-xl border border-border bg-surface p-4">
          <div className="text-xs text-muted">Source: {source || "—"}</div>
          <dl className="mt-3 grid gap-2 sm:grid-cols-2">
            {Object.entries(vehicle).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 text-sm">
                <dt className="text-muted">{k}</dt>
                <dd className="font-mono text-fg">{String(v)}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted">
          No cached vehicle yet.
        </div>
      )}
    </div>
  );
}
