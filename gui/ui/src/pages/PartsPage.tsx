import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type PartsSheetRow } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatShopTime } from "@/lib/utils";

const PART_STATUSES = [
  { value: "", label: "Open (hide received)" },
  { value: "new_request", label: "New request" },
  { value: "ordered", label: "Ordered" },
  { value: "received", label: "Received" },
  { value: "received_wrong", label: "Received wrong" },
] as const;

function statusLabel(s: string): string {
  const hit = PART_STATUSES.find((p) => p.value === s);
  return hit?.label || s.replace(/_/g, " ");
}

export function PartsPage() {
  const [rows, setRows] = useState<PartsSheetRow[]>([]);
  const [status, setStatus] = useState("");
  const [manufacturer, setManufacturer] = useState("");
  const [partNumber, setPartNumber] = useState("");
  const [roId, setRoId] = useState("");
  const [includeReceived, setIncludeReceived] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    setBusy(true);
    setErr("");
    try {
      const r = await api.listParts({
        status: status || undefined,
        manufacturer: manufacturer || undefined,
        part_number: partNumber || undefined,
        ro_id: roId || undefined,
        include_received: includeReceived || status === "received",
      });
      setRows(r.parts || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load parts");
    } finally {
      setBusy(false);
    }
  }, [status, manufacturer, partNumber, roId, includeReceived]);

  useEffect(() => {
    void load();
  }, [load]);

  async function setStatusFor(row: PartsSheetRow, next: string) {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      let wrong_note = "";
      if (next === "received_wrong") {
        wrong_note =
          window.prompt("What was wrong with the part?", "Received wrong part") ||
          "Received wrong part";
      }
      await api.patchPart(row.ro_id, row.work_item_id, row.part_id, {
        status: next,
        wrong_note,
      });
      setMsg(`${row.part_id} → ${statusLabel(next)}`);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Update failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold">
          Parts order sheet
        </h1>
        <p className="mt-1 text-sm text-muted">
          Compiled from work-item parts on local ROs. Received lines drop from the bay cache after
          the keep window (default 24h) once synced.
        </p>
      </div>

      <section className="grid gap-3 rounded-2xl border border-border bg-surface p-4 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <Label>Status</Label>
          <select
            className="mt-1 flex h-10 w-full rounded-lg border border-border bg-bg px-3 text-sm"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            {PART_STATUSES.map((s) => (
              <option key={s.label} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label>Manufacturer contains</Label>
          <Input
            className="mt-1"
            value={manufacturer}
            onChange={(e) => setManufacturer(e.target.value)}
            placeholder="Ford"
          />
        </div>
        <div>
          <Label>Part number contains</Label>
          <Input
            className="mt-1"
            value={partNumber}
            onChange={(e) => setPartNumber(e.target.value)}
          />
        </div>
        <div>
          <Label>RO id</Label>
          <Input className="mt-1" value={roId} onChange={(e) => setRoId(e.target.value)} />
        </div>
        <div className="flex items-end gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={includeReceived}
              onChange={(e) => setIncludeReceived(e.target.checked)}
            />
            Include received
          </label>
          <Button type="button" variant="secondary" disabled={busy} onClick={() => void load()}>
            Refresh
          </Button>
        </div>
      </section>

      {err ? <p className="text-sm text-red-600 dark:text-red-400">{err}</p> : null}
      {msg ? <p className="text-sm text-muted">{msg}</p> : null}

      {!rows.length ? (
        <p className="text-sm text-muted">{busy ? "Loading…" : "No matching parts."}</p>
      ) : (
        <ul className="space-y-3">
          {rows.map((row) => (
            <li
              key={`${row.ro_id}-${row.work_item_id}-${row.part_id}`}
              className="rounded-2xl border border-border bg-surface p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-medium">
                    {row.description || "—"}{" "}
                    <span className="font-mono text-xs text-muted">
                      {row.part_id} · {statusLabel(row.status)}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-muted">
                    {row.manufacturer || row.make || "—"}
                    {row.part_number ? ` · PN ${row.part_number}` : ""}
                    {" · "}
                    <Link className="text-accent hover:underline" to={`/ro/${row.ro_id}`}>
                      {row.ro_id}
                    </Link>
                    {row.work_item_id ? ` / ${row.work_item_id}` : ""}
                    {row.vehicle ? ` · ${row.vehicle}` : ""}
                    {row.customer ? ` · ${row.customer}` : ""}
                  </p>
                  {row.concern ? (
                    <p className="mt-1 text-xs text-muted">{row.concern}</p>
                  ) : null}
                  {row.wrong_note ? (
                    <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
                      Wrong: {row.wrong_note}
                    </p>
                  ) : null}
                  <p className="mt-1 text-xs text-muted">
                    {row.requested_at ? `asked ${formatShopTime(row.requested_at)}` : ""}
                    {row.ordered_at ? ` · ordered ${formatShopTime(row.ordered_at)}` : ""}
                    {row.received_at ? ` · received ${formatShopTime(row.received_at)}` : ""}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {row.status === "new_request" ? (
                    <Button
                      type="button"
                      size="sm"
                      disabled={busy}
                      onClick={() => void setStatusFor(row, "ordered")}
                    >
                      Mark ordered
                    </Button>
                  ) : null}
                  {row.status === "ordered" || row.status === "new_request" ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={busy}
                      onClick={() => void setStatusFor(row, "received")}
                    >
                      Received
                    </Button>
                  ) : null}
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    onClick={() => void setStatusFor(row, "received_wrong")}
                  >
                    Wrong part
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
