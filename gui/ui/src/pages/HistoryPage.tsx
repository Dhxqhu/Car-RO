import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { FileText, History, Plus, Search } from "lucide-react";
import { api, type RepairOrder } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function matchLabel(matchedBy: string, remote: boolean): string {
  const base =
    matchedBy === "vin_exact"
      ? "Exact VIN"
      : matchedBy === "vin_partial"
        ? "Partial VIN"
        : matchedBy === "name"
          ? "Customer name"
          : "No match";
  return remote ? `${base} · includes server archive` : `${base} · local only`;
}

export function HistoryPage() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [vin, setVin] = useState(params.get("vin") || "");
  const [name, setName] = useState(params.get("name") || "");
  const [excludeId] = useState(params.get("exclude") || "");
  const [orders, setOrders] = useState<RepairOrder[]>([]);
  const [matchedBy, setMatchedBy] = useState("");
  const [remote, setRemote] = useState(false);
  const [searched, setSearched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  async function lookup() {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const r = await api.history(vin, name, excludeId || undefined);
      setOrders(r.orders);
      setMatchedBy(r.matched_by);
      setRemote(r.remote_enabled);
      setSearched(true);
      if (r.orders.length === 0) {
        setMsg(
          r.remote_enabled
            ? "No prior repair history on this machine or the server."
            : "No prior repair history locally. Set a Server URL in Settings to search the archive.",
        );
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Lookup failed");
    } finally {
      setBusy(false);
    }
  }

  async function pack(kind: "text" | "pdf" | "pdf-lite") {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const r = await api.historyPack(vin, name, kind, excludeId || undefined);
      const pages =
        r.estimated_pages != null ? ` (~${r.estimated_pages} pages)` : "";
      setMsg(`Wrote ${r.kind} pack (${r.count} job(s))${pages} → ${r.path}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Pack failed");
    } finally {
      setBusy(false);
    }
  }

  async function newFrom(priorId: string) {
    setBusy(true);
    setErr("");
    try {
      const o = await api.historyNewFrom(priorId);
      nav(`/ro/${o.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Create failed");
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight">
          Vehicle history
        </h1>
        <p className="mt-1 text-sm text-muted">
          VIN-first lookup against local cache and the shop server (when configured). Name
          is used only if VIN is blank or finds nothing.
        </p>
      </div>

      <form
        className="space-y-4 rounded-2xl border border-border bg-surface p-5"
        onSubmit={(e) => {
          e.preventDefault();
          void lookup();
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="hist-vin">VIN</Label>
            <Input
              id="hist-vin"
              placeholder="Full VIN or last 8+ characters"
              value={vin}
              onChange={(e) => setVin(e.target.value)}
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="hist-name">Customer name</Label>
            <Input
              id="hist-name"
              placeholder="Fallback if no VIN / no VIN hits"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={busy || (!vin.trim() && !name.trim())}>
            <Search className="h-4 w-4" />
            {busy ? "Looking up…" : "Lookup"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={busy || orders.length === 0}
            onClick={() => void pack("text")}
          >
            <FileText className="h-4 w-4" />
            Text pack
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={busy || orders.length === 0}
            onClick={() => void pack("pdf-lite")}
          >
            PDF (no photos)
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={busy || orders.length === 0}
            onClick={() => {
              if (
                orders.length > 0 &&
                !confirm(
                  "Full PDF includes photos and can be long. Continue?",
                )
              ) {
                return;
              }
              void pack("pdf");
            }}
          >
            PDF + photos
          </Button>
        </div>
      </form>

      {msg ? <p className="text-sm text-accent">{msg}</p> : null}
      {err ? <p className="text-sm text-danger">{err}</p> : null}

      {searched && orders.length > 0 ? (
        <div className="space-y-3">
          <p className="flex items-center gap-2 text-sm text-muted">
            <History className="h-4 w-4 text-accent" />
            {orders.length} prior job(s) · {matchLabel(matchedBy, remote)}
          </p>
          <ul className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-surface">
            {orders.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                <div className="min-w-0 flex-1">
                  <div className="font-medium">
                    {o.last_name || o.first_name
                      ? `${o.last_name}${o.last_name && o.first_name ? ", " : ""}${o.first_name}`
                      : "(no customer)"}
                  </div>
                  <div className="text-sm text-muted">
                    {[o.year, o.make, o.model].filter(Boolean).join(" ") || "—"} ·{" "}
                    {o.vin || "no VIN"} · {o.id}
                  </div>
                  {o.complaint ? (
                    <p className="mt-1 line-clamp-2 text-sm text-muted">{o.complaint}</p>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Link
                    to={`/ro/${o.id}`}
                    className="inline-flex h-8 items-center justify-center rounded-lg border border-border bg-surface px-3 text-xs font-medium hover:bg-border/40"
                  >
                    Open
                  </Link>
                  <Button
                    size="sm"
                    disabled={busy}
                    onClick={() => void newFrom(o.id)}
                  >
                    <Plus className="h-3.5 w-3.5" />
                    New from vehicle
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
