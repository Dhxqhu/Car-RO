import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Search, UserRound } from "lucide-react";
import { api, type RepairOrder } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * New RO: blank, or prefill customer + vehicle from a prior job.
 */
export function NewRoDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const nav = useNavigate();
  const [vin, setVin] = useState("");
  const [name, setName] = useState("");
  const [hits, setHits] = useState<RepairOrder[]>([]);
  const [matchedBy, setMatchedBy] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [searched, setSearched] = useState(false);

  if (!open) return null;

  function reset() {
    setVin("");
    setName("");
    setHits([]);
    setMatchedBy("");
    setErr("");
    setNote("");
    setSearched(false);
    setBusy(false);
  }

  function close() {
    reset();
    onClose();
  }

  async function blank() {
    setBusy(true);
    setErr("");
    try {
      const o = await api.createRo();
      setBusy(false);
      close();
      nav(`/ro/${o.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not create RO");
      setBusy(false);
    }
  }

  async function lookup() {
    if (!vin.trim() && !name.trim()) {
      setErr("Enter a VIN and/or customer name or phone");
      return;
    }
    setBusy(true);
    setErr("");
    setNote("");
    try {
      const r = await api.history(vin, name, undefined, true);
      setHits(r.orders || []);
      setMatchedBy(r.matched_by || "");
      setSearched(true);
      if (r.note) setNote(r.note);
      else if (r.remote_enabled && r.remote_ok === false) {
        setNote("Shop server unreachable — showing jobs already on this desk.");
      }
      if (!(r.orders || []).length) {
        setErr(
          r.note ||
            "No prior jobs found — try another VIN, name, or phone (or Blank RO).",
        );
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Lookup failed");
      setHits([]);
    } finally {
      setBusy(false);
    }
  }

  async function usePrior(priorId: string) {
    setBusy(true);
    setErr("");
    try {
      const o = await api.historyNewFrom(priorId);
      setBusy(false);
      close();
      nav(`/ro/${o.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not create RO");
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <button
        type="button"
        className="absolute inset-0 cursor-default"
        aria-label="Close"
        onClick={close}
      />
      <div className="relative z-10 w-full max-w-lg space-y-4 rounded-2xl border border-border bg-surface p-5 shadow-lg">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">New repair order</h2>
          <p className="mt-1 text-sm text-muted">
            Start blank, or pull the latest customer and vehicle info for a car.
            Same vehicle shows once even if it has many old repair orders.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={busy} onClick={() => void blank()}>
            <Plus className="h-4 w-4" />
            Blank RO
          </Button>
        </div>

        <div className="space-y-3 border-t border-border pt-4">
          <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-accent">
            <UserRound className="h-3.5 w-3.5" />
            Returning customer
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="newro-vin">VIN</Label>
              <Input
                id="newro-vin"
                placeholder="Full or last 8+"
                value={vin}
                onChange={(e) => setVin(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void lookup();
                }}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="newro-name">Name or phone</Label>
              <Input
                id="newro-name"
                placeholder="Last name or phone"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void lookup();
                }}
              />
            </div>
          </div>
          <Button
            type="button"
            variant="secondary"
            disabled={busy}
            onClick={() => void lookup()}
          >
            <Search className="h-4 w-4" />
            Find car
          </Button>

          {matchedBy ? (
            <p className="text-xs text-muted">Matched by {matchedBy.replace(/_/g, " ")}</p>
          ) : null}
          {note ? <p className="text-xs text-muted">{note}</p> : null}

          {searched && hits.length ? (
            <ul className="max-h-56 space-y-2 overflow-y-auto">
              {hits.slice(0, 20).map((o) => (
                <li
                  key={o.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border/70 px-3 py-2 text-sm"
                >
                  <div className="min-w-0">
                    <div className="font-medium">
                      {o.last_name || o.first_name
                        ? `${o.last_name || ""}${o.last_name && o.first_name ? ", " : ""}${o.first_name || ""}`
                        : "(no customer)"}
                      {o.phone ? (
                        <span className="ml-2 font-normal text-muted">{o.phone}</span>
                      ) : null}
                    </div>
                    <div className="truncate text-xs text-muted">
                      {[o.year, o.make, o.model].filter(Boolean).join(" ") || "—"}
                      {o.vin ? ` · ${o.vin}` : ""}
                      {o.plate ? ` · ${o.plate}` : ""}
                      {" · last visit "}
                      {o.id}
                    </div>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    disabled={busy}
                    onClick={() => void usePrior(o.id)}
                  >
                    Use
                  </Button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        {err ? <p className="text-sm text-danger">{err}</p> : null}

        <div className="flex justify-end">
          <Button type="button" variant="ghost" disabled={busy} onClick={close}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}
