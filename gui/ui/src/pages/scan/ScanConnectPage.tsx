import { useEffect, useState } from "react";
import { ScaffoldNote } from "@/components/ScaffoldNote";
import { Button } from "@/components/ui/button";
import { obdApi, type ObdSession } from "@/lib/obdApi";

export function ScanConnectPage() {
  const [session, setSession] = useState<ObdSession | null>(null);
  const [found, setFound] = useState<boolean | null>(null);
  const [root, setRoot] = useState<string | null>(null);
  const [wired, setWired] = useState(false);
  const [lockHint, setLockHint] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () =>
    obdApi
      .health()
      .then((h) => {
        setSession(h.session);
        setFound(h.obdscan_found);
        setRoot(h.obdscan_root);
        setWired(h.wired);
        if (h.lock?.held) {
          setLockHint(`${h.lock.owner || "unknown"} (pid ${h.lock.pid}) · ${h.lock.port || "—"}`);
        } else if (h.lock?.stale) {
          setLockHint("stale lock (will clear on next connect)");
        } else {
          setLockHint(null);
        }
      })
      .catch((e: Error) => setMsg(e.message));

  useEffect(() => {
    void refresh();
  }, []);

  const connect = async () => {
    setBusy(true);
    setMsg(null);
    try {
      await obdApi.connect();
      await refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await obdApi.disconnect();
      setSession(r.session);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <ScaffoldNote>
        Connect opens a real ElmSession in the local engine and takes the shared adapter lock.
        Codes / live pages are still scaffold until the next pass.
      </ScaffoldNote>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-border bg-surface p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-muted">Status</div>
          <div className="mt-2 font-[family-name:var(--font-display)] text-xl">
            {session?.connected ? "Connected" : "Disconnected"}
          </div>
          <dl className="mt-3 space-y-1 text-sm text-muted">
            <div className="flex justify-between gap-2">
              <dt>Adapter</dt>
              <dd className="text-fg">{session?.adapter_label || "—"}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Port</dt>
              <dd className="font-mono text-fg">{session?.port || "—"}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Protocol</dt>
              <dd className="text-fg">{session?.protocol || "—"}</dd>
            </div>
          </dl>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button onClick={connect} disabled={busy}>
              Connect
            </Button>
            <Button variant="ghost" onClick={disconnect} disabled={busy}>
              Disconnect
            </Button>
          </div>
        </div>
        <div className="rounded-xl border border-border bg-surface p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-muted">
            Engine bridge
          </div>
          <dl className="mt-3 space-y-1 text-sm text-muted">
            <div className="flex justify-between gap-2">
              <dt>obdscan found</dt>
              <dd className="text-fg">{found == null ? "…" : found ? "yes" : "no"}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Live bus wired</dt>
              <dd className="text-fg">{wired ? "yes" : "not yet"}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Adapter lock</dt>
              <dd className="text-right text-fg">{lockHint || "free"}</dd>
            </div>
          </dl>
          {root ? (
            <p className="mt-3 break-all font-mono text-xs text-muted">{root}</p>
          ) : (
            <p className="mt-3 text-sm text-muted">
              Clone or set <code className="text-fg">OBDSCAN_ROOT</code> so the engine can import
              ElmSession later.
            </p>
          )}
        </div>
      </div>
      {msg ? <p className="text-sm text-danger">{msg}</p> : null}
    </div>
  );
}
