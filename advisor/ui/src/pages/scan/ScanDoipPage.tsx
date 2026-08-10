import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ScaffoldNote } from "@/components/ScaffoldNote";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  obdApi,
  type DoipPackSummary,
  type DoipProbeRow,
  type DoipVehicle,
} from "@/lib/obdApi";
import { formatLabel } from "@/lib/utils";

export function ScanDoipPage() {
  const [hasDoip, setHasDoip] = useState<boolean | null>(null);
  const [statusHint, setStatusHint] = useState<string | null>(null);
  const [statusNote, setStatusNote] = useState<string | null>(null);
  const [packs, setPacks] = useState<DoipPackSummary[]>([]);
  const [packId, setPackId] = useState("generic");
  const [ip, setIp] = useState("169.254.1.20");
  const [la, setLa] = useState("0x00E0");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [vehicles, setVehicles] = useState<DoipVehicle[]>([]);
  const [probeRows, setProbeRows] = useState<DoipProbeRow[]>([]);
  const [dids, setDids] = useState<{ id: string; value: string }[]>([]);
  const [codes, setCodes] = useState<string[]>([]);

  const selected = useMemo(
    () => packs.find((p) => p.id === packId) ?? null,
    [packs, packId],
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const st = await obdApi.doipStatus();
        if (cancelled) return;
        setHasDoip(st.has_doip);
        setStatusHint(st.hint);
        setStatusNote(st.note ?? null);
        const pr = await obdApi.doipPacks();
        if (cancelled) return;
        setPacks(pr.packs);
        if (pr.packs.length) {
          setPackId((cur) =>
            pr.packs.some((p) => p.id === cur) ? cur : pr.packs[0].id,
          );
        }
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : String(e));
          setHasDoip(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selected) return;
    if (selected.ip_hints[0]) setIp(selected.ip_hints[0]);
    if (selected.gateway_addresses[0]) setLa(selected.gateway_addresses[0]);
  }, [selected]);

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

  const target = () => ({ pack: packId, ip: ip.trim(), la: la.trim() });

  return (
    <div className="space-y-4">
      <ScaffoldNote>
        Enhanced DoIP / manufacturer packs (obdscan menu 15). Uses GT327{" "}
        <strong className="text-fg">ENET / DoIP</strong> — not the ELM Bluetooth
        connect path. Flip the hardware switch; ELM session.lock is unused here.
      </ScaffoldNote>

      <div className="rounded-xl border border-border bg-surface p-4 text-sm">
        <div className="text-xs font-medium uppercase tracking-wide text-muted">
          DoIP stack
        </div>
        <p className="mt-2">
          {hasDoip == null
            ? "Checking…"
            : hasDoip
              ? "Ready"
              : "Not installed"}
        </p>
        {statusHint ? (
          <p className="mt-1 font-mono text-xs text-muted">{statusHint}</p>
        ) : null}
        {statusNote ? <p className="mt-1 text-xs text-muted">{statusNote}</p> : null}
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <label className="block space-y-1.5 text-sm sm:col-span-1">
          <span className="text-muted">Manufacturer pack</span>
          <select
            className="flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-fg"
            value={packId}
            onChange={(e) => setPackId(e.target.value)}
            disabled={!packs.length}
          >
            {packs.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.id})
              </option>
            ))}
          </select>
        </label>
        <label className="block space-y-1.5 text-sm">
          <span className="text-muted">IP</span>
          <Input value={ip} onChange={(e) => setIp(e.target.value)} spellCheck={false} />
        </label>
        <label className="block space-y-1.5 text-sm">
          <span className="text-muted">Logical address</span>
          <Input value={la} onChange={(e) => setLa(e.target.value)} spellCheck={false} />
        </label>
      </div>

      {selected ? (
        <p className="text-xs text-muted">
          {selected.description} · {selected.module_count} modules · maturity{" "}
          {selected.maturity}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button
          disabled={busy || hasDoip === false}
          onClick={() =>
            void run("Discover done", async () => {
              const r = await obdApi.doipDiscover(5);
              setVehicles(r.vehicles);
              if (r.vehicles[0]) {
                setIp(r.vehicles[0].ip);
                setLa(r.vehicles[0].la);
              }
            })
          }
        >
          Discover
        </Button>
        <Button
          variant="ghost"
          disabled={busy || hasDoip === false || !ip.trim()}
          onClick={() =>
            void run("Probe done", async () => {
              const r = await obdApi.doipProbe({
                pack: packId,
                ip: ip.trim(),
                max_addresses: 12,
              });
              setProbeRows(r.results);
              if (r.alive[0]) setLa(r.alive[0].la);
            })
          }
        >
          Probe modules
        </Button>
        <Button
          variant="ghost"
          disabled={busy || hasDoip === false || !ip.trim() || !la.trim()}
          onClick={() =>
            void run("DIDs read", async () => {
              const r = await obdApi.doipDids(target());
              setDids(r.dids);
            })
          }
        >
          Read DIDs
        </Button>
        <Button
          variant="ghost"
          disabled={busy || hasDoip === false || !ip.trim() || !la.trim()}
          onClick={() =>
            void run("DTCs read", async () => {
              const r = await obdApi.doipDtcs(target());
              setCodes(r.codes);
              if (!r.ok && r.error) setErr(r.error);
            })
          }
        >
          Read DTCs
        </Button>
        <Button
          variant="ghost"
          disabled={busy || hasDoip === false || !ip.trim() || !la.trim()}
          onClick={() => {
            if (!window.confirm("Clear UDS DTCs on this ECU / logical address?")) {
              return;
            }
            void run("DTCs cleared", async () => {
              const r = await obdApi.doipClearDtcs(target());
              if (!r.ok) setErr(r.message);
              else setMsg(r.message);
            });
          }}
        >
          Clear DTCs
        </Button>
      </div>

      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {msg ? <p className="text-sm text-muted">{msg}</p> : null}

      {vehicles.length > 0 ? (
        <ResultCard title="Discovered vehicles">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted">
              <tr>
                <th className="py-1 pr-3 font-medium">IP</th>
                <th className="py-1 pr-3 font-medium">LA</th>
                <th className="py-1 font-medium">VIN</th>
              </tr>
            </thead>
            <tbody>
              {vehicles.map((v) => (
                <tr key={`${v.ip}-${v.la}`} className="border-t border-border">
                  <td className="py-1.5 pr-3 font-mono">
                    <button
                      type="button"
                      className="text-accent hover:underline"
                      onClick={() => {
                        setIp(v.ip);
                        setLa(v.la);
                      }}
                    >
                      {v.ip}
                    </button>
                  </td>
                  <td className="py-1.5 pr-3 font-mono">{v.la}</td>
                  <td className="py-1.5 font-mono">{v.vin || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ResultCard>
      ) : null}

      {probeRows.length > 0 ? (
        <ResultCard title="Module probe">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted">
              <tr>
                <th className="py-1 pr-3 font-medium">LA</th>
                <th className="py-1 pr-3 font-medium">Name</th>
                <th className="py-1 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {probeRows.map((r) => (
                <tr key={r.la} className="border-t border-border">
                  <td className="py-1.5 pr-3 font-mono">
                    <button
                      type="button"
                      className="text-accent hover:underline"
                      onClick={() => setLa(r.la)}
                    >
                      {r.la}
                    </button>
                  </td>
                  <td className="py-1.5 pr-3">{r.name}</td>
                  <td className={`py-1.5 ${r.alive ? "text-accent" : "text-muted"}`}>
                    {formatLabel(r.status)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ResultCard>
      ) : null}

      {dids.length > 0 ? (
        <ResultCard title="DIDs">
          <dl className="space-y-2 text-sm">
            {dids.map((d) => (
              <div key={d.id} className="flex flex-wrap justify-between gap-2">
                <dt className="text-muted">{d.id}</dt>
                <dd className="font-mono text-fg">{d.value}</dd>
              </div>
            ))}
          </dl>
        </ResultCard>
      ) : null}

      {codes.length > 0 ? (
        <ResultCard title="UDS DTCs">
          <ul className="space-y-1 font-mono text-sm">
            {codes.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </ResultCard>
      ) : null}
    </div>
  );
}

function ResultCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{title}</div>
      <div className="mt-3 max-h-80 overflow-auto">{children}</div>
    </div>
  );
}
