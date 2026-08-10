import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { History, Plus, RefreshCw, Search } from "lucide-react";
import { api, type RepairOrder, type Technician } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatStatus } from "@/lib/utils";

export function RoListPage() {
  const nav = useNavigate();
  const [orders, setOrders] = useState<RepairOrder[]>([]);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [me, setMe] = useState<Technician | null>(null);

  async function load(query = q) {
    setError("");
    try {
      const r = await api.listRos(query);
      setOrders(r.orders);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }

  useEffect(() => {
    void load("");
    void api
      .whoami()
      .then((r) => setMe(r.technician))
      .catch(() => undefined);
  }, []);

  async function setCurrent(id: string) {
    setBusy(true);
    setError("");
    try {
      await api.setCurrentTask(id, true);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not set current task");
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
      setError(r.message || "");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight">
            Repair orders
          </h1>
          <p className="mt-1 text-sm text-muted">Bay cache — sync to push/pull the shop server.</p>
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

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void load(q);
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

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      <ul className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-surface">
        {orders.length === 0 ? (
          <li className="px-5 py-10 text-center text-sm text-muted">No repair orders yet.</li>
        ) : (
          orders.map((o, i) => {
            const mineCurrent =
              !!me &&
              ((!!me.id && o.current_tech_id === me.id) ||
                (!!me.name && o.current_tech_name === me.name));
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
                    </div>
                    <div className="text-sm text-muted">
                      {[o.year, o.make, o.model].filter(Boolean).join(" ") || "—"} · {o.id}
                      {o.current_tech_name ? (
                        <span className="text-accent">
                          {" "}
                          · {mineCurrent ? "Your current task" : `${o.current_tech_name} working`}
                        </span>
                      ) : null}
                    </div>
                  </Link>
                  <div className="flex shrink-0 flex-col items-end gap-1 text-right text-xs text-muted">
                    <div className="font-medium text-accent">{formatStatus(o.status)}</div>
                    <div>{o.assigned_to_name || o.technician_name || "—"}</div>
                    {me && !mineCurrent ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => void setCurrent(o.id)}
                      >
                        Select as current task
                      </Button>
                    ) : null}
                    {mineCurrent ? (
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-accent">
                        Current
                      </span>
                    ) : null}
                  </div>
                </div>
              </li>
            );
          })
        )}
      </ul>
      <style>{`@keyframes rowIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}`}</style>
    </div>
  );
}
