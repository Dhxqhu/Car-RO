import { useEffect, useState } from "react";
import { ConnectionHints, parseApiError } from "@/components/ConnectionHints";
import { ScaffoldNote } from "@/components/ScaffoldNote";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { obdApi, type ObdAdapter } from "@/lib/obdApi";

export function ScanAdaptersPage() {
  const [adapters, setAdapters] = useState<ObdAdapter[]>([]);
  const [defaultId, setDefaultId] = useState<string | null>(null);
  const [path, setPath] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [id, setId] = useState("");
  const [label, setLabel] = useState("");
  const [port, setPort] = useState("");
  const [baud, setBaud] = useState("38400");
  const [busy, setBusy] = useState(false);
  const [discoverNote, setDiscoverNote] = useState<string | null>(null);
  const [hints, setHints] = useState<string[]>([]);
  const [platform, setPlatform] = useState<string | null>(null);

  const refresh = () =>
    obdApi
      .adapters()
      .then((r) => {
        setAdapters(r.adapters);
        setDefaultId(r.default_id);
        setPath(r.path);
        setNote(r.note ?? null);
      })
      .catch((e: unknown) => {
        const { message, hints: h } = parseApiError(e);
        setErr(message);
        setHints(h);
      });

  useEffect(() => {
    void refresh();
    void obdApi
      .health()
      .then((h) => setPlatform(h.platform ?? null))
      .catch(() => undefined);
  }, []);

  const runSetup = async (kind: "usb" | "bt") => {
    setBusy(true);
    setErr(null);
    setMsg(null);
    setDiscoverNote(null);
    setHints([]);
    try {
      if (kind === "usb") {
        const r = await obdApi.autosetupUsb();
        setMsg(r.message || `USB adapter ${r.adapter_id} ready`);
        if (r.hints?.length) setHints(r.hints);
      } else {
        setDiscoverNote("Scanning Bluetooth (~8s) — keep the adapter on and in BT/ELM mode…");
        const r = await obdApi.autosetupBluetooth({ scan_seconds: 8 });
        setMsg(r.message || `Bluetooth adapter ${r.adapter_id} ready`);
        if (r.warning) setDiscoverNote(r.warning);
        if (!r.elm_ok && r.ok) {
          setDiscoverNote(
            (r.warning ? `${r.warning} · ` : "") +
              "Profile saved; ELM hello not seen yet — try Connect from this page.",
          );
          setHints(r.hints ?? []);
        } else if (r.hints?.length) {
          setHints(r.hints);
        }
      }
      await refresh();
    } catch (e) {
      const { message, hints: h } = parseApiError(e);
      setErr(message);
      setHints(h);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <ScaffoldNote>
        Adapter config (obdscan menu <strong className="text-fg">c</strong>). Edits{" "}
        <code className="text-fg">adapters.json</code> shared with the CLI. Auto-setup scans
        and probes like the CLI wizard.
      </ScaffoldNote>
      {path ? <p className="font-mono text-xs text-muted">{path}</p> : null}
      {note ? <p className="text-sm text-muted">{note}</p> : null}

      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="text-xs font-medium uppercase tracking-wide text-muted">
          Auto-setup
        </div>
        <p className="mt-1 text-xs text-muted">
          USB probes serial ports (Linux: /dev/ttyUSB* · Windows: COMx). Bluetooth prefers
          GT327 / ELM names — Linux binds rfcomm; Windows uses a paired Bluetooth COM port —
          then probes ATZ.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button disabled={busy} onClick={() => void runSetup("bt")}>
            Auto-setup Bluetooth
          </Button>
          <Button disabled={busy} variant="ghost" onClick={() => void runSetup("usb")}>
            Auto-setup USB
          </Button>
          <Button
            disabled={busy}
            variant="ghost"
            onClick={() =>
              void (async () => {
                setBusy(true);
                setErr(null);
                setHints([]);
                try {
                  const d = await obdApi.discoverAdapters();
                  if (d.platform) setPlatform(d.platform);
                  const usb = d.usb.map((u) => u.path).join(", ") || "(none)";
                  const bt =
                    d.bluetooth
                      .slice(0, 8)
                      .map((b) => `${b.name || "?"} ${b.addr || b.port || ""}`.trim())
                      .join(" · ") || "(none)";
                  setDiscoverNote(`USB: ${usb}\nBluetooth: ${bt}`);
                  if ((!d.usb.length || !d.bluetooth.length) && d.hints?.length) {
                    setHints(d.hints);
                  }
                } catch (e) {
                  const { message, hints: h } = parseApiError(e);
                  setErr(message);
                  setHints(h);
                } finally {
                  setBusy(false);
                }
              })()
            }
          >
            Scan only
          </Button>
        </div>
        {discoverNote ? (
          <pre className="mt-3 whitespace-pre-wrap text-xs text-muted">{discoverNote}</pre>
        ) : null}
      </div>

      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {msg ? <p className="text-sm text-muted">{msg}</p> : null}
      {hints.length > 0 ? (
        <ConnectionHints
          title={err ? "Not found — common fixes" : "Connection tips"}
          hints={hints}
          platform={platform}
        />
      ) : null}

      {adapters.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted">
          No adapters yet — add one below or run <code className="text-fg">obdscan</code> config.
        </div>
      ) : (
        <ul className="space-y-2">
          {adapters.map((a, i) => {
            const aid = String(a.id ?? i);
            const alabel = String(a.label ?? a.name ?? aid);
            return (
              <li
                key={aid}
                className="rounded-xl border border-border bg-surface px-4 py-3 text-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <span className="font-medium">{alabel}</span>
                    {defaultId && aid === defaultId ? (
                      <span className="ml-2 text-xs text-accent">default</span>
                    ) : null}
                    <div className="mt-1 font-mono text-xs text-muted">
                      {String(a.port ?? "—")} @ {String(a.baud ?? "—")}
                      {a.transport ? ` · ${String(a.transport)}` : ""}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={aid === defaultId}
                      onClick={() =>
                        void obdApi
                          .setDefaultAdapter(aid)
                          .then(() => {
                            setMsg(`Default → ${aid}`);
                            return refresh();
                          })
                          .catch((e: unknown) => {
                            const { message, hints: h } = parseApiError(e);
                            setErr(message);
                            setHints(h);
                          })
                      }
                    >
                      Set default
                    </Button>
                    <Button
                      size="sm"
                      onClick={() =>
                        void obdApi
                          .connect({ adapter_id: aid })
                          .then(() => {
                            setMsg(`Connected with ${aid}`);
                            setHints([]);
                          })
                          .catch((e: unknown) => {
                            const { message, hints: h } = parseApiError(e);
                            setErr(message);
                            setHints(h);
                          })
                      }
                    >
                      Connect
                    </Button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="text-xs font-medium uppercase tracking-wide text-muted">
          Add / update adapter
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <Input placeholder="id" value={id} onChange={(e) => setId(e.target.value)} />
          <Input placeholder="label" value={label} onChange={(e) => setLabel(e.target.value)} />
          <Input
            placeholder="port (COM3 or /dev/rfcomm0)"
            value={port}
            onChange={(e) => setPort(e.target.value)}
          />
          <Input placeholder="baud" value={baud} onChange={(e) => setBaud(e.target.value)} />
        </div>
        <Button
          className="mt-3"
          onClick={() =>
            void (async () => {
              setErr(null);
              setHints([]);
              try {
                await obdApi.upsertAdapter({
                  id,
                  label: label || id,
                  port,
                  baud: Number(baud) || 38400,
                  make_default: adapters.length === 0,
                });
                setMsg(`Saved ${id}`);
                await refresh();
              } catch (e) {
                const { message, hints: h } = parseApiError(e);
                setErr(message);
                setHints(h);
              }
            })()
          }
        >
          Save adapter
        </Button>
      </div>
    </div>
  );
}
