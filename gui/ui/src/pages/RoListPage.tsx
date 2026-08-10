import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { History, Plus, RefreshCw, Search, Server } from "lucide-react";
import { api, type RepairOrder, type Technician } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatStatus } from "@/lib/utils";

type Tab = "local" | "server";

export function RoListPage() {
  const nav = useNavigate();
  const [tab, setTab] = useState<Tab>("local");
  const [orders, setOrders] = useState<RepairOrder[]>([]);
  const [sources, setSources] = useState<Record<string, string>>({});
  const [q, setQ] = useState("");
  const [extName, setExtName] = useState("");
  const [extVin, setExtVin] = useState("");
  const [extPlate, setExtPlate] = useState("");
  const [extMake, setExtMake] = useState("");
  const [extQueried, setExtQueried] = useState(false);
  const [remoteEnabled, setRemoteEnabled] = useState(true);
  const [remoteOnly, setRemoteOnly] = useState(0);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [me, setMe] = useState<Technician | null>(null);
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "billed_out">("all");

  const visibleOrders = orders.filter((o) => {
    if (statusFilter === "billed_out") return o.status === "billed_out";
    if (statusFilter === "active") return o.status !== "billed_out";
    return true;
  });

  async function loadLocal(query = q) {
    setError("");
    setMsg("");
    try {
      const r = await api.listRos(query);
      setOrders(r.orders);
      setSources({});
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }

  async function loadServer() {
    setBusy(true);
    setError("");
    setMsg("");
    try {
      const r = await api.extendedSearch({
        q,
        name: extName,
        vin: extVin,
        plate: extPlate,
        make: extMake,
      });
      setOrders(r.orders);
      setSources(r.sources || {});
      setRemoteEnabled(r.remote_enabled);
      setRemoteOnly(r.remote_only || 0);
      setExtQueried(true);
      if (!r.remote_enabled) {
        setMsg("No server URL configured — results are local only. Set Server URL in Config.");
      } else if (r.orders.length === 0) {
        setMsg("No matches on this bay or the shop server.");
      } else if (r.remote_only) {
        setMsg(
          `Found ${r.orders.length} · ${r.remote_only} pulled from server archive into local cache.`,
        );
      } else {
        setMsg(`Found ${r.orders.length} (all already on this bay).`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Server search failed");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void loadLocal("");
    void api
      .whoami()
      .then((r) => setMe(r.technician))
      .catch(() => undefined);
    void api
      .getConfig()
      .then((c) => setRemoteEnabled(Boolean(c.server_url)))
      .catch(() => undefined);
  }, []);

  async function setCurrent(id: string, itemId?: string) {
    setBusy(true);
    setError("");
    try {
      await api.setCurrentTask(id, true, itemId);
      if (tab === "local") await loadLocal();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not set current work");
    } finally {
      setBusy(false);
    }
  }

  async function addToQueue(id: string, itemId?: string) {
    setBusy(true);
    setError("");
    try {
      await api.queueAction(id, "add", itemId);
      if (tab === "local") await loadLocal();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add to queue");
    } finally {
      setBusy(false);
    }
  }

  async function markBilledOut(id: string) {
    setBusy(true);
    setError("");
    try {
      await api.queueAction(id, "billed_out");
      if (tab === "local") await loadLocal();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not mark billed out");
    } finally {
      setBusy(false);
    }
  }

  async function markComplete(id: string) {
    setBusy(true);
    setError("");
    try {
      await api.queueAction(id, "complete");
      if (tab === "local") await loadLocal();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not mark done");
    } finally {
      setBusy(false);
    }
  }

  async function reopen(id: string) {
    setBusy(true);
    setError("");
    try {
      await api.queueAction(id, "reopen");
      if (tab === "local") await loadLocal();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not reopen");
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    setBusy(true);
    try {
      const o = await api.createRo();
      nav(`/ro/${o.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  async function sync() {
    setBusy(true);
    try {
      const r = await api.sync();
      setError("");
      setMsg(r.message || "");
      if (tab === "local") await loadLocal();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setBusy(false);
    }
  }

  function sourceBadge(id: string): string | null {
    if (tab !== "server") return null;
    const s = sources[id];
    if (s === "server") return "server";
    if (s === "both") return "local+server";
    if (s === "local") return "local";
    return null;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight">
            Repair orders
          </h1>
          <p className="mt-1 text-sm text-muted">
            Bay cache for active work · server archive for older billed-out history.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => nav("/history")} disabled={busy}>
            <History className="h-4 w-4" />
            History
          </Button>
          <Button variant="secondary" onClick={() => void sync()} disabled={busy}>
            <RefreshCw className="h-4 w-4" />
            Sync
          </Button>
          <Button onClick={() => void create()} disabled={busy}>
            <Plus className="h-4 w-4" />
            New RO
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        <Button
          type="button"
          size="sm"
          variant={tab === "local" ? "default" : "secondary"}
          onClick={() => {
            setTab("local");
            setMsg("");
            setError("");
            void loadLocal(q);
          }}
        >
          Local cache
        </Button>
        <Button
          type="button"
          size="sm"
          variant={tab === "server" ? "default" : "secondary"}
          onClick={() => {
            setTab("server");
            setMsg("");
            setError("");
            setOrders([]);
            setExtQueried(false);
          }}
        >
          <Server className="h-3.5 w-3.5" />
          Server search
        </Button>
      </div>

      {tab === "local" ? (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void loadLocal(q);
          }}
        >
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input
              className="pl-9"
              placeholder="Search name, VIN, plate, make…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <Button type="submit" variant="secondary">
            Search
          </Button>
        </form>
      ) : (
        <form
          className="space-y-3 rounded-2xl border border-border bg-surface p-4"
          onSubmit={(e) => {
            e.preventDefault();
            void loadServer();
          }}
        >
          <p className="text-xs text-muted">
            Searches this bay and the shop server. Hits only on the server are cached here so you
            can open them. Use this when a repeat customer’s older jobs were pruned locally.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="ext-q">Any text</Label>
              <Input
                id="ext-q"
                placeholder="Name, VIN, plate, complaint…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ext-name">Customer name</Label>
              <Input
                id="ext-name"
                value={extName}
                onChange={(e) => setExtName(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ext-vin">VIN</Label>
              <Input
                id="ext-vin"
                value={extVin}
                onChange={(e) => setExtVin(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ext-plate">Plate</Label>
              <Input
                id="ext-plate"
                value={extPlate}
                onChange={(e) => setExtPlate(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ext-make">Make</Label>
              <Input
                id="ext-make"
                value={extMake}
                onChange={(e) => setExtMake(e.target.value)}
              />
            </div>
          </div>
          <Button type="submit" disabled={busy}>
            <Search className="h-4 w-4" />
            Search archive
          </Button>
          {!remoteEnabled ? (
            <p className="text-xs text-danger">
              Server URL not set — configure it under Config to reach the archive.
            </p>
          ) : null}
        </form>
      )}

      {msg ? <p className="text-sm text-accent">{msg}</p> : null}
      {error ? <p className="text-sm text-danger">{error}</p> : null}

      {tab === "local" || extQueried ? (
        <div className="flex flex-wrap gap-1">
          {(
            [
              ["all", "All"],
              ["active", "Active"],
              ["billed_out", "Billed out"],
            ] as const
          ).map(([key, label]) => (
            <Button
              key={key}
              type="button"
              size="sm"
              variant={statusFilter === key ? "default" : "secondary"}
              onClick={() => setStatusFilter(key)}
            >
              {label}
            </Button>
          ))}
        </div>
      ) : null}

      <ul className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-surface">
        {tab === "server" && !extQueried ? (
          <li className="px-5 py-10 text-center text-sm text-muted">
            Enter a name, VIN, or other field and search the shop server archive.
          </li>
        ) : visibleOrders.length === 0 ? (
          <li className="px-5 py-10 text-center text-sm text-muted">
            {orders.length === 0
              ? tab === "local"
                ? "No repair orders yet."
                : "No matches."
              : "No repair orders match this filter."}
          </li>
        ) : (
          visibleOrders.map((o, i) => {
            const mineCurrent =
              !!me &&
              ((!!me.id && o.current_tech_id === me.id) ||
                (!!me.name && o.current_tech_name === me.name));
            const myItem =
              (o.work_items || []).find(
                (w) =>
                  !!me &&
                  ((!!me.id && w.assigned_to_id === me.id) ||
                    (!!me.name && w.assigned_to_name === me.name)),
              ) || null;
            const onMyQueue = !!myItem;
            const firstOpenItem =
              (o.work_items || []).find(
                (w) => w.status !== "done" && w.status !== "declined",
              ) ||
              (o.work_items || [])[0] ||
              null;
            const isClosed = o.status === "billed_out";
            const badge = sourceBadge(o.id);
            return (
              <li
                key={o.id}
                className="animate-[rowIn_0.3s_ease_both]"
                style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}
              >
                <div className="flex items-center justify-between gap-3 px-5 py-4 transition-colors hover:bg-border/25">
                  <Link to={`/ro/${o.id}`} className="min-w-0 flex-1">
                    <div className="font-medium">
                      {o.last_name || o.first_name
                        ? `${o.last_name}${o.last_name && o.first_name ? ", " : ""}${o.first_name}`
                        : "(no customer)"}
                      {badge ? (
                        <span className="ml-2 text-xs font-normal text-accent">[{badge}]</span>
                      ) : null}
                    </div>
                    <div className="text-sm text-muted">
                      {[o.year, o.make, o.model].filter(Boolean).join(" ") || "—"} · {o.id}
                      {o.current_tech_name ? (
                        <span className="text-accent">
                          {" "}
                          ·{" "}
                          {mineCurrent
                            ? `Your current work${o.current_item_id ? ` (${o.current_item_id})` : ""}`
                            : `${o.current_tech_name} working${
                                o.current_item_id ? ` ${o.current_item_id}` : ""
                              }`}
                        </span>
                      ) : onMyQueue && !isClosed ? (
                        <span className="text-accent">
                          {" "}
                          · On your queue{myItem ? ` (${myItem.id})` : ""}
                        </span>
                      ) : null}
                    </div>
                  </Link>
                  <div className="flex shrink-0 flex-col items-end gap-1 text-right text-xs text-muted">
                    <div className="font-medium text-accent">{formatStatus(o.status)}</div>
                    <div>{o.assigned_to_name || o.technician_name || "—"}</div>
                    {me && tab === "local" ? (
                      <div className="flex flex-col items-end gap-0.5">
                        {o.status === "done" ? (
                          <>
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              disabled={busy}
                              onClick={() => void reopen(o.id)}
                            >
                              Reopen
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              disabled={busy}
                              onClick={() => void markBilledOut(o.id)}
                            >
                              Mark billed out
                            </Button>
                          </>
                        ) : o.status === "billed_out" ? (
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            disabled={busy}
                            onClick={() => void reopen(o.id)}
                          >
                            Reopen
                          </Button>
                        ) : (
                          <>
                            {!onMyQueue ? (
                              <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                disabled={busy || !firstOpenItem}
                                onClick={() => void addToQueue(o.id, firstOpenItem?.id)}
                              >
                                Queue next item
                              </Button>
                            ) : null}
                            {!mineCurrent ? (
                              <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                disabled={busy || !firstOpenItem}
                                onClick={() => void setCurrent(o.id, firstOpenItem?.id)}
                              >
                                Work next item
                              </Button>
                            ) : (
                              <span className="text-[10px] font-semibold uppercase tracking-wide text-accent">
                                Current{o.current_item_id ? ` ${o.current_item_id}` : ""}
                              </span>
                            )}
                            {onMyQueue || mineCurrent ? (
                              <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                disabled={busy}
                                onClick={() => void markComplete(o.id)}
                              >
                                Mark done
                              </Button>
                            ) : null}
                          </>
                        )}
                      </div>
                    ) : null}
                  </div>
                </div>
              </li>
            );
          })
        )}
      </ul>
      {tab === "server" && remoteOnly > 0 ? (
        <p className="text-xs text-muted">
          Server-only hits are saved locally. Sync may prune older billed-out jobs again (Config →
          billed-out keep).
        </p>
      ) : null}
      <style>{`@keyframes rowIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}`}</style>
    </div>
  );
}
