import { useState } from "react";
import { ScaffoldNote } from "@/components/ScaffoldNote";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { obdApi, type DtcRow } from "@/lib/obdApi";

export function ScanCodesPage() {
  const [codes, setCodes] = useState<DtcRow[]>([]);
  const [lookupQ, setLookupQ] = useState("P0420");
  const [lookupRows, setLookupRows] = useState<
    { code: string; description: string; found?: boolean }[]
  >([]);
  const [lookupDbSize, setLookupDbSize] = useState<number | null>(null);
  const [lookupTried, setLookupTried] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      await fn();
      setMsg(label);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const doLookup = () =>
    void run("Lookup done", async () => {
      const r = await obdApi.lookup(lookupQ);
      setLookupRows(r.results);
      setLookupDbSize(r.db_size);
      setLookupTried(true);
    });

  return (
    <div className="space-y-4">
      <ScaffoldNote>
        Same as obdscan menu 4 / 5 / 13 / 17 — read / clear / lookup / save to Documents/Saved Codes.
      </ScaffoldNote>
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={busy}
          onClick={() =>
            void run("Codes read", async () => {
              const r = await obdApi.codes(false);
              setCodes(r.codes);
              if (!r.ok && r.note) setErr(r.note);
            })
          }
        >
          Read codes
        </Button>
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() =>
            void run("Codes read (force)", async () => {
              const r = await obdApi.codes(true);
              setCodes(r.codes);
            })
          }
        >
          Force read
        </Button>
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() => {
            if (!window.confirm("Clear stored DTCs and freeze-frame data?")) return;
            void run("Clear sent", async () => {
              const r = await obdApi.clearCodes();
              if (!r.ok) setErr(r.response || "Clear not accepted");
            });
          }}
        >
          Clear codes
        </Button>
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() =>
            void run("Report saved", async () => {
              const r = await obdApi.save(false);
              if (!r.ok) setErr(r.note || "Save failed");
              else if (r.codes) setCodes(r.codes);
              if (r.path) setMsg(`Saved → ${r.path}`);
            })
          }
        >
          Save report
        </Button>
      </div>

      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {msg ? <p className="text-sm text-muted">{msg}</p> : null}

      <div className="rounded-xl border border-border bg-surface">
        {codes.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-muted">No DTCs loaded yet.</div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border text-xs text-muted">
              <tr>
                <th className="px-4 py-2 font-medium">Type</th>
                <th className="px-4 py-2 font-medium">Code</th>
                <th className="px-4 py-2 font-medium">Description</th>
              </tr>
            </thead>
            <tbody>
              {codes.map((c) => (
                <tr key={`${c.type}-${c.code}`} className="border-b border-border last:border-0">
                  <td className="px-4 py-2 text-muted">{c.type}</td>
                  <td className="px-4 py-2 font-mono font-medium text-accent">{c.code}</td>
                  <td className="px-4 py-2">{c.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="text-xs font-medium uppercase tracking-wide text-muted">
          Lookup (offline DB)
        </div>
        <p className="mt-1 text-xs text-muted">
          Generic SAE definitions (e.g. P0420 catalyst). Separate from the live DTC list above.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Input
            className="max-w-xs"
            value={lookupQ}
            onChange={(e) => setLookupQ(e.target.value)}
            placeholder="P0420 P0301"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                doLookup();
              }
            }}
          />
          <Button variant="ghost" disabled={busy} onClick={doLookup}>
            Lookup
          </Button>
        </div>
        {lookupTried && lookupDbSize != null ? (
          <p className="mt-2 text-xs text-muted">Database: {lookupDbSize} codes loaded</p>
        ) : null}
        {lookupTried && lookupRows.length === 0 ? (
          <p className="mt-3 text-sm text-danger">No codes parsed — try P0420</p>
        ) : null}
        {lookupRows.length > 0 ? (
          <ul className="mt-3 space-y-2 text-sm">
            {lookupRows.map((r) => (
              <li
                key={r.code}
                className="rounded-lg border border-border bg-bg px-3 py-2"
              >
                <div className="font-mono font-medium text-accent">{r.code}</div>
                <div className="mt-0.5 text-fg">{r.description}</div>
                {r.found === false ? (
                  <div className="mt-0.5 text-xs text-muted">Not in generic table</div>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
