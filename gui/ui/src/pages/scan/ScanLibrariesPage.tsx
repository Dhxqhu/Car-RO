import { useEffect, useState } from "react";
import { ScaffoldNote } from "@/components/ScaffoldNote";
import { Button } from "@/components/ui/button";
import { obdApi, type DoipPackDetail, type DoipPackSummary } from "@/lib/obdApi";

export function ScanLibrariesPage() {
  const [packs, setPacks] = useState<DoipPackSummary[]>([]);
  const [detail, setDetail] = useState<DoipPackDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    void obdApi
      .doipPacks()
      .then((r) => setPacks(r.packs))
      .catch((e: Error) => setErr(e.message));
  }, []);

  return (
    <div className="space-y-4">
      <ScaffoldNote>
        Manufacturer libraries (obdscan menu 16). Packs are address/DID scaffolds — use the DoIP
        tab to probe a live car on ENET.
      </ScaffoldNote>
      {err ? <p className="text-sm text-danger">{err}</p> : null}

      <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
        {packs.map((p) => (
          <li key={p.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
            <div>
              <div className="font-medium">{p.name}</div>
              <div className="text-xs text-muted">
                {p.id} · {p.module_count} modules · {p.did_count} DIDs · {p.maturity}
              </div>
            </div>
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                void obdApi
                  .doipPack(p.id)
                  .then(setDetail)
                  .catch((e: Error) => setErr(e.message))
              }
            >
              Details
            </Button>
          </li>
        ))}
      </ul>

      {detail ? (
        <div className="space-y-3 rounded-xl border border-border bg-surface p-4">
          <div className="text-sm font-medium">
            {detail.name}{" "}
            <span className="font-mono text-xs text-muted">({detail.id})</span>
          </div>
          <p className="text-sm text-muted">{detail.description}</p>
          <p className="text-xs text-muted">
            Tester {detail.tester_address} · port {detail.default_doip_port} · IP hints:{" "}
            {detail.ip_hints.join(", ")}
          </p>
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-muted">Modules</div>
            <ul className="mt-2 max-h-48 space-y-1 overflow-auto font-mono text-xs">
              {detail.modules.map((m) => (
                <li key={m.address}>
                  {m.address} · {m.name} · {m.addressing}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-muted">DIDs</div>
            <ul className="mt-2 max-h-48 space-y-1 overflow-auto font-mono text-xs">
              {detail.dids.map((d) => (
                <li key={d.did}>
                  {d.did} · {d.name}
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </div>
  );
}
