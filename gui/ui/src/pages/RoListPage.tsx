import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, RefreshCw, Search } from "lucide-react";
import { api, type RepairOrder } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function RoListPage() {
  const nav = useNavigate();
  const [orders, setOrders] = useState<RepairOrder[]>([]);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

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
  }, []);

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
          orders.map((o, i) => (
            <li
              key={o.id}
              className="animate-[rowIn_0.3s_ease_both]"
              style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}
            >
              <Link
                to={`/ro/${o.id}`}
                className="flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-border/25"
              >
                <div>
                  <div className="font-medium">
                    {o.last_name || o.first_name
                      ? `${o.last_name}${o.last_name && o.first_name ? ", " : ""}${o.first_name}`
                      : "(no customer)"}
                  </div>
                  <div className="text-sm text-muted">
                    {[o.year, o.make, o.model].filter(Boolean).join(" ") || "—"} · {o.id}
                  </div>
                </div>
                <div className="text-right text-xs text-muted">
                  <div className="font-semibold uppercase tracking-wide text-accent">{o.status}</div>
                  <div>{o.technician_name || "—"}</div>
                </div>
              </Link>
            </li>
          ))
        )}
      </ul>
      <style>{`@keyframes rowIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}`}</style>
    </div>
  );
}
