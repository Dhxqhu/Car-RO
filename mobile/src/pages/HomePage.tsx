import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { NotifyButton } from "@/components/NotifyButton";
import { api, type RepairOrder } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { customerLabel, formatStatus, vehicleLabel } from "@/lib/utils";

type AssignedRow = {
  id: string;
  customer?: string;
  vehicle?: string;
  status?: string;
};

export function HomePage({
  id,
  name,
  role,
}: {
  id: string;
  name: string;
  role: string;
}) {
  const isTech = role === "technician";
  const [rows, setRows] = useState<AssignedRow[]>([]);
  const [unread, setUnread] = useState(0);
  const [shiftOn, setShiftOn] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setError("");
    try {
      if (isTech) {
        const [board, shift, msgs] = await Promise.all([
          api.assigned(id),
          api.myShift(id),
          api.messages(id),
        ]);
        setRows((board.mine || []) as AssignedRow[]);
        setShiftOn(Boolean(shift.shift && !shift.shift.ended_at));
        setUnread(msgs.unread || 0);
      } else {
        const [recent, msgs] = await Promise.all([api.recent(24 * 60), api.messages(id)]);
        setRows(
          (recent.orders || []).slice(0, 20).map((o: RepairOrder) => ({
            id: o.id,
            customer: customerLabel(o),
            vehicle: vehicleLabel(o),
            status: o.status,
          })),
        );
        setUnread(msgs.unread || 0);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load");
    }
  }

  useEffect(() => {
    void load();
  }, [id, isTech]);

  async function toggleShift() {
    setBusy(true);
    try {
      if (shiftOn) await api.endShift(id);
      else await api.startShift(id, name);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Shift failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <NotifyButton />
      {isTech ? (
        <div className="flex items-center justify-between rounded-xl border border-border bg-surface px-4 py-3">
          <div>
            <p className="text-sm font-medium">{shiftOn ? "On the clock" : "Clocked out"}</p>
            <p className="text-xs text-muted">Day clock only — not job timers</p>
          </div>
          <Button size="sm" variant={shiftOn ? "secondary" : "default"} disabled={busy} onClick={() => void toggleShift()}>
            {shiftOn ? "End day" : "Start day"}
          </Button>
        </div>
      ) : null}

      {unread > 0 ? (
        <Link
          to="/messages"
          className="block rounded-xl border border-amber-600/40 bg-amber-500/15 px-4 py-3 text-sm"
        >
          {unread} unread message{unread === 1 ? "" : "s"}
        </Link>
      ) : null}

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      <div>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
          {isTech ? "Assigned to you" : "Updated today"}
        </h2>
        {rows.length === 0 ? (
          <p className="text-sm text-muted">Nothing here yet.</p>
        ) : (
          <ul className="space-y-2">
            {rows.map((r) => (
              <li key={r.id}>
                <Link
                  to={`/ro/${r.id}`}
                  className="block rounded-xl border border-border bg-surface px-4 py-3"
                >
                  <p className="font-medium">{r.customer || r.id}</p>
                  <p className="text-sm text-muted">{r.vehicle}</p>
                  <p className="mt-1 text-xs text-muted">{formatStatus(r.status)}</p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
