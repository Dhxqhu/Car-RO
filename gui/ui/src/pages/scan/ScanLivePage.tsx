import { useEffect, useState } from "react";
import { ScaffoldNote } from "@/components/ScaffoldNote";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { obdApi, type PidInfo } from "@/lib/obdApi";

export function ScanLivePage() {
  const [catalog, setCatalog] = useState<PidInfo[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [edit, setEdit] = useState("");
  const [values, setValues] = useState<
    Record<string, { value: string | null; unit: string; error?: string }>
  >({});
  const [streaming, setStreaming] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    void obdApi
      .pids()
      .then((r) => {
        setCatalog(r.pids);
        setSelected(r.selected);
        setEdit(r.selected.join(" "));
      })
      .catch((e: Error) => setErr(e.message));
  }, []);

  useEffect(() => {
    if (!streaming) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await obdApi.live();
        if (!cancelled) setValues(r.values);
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : String(e));
          setStreaming(false);
        }
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 500);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [streaming]);

  const applyConfig = async () => {
    setErr(null);
    try {
      const names = edit.split(/[\s,]+/).filter(Boolean);
      const r = await obdApi.configureLive(names);
      setSelected(r.pids);
      setEdit(r.pids.join(" "));
      if (r.unknown.length) setMsg(`Unknown ignored: ${r.unknown.join(", ")}`);
      else setMsg(`Live PIDs: ${r.pids.join(" ") || "(none)"}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-4">
      <ScaffoldNote>
        Live data + configure PIDs (obdscan menu 6 / 7 / 8). Custom PIDs come from the active
        profile (Profiles tab).
      </ScaffoldNote>

      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="text-xs font-medium uppercase tracking-wide text-muted">
          Configure live PIDs
        </div>
        <p className="mt-1 text-xs text-muted">
          Names separated by space/comma. Example: RPM THROTTLE COOLANT
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Input value={edit} onChange={(e) => setEdit(e.target.value)} className="min-w-[16rem] flex-1" />
          <Button variant="ghost" onClick={() => void applyConfig()}>
            Apply
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              setEdit("RPM SPEED COOLANT LOAD THROTTLE");
            }}
          >
            Default
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          disabled={streaming || selected.length === 0}
          onClick={() => {
            setErr(null);
            setStreaming(true);
          }}
        >
          Start stream
        </Button>
        <Button variant="ghost" disabled={!streaming} onClick={() => setStreaming(false)}>
          Stop
        </Button>
        <Button
          variant="ghost"
          onClick={() =>
            void (async () => {
              setErr(null);
              try {
                const r = await obdApi.live();
                setValues(r.values);
              } catch (e) {
                setErr(e instanceof Error ? e.message : String(e));
              }
            })()
          }
        >
          Snapshot once
        </Button>
      </div>

      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {msg ? <p className="text-sm text-muted">{msg}</p> : null}

      <div className="rounded-xl border border-border bg-surface">
        {Object.keys(values).length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-muted">
            No live values yet — connect, then start stream or snapshot.
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border text-xs text-muted">
              <tr>
                <th className="px-4 py-2 font-medium">PID</th>
                <th className="px-4 py-2 font-medium">Value</th>
                <th className="px-4 py-2 font-medium">Unit</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(values).map(([name, v]) => (
                <tr key={name} className="border-b border-border last:border-0">
                  <td className="px-4 py-2 font-mono">{name}</td>
                  <td className="px-4 py-2 font-medium">{v.value ?? "—"}</td>
                  <td className="px-4 py-2 text-muted">{v.unit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <details className="rounded-xl border border-border bg-surface p-4">
        <summary className="cursor-pointer text-sm font-medium">
          PID catalog ({catalog.length})
        </summary>
        <ul className="mt-3 max-h-64 space-y-1 overflow-auto font-mono text-xs text-muted">
          {catalog.map((p) => (
            <li key={p.name}>
              <button
                type="button"
                className="text-left hover:text-accent"
                onClick={() =>
                  setEdit((cur) => (cur.includes(p.name) ? cur : `${cur} ${p.name}`.trim()))
                }
              >
                {p.name} · 01{p.pid} · {p.unit}
                {p.custom ? " · custom" : ""}
              </button>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
