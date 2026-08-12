import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type RepairOrder } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { customerLabel, formatStatus, vehicleLabel } from "@/lib/utils";

export function OrdersPage() {
  const [q, setQ] = useState("");
  const [orders, setOrders] = useState<RepairOrder[]>([]);
  const [error, setError] = useState("");

  async function load(query: string) {
    setError("");
    try {
      const rows = await api.listRos(query);
      setOrders(Array.isArray(rows) ? rows : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    }
  }

  useEffect(() => {
    void load("");
  }, []);

  useEffect(() => {
    const t = window.setTimeout(() => void load(q), 250);
    return () => window.clearTimeout(t);
  }, [q]);

  return (
    <div className="space-y-3">
      <Input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search name, VIN, plate, RO…"
      />
      {error ? <p className="text-sm text-danger">{error}</p> : null}
      {orders.length === 0 ? (
        <p className="text-sm text-muted">No matching orders.</p>
      ) : (
        <ul className="space-y-2">
          {orders.map((o) => (
            <li key={o.id}>
              <Link
                to={`/ro/${o.id}`}
                className="block rounded-xl border border-border bg-surface px-4 py-3"
              >
                <p className="font-medium">{customerLabel(o)}</p>
                <p className="text-sm text-muted">{vehicleLabel(o)}</p>
                <p className="mt-1 text-xs text-muted">
                  {o.id} · {formatStatus(o.status)}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
