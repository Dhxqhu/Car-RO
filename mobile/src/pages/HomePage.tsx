import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { NotifyButton } from "@/components/NotifyButton";
import { api, type AssignedJob, type RepairOrder, type WorkItem } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { customerLabel, formatStatus, formatWorkedMinutes, vehicleLabel } from "@/lib/utils";

function matchesMe(item: WorkItem, personId: string, personName: string): boolean {
  const mid = personId.trim().toLowerCase();
  const mname = personName.trim().toLowerCase();
  const tid = (item.timer_tech_id || "").trim().toLowerCase();
  const tname = (item.timer_tech_name || "").trim().toLowerCase();
  if (mid && tid && mid === tid) return true;
  if (mname && tname && mname === tname) return true;
  return false;
}

function itemOpen(item: WorkItem): boolean {
  const st = (item.status || "").toLowerCase();
  return st !== "done" && st !== "declined" && st !== "canceled";
}

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
  const [rows, setRows] = useState<AssignedJob[]>([]);
  const [recent, setRecent] = useState<RepairOrder[]>([]);
  const [unread, setUnread] = useState(0);
  const [shiftOn, setShiftOn] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [actingId, setActingId] = useState("");

  async function load() {
    setError("");
    try {
      if (isTech) {
        const [board, shift, msgs] = await Promise.all([
          api.assigned(id),
          api.myShift(id),
          api.messages(id),
        ]);
        setRows((board.mine || []) as AssignedJob[]);
        setShiftOn(Boolean(shift.shift && !shift.shift.ended_at));
        setUnread(msgs.unread || 0);
      } else {
        const [rec, msgs] = await Promise.all([api.recent(24 * 60), api.messages(id)]);
        setRecent((rec.orders || []).slice(0, 20));
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

  async function clockJob(roId: string, itemId: string, active: boolean) {
    setActingId(itemId);
    setError("");
    try {
      await api.setCurrentTask(roId, active, itemId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update job clock");
    } finally {
      setActingId("");
    }
  }

  return (
    <div className="space-y-4">
      <NotifyButton />
      {isTech ? (
        <div className="flex items-center justify-between rounded-xl border border-border bg-surface px-4 py-3">
          <div>
            <p className="text-sm font-medium">{shiftOn ? "On the clock" : "Clocked out"}</p>
            <p className="text-xs text-muted">Day clock. Use Clock in on a job below for the job timer.</p>
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

      {isTech ? (
        <div>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
            Assigned to you
            {rows.length ? ` · ${rows.length}` : ""}
          </h2>
          {rows.length === 0 ? (
            <p className="text-sm text-muted">Nothing here yet.</p>
          ) : (
            <ul className="space-y-2">
              {rows.map((r) => {
                const roId = r.id || r.ro_id || "";
                const items = (r.work_items || []).filter(itemOpen);
                return (
                  <li key={roId} className="rounded-xl border border-border bg-surface px-4 py-3">
                    <Link to={`/ro/${roId}`} className="block">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <p className="font-medium">{r.vehicle || roId}</p>
                        {r.waiter ? (
                          <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">
                            Waiter
                          </span>
                        ) : null}
                        {r.urgent ? (
                          <span className="rounded bg-danger/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-danger">
                            Urgent
                          </span>
                        ) : null}
                      </div>
                      <p className="text-sm text-muted">
                        {r.customer}
                        {r.status ? ` · ${formatStatus(r.status)}` : ""}
                      </p>
                    </Link>
                    {items.length === 0 ? (
                      <p className="mt-2 text-xs text-muted">No open work items.</p>
                    ) : (
                      <ul className="mt-2 ml-1 space-y-2 border-l-2 border-border pl-3">
                        {items.map((w) => {
                          const mine = Boolean(w.timer_started_at) && matchesMe(w, id, name);
                          const otherOn = Boolean(w.timer_started_at) && !mine;
                          return (
                            <li key={w.id} className="flex items-start justify-between gap-2">
                              <div className="min-w-0">
                                <p className="text-sm font-medium">{w.concern || w.id}</p>
                                <p className="text-xs text-muted">
                                  {formatStatus(w.status)}
                                  {w.worked_minutes ? ` · ${formatWorkedMinutes(w.worked_minutes)}` : ""}
                                  {mine ? " · timer on" : ""}
                                  {otherOn && w.timer_tech_name ? ` · ${w.timer_tech_name}` : ""}
                                </p>
                              </div>
                              {mine ? (
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  disabled={actingId === w.id || busy}
                                  onClick={() => void clockJob(roId, w.id, false)}
                                >
                                  Clock out
                                </Button>
                              ) : otherOn ? null : (
                                <Button
                                  size="sm"
                                  disabled={actingId === w.id || busy}
                                  onClick={() => void clockJob(roId, w.id, true)}
                                >
                                  Clock in
                                </Button>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : (
        <div>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
            Updated today
          </h2>
          {recent.length === 0 ? (
            <p className="text-sm text-muted">Nothing here yet.</p>
          ) : (
            <ul className="space-y-2">
              {recent.map((o) => (
                <li key={o.id}>
                  <Link
                    to={`/ro/${o.id}`}
                    className="block rounded-xl border border-border bg-surface px-4 py-3"
                  >
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <p className="font-medium">{vehicleLabel(o)}</p>
                      {o.waiter ? (
                        <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">
                          Waiter
                        </span>
                      ) : null}
                      {o.urgent ? (
                        <span className="rounded bg-danger/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-danger">
                          Urgent
                        </span>
                      ) : null}
                    </div>
                    <p className="text-sm text-muted">{customerLabel(o)}</p>
                    <p className="mt-1 text-xs text-muted">
                      {o.id} · {formatStatus(o.status)}
                    </p>
                    {(o.work_items || []).length ? (
                      <ul className="mt-2 ml-1 space-y-1 border-l-2 border-border pl-3 text-xs text-muted">
                        {(o.work_items || []).map((w) => (
                          <li key={w.id}>
                            {w.concern || w.id}
                            {w.status ? ` · ${formatStatus(w.status)}` : ""}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
