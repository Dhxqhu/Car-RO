import { useEffect, useState } from "react";
import { ConnectionHints, parseApiError } from "@/components/ConnectionHints";
import { ScaffoldNote } from "@/components/ScaffoldNote";
import { Button } from "@/components/ui/button";
import { obdApi, type ObdAdapter, type ObdSession } from "@/lib/obdApi";

export function ScanConnectPage() {
  const [session, setSession] = useState<ObdSession | null>(null);
  const [found, setFound] = useState<boolean | null>(null);
  const [root, setRoot] = useState<string | null>(null);
  const [wired, setWired] = useState(false);
  const [platform, setPlatform] = useState<string | null>(null);
  const [healthHints, setHealthHints] = useState<string[]>([]);
  const [lockHint, setLockHint] = useState<string | null>(null);
  const [adapters, setAdapters] = useState<ObdAdapter[]>([]);
  const [defaultId, setDefaultId] = useState<string | null>(null);
  const [adapterId, setAdapterId] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [errHints, setErrHints] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const refresh = () =>
    Promise.all([obdApi.health(), obdApi.adapters().catch(() => null)]).then(([h, a]) => {
      setSession(h.session);
      setFound(h.obdscan_found);
      setRoot(h.obdscan_root);
      setWired(h.wired);
      setPlatform(h.platform ?? null);
      setHealthHints(h.connection_hints ?? []);
      if (h.lock?.held) {
        setLockHint(`${h.lock.owner || "unknown"} (pid ${h.lock.pid}) · ${h.lock.port || "—"}`);
      } else if (h.lock?.stale) {
        setLockHint("stale lock (will clear on next connect)");
      } else {
        setLockHint(null);
      }
      if (a) {
        setAdapters(a.adapters);
        setDefaultId(a.default_id);
        if (!adapterId && a.default_id) setAdapterId(a.default_id);
      }
    });

  useEffect(() => {
    let cancelled = false;
    void refresh().catch((e: unknown) => {
      if (!cancelled) {
        const { message, hints } = parseApiError(e);
        setMsg(message);
        setErrHints(hints);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const connect = async () => {
    setBusy(true);
    setMsg(null);
    setErrHints([]);
    try {
      await obdApi.connect(adapterId ? { adapter_id: adapterId } : {});
      await refresh();
    } catch (e) {
      const { message, hints } = parseApiError(e);
      setMsg(message);
      setErrHints(hints);
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    setMsg(null);
    setErrHints([]);
    try {
      const r = await obdApi.disconnect();
      setSession(r.session);
    } catch (e) {
      const { message, hints } = parseApiError(e);
      setMsg(message);
      setErrHints(hints);
    } finally {
      setBusy(false);
    }
  };

  const showHints =
    errHints.length > 0
      ? errHints
      : found === false
        ? healthHints
        : msg
          ? healthHints
          : [];

  return (
    <div className="space-y-4">
      <ScaffoldNote>
        Connect opens a real ElmSession and takes the shared adapter lock (obdscan menu 1–3).
        DoIP / ENET is on the DoIP tab — flip the GT327 switch for that path.
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
          {adapters.length > 0 ? (
            <label className="mt-4 block space-y-1.5 text-sm">
              <span className="text-muted">Connect with</span>
              <select
                className="flex h-10 w-full rounded-lg border border-border bg-bg px-3 text-sm text-fg"
                value={adapterId}
                onChange={(e) => setAdapterId(e.target.value)}
              >
                {adapters.map((a, i) => {
                  const id = String(a.id ?? i);
                  return (
                    <option key={id} value={id}>
                      {String(a.label ?? id)}
                      {defaultId === id ? " (default)" : ""}
                    </option>
                  );
                })}
              </select>
            </label>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <Button onClick={() => void connect()} disabled={busy}>
              Connect
            </Button>
            <Button variant="ghost" onClick={() => void disconnect()} disabled={busy}>
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
              <dt>Host OS</dt>
              <dd className="text-fg">{platform || "—"}</dd>
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
              ElmSession.
            </p>
          )}
        </div>
      </div>
      {msg ? <p className="text-sm text-danger">{msg}</p> : null}
      {found === false || msg || errHints.length > 0 ? (
        <ConnectionHints
          title={found === false ? "obdscan not found — try this" : "Connection tips"}
          hints={showHints}
          platform={platform}
        />
      ) : null}
    </div>
  );
}
