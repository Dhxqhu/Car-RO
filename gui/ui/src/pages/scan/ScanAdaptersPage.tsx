import { useEffect, useState } from "react";
import { ScaffoldNote } from "@/components/ScaffoldNote";
import { obdApi, type ObdAdapter } from "@/lib/obdApi";

export function ScanAdaptersPage() {
  const [adapters, setAdapters] = useState<ObdAdapter[]>([]);
  const [defaultId, setDefaultId] = useState<string | null>(null);
  const [path, setPath] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    obdApi
      .adapters()
      .then((r) => {
        setAdapters(r.adapters);
        setDefaultId(r.default_id);
        setPath(r.path);
        setNote(r.note ?? null);
      })
      .catch((e: Error) => setErr(e.message));
  }, []);

  return (
    <div className="space-y-4">
      <ScaffoldNote>
        Adapter wizard (USB vs Bluetooth / GT327) will mirror obdscan Config. Edit via CLI for now.
      </ScaffoldNote>
      {path ? <p className="font-mono text-xs text-muted">{path}</p> : null}
      {note ? <p className="text-sm text-muted">{note}</p> : null}
      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {adapters.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted">
          No adapters.json yet — run <code className="text-fg">obdscan</code> once to create it.
        </div>
      ) : (
        <ul className="space-y-2">
          {adapters.map((a, i) => {
            const id = String(a.id ?? i);
            const label = String(a.label ?? a.name ?? id);
            return (
              <li
                key={id}
                className="rounded-xl border border-border bg-surface px-4 py-3 text-sm"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{label}</span>
                  {defaultId && id === defaultId ? (
                    <span className="text-xs text-accent">default</span>
                  ) : null}
                </div>
                <div className="mt-1 font-mono text-xs text-muted">
                  {String(a.port ?? "—")} @ {String(a.baud ?? "—")}
                  {a.transport ? ` · ${String(a.transport)}` : ""}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
