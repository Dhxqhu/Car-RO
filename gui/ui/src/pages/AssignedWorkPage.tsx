import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { api, type AssignedBoard, type AssignedOrderSummary } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { formatDataSource, formatStatus } from "@/lib/utils";

function OrderCard({
  o,
  meId,
  meName,
}: {
  o: AssignedOrderSummary;
  meId?: string;
  meName?: string;
}) {
  return (
    <li className="rounded-xl border border-border bg-surface px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <Link to={`/ro/${o.id}`} className="font-medium text-accent hover:underline">
            {o.id}
          </Link>
          <div className="text-sm">{o.customer}</div>
          <div className="text-sm text-muted">{o.vehicle}</div>
        </div>
        <div className="text-right text-xs text-muted">
          <div className="font-medium text-fg/80">{formatStatus(o.status)}</div>
          {o.assigned_to_name ? <div>RO → {o.assigned_to_name}</div> : null}
          {o.current_tech_name ? (
            <div className="mt-0.5 font-medium text-accent">Now: {o.current_tech_name}</div>
          ) : null}
        </div>
      </div>
      {(o.work_items || []).length > 0 ? (
        <ul className="mt-2 space-y-1 border-t border-border/60 pt-2 text-xs text-muted">
          {o.work_items.map((w) => {
            const mine =
              (!!meId && (w.assigned_to_id === meId || w.notes_by === meName)) ||
              (!!meName &&
                (w.assigned_to_name === meName || w.notes_by === meName));
            const notesWho = w.notes_by || w.assigned_to_name;
            const concernWho = w.created_by
              ? w.created_by_role
                ? `${w.created_by} (${w.created_by_role})`
                : w.created_by
              : "";
            return (
              <li key={w.id} className={mine ? "text-fg" : undefined}>
                <span className="font-mono">{w.id}</span> · {formatStatus(w.status)}
                {notesWho ? ` · notes: ${notesWho}` : " · no notes yet"}
                {concernWho ? ` · concern: ${concernWho}` : ""}
                {w.concern ? ` — ${w.concern}` : ""}
              </li>
            );
          })}
        </ul>
      ) : null}
    </li>
  );
}

export function AssignedWorkPage() {
  const [board, setBoard] = useState<AssignedBoard | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setBusy(true);
    setErr("");
    try {
      setBoard(await api.assignedBoard());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load assigned work");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const t = window.setInterval(() => void refresh(), 30000);
    return () => window.clearInterval(t);
  }, [refresh]);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight">
            Assigned work
          </h1>
          <p className="mt-1 max-w-xl text-sm text-muted">
            Who is on what car right now, plus assigned queues. On an RO, use “Set as my current
            task” so the shop sees what you’re working on.
          </p>
        </div>
        <Button variant="secondary" disabled={busy} onClick={() => void refresh()}>
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      </div>

      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {board?.source ? (
        <p className="text-xs text-muted">Source: {formatDataSource(board.source)}</p>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
          Working now
        </h2>
        {(board?.now_working || []).length === 0 ? (
          <p className="text-sm text-muted">No tech has a current task set.</p>
        ) : (
          <ul className="space-y-2">
            {(board?.now_working || []).map((entry) => (
              <li
                key={`${entry.tech_id || entry.tech_name}-${entry.order.id}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-surface px-4 py-3 text-sm"
              >
                <div>
                  <span className="font-medium">
                    {entry.tech_name || entry.tech_id}
                    {entry.is_me ? " (you)" : ""}
                  </span>
                  <span className="text-muted"> → </span>
                  <Link
                    to={`/ro/${entry.order.id}`}
                    className="font-medium text-accent hover:underline"
                  >
                    {entry.order.vehicle}
                  </Link>
                  <span className="text-muted"> · {entry.order.customer}</span>
                </div>
                <div className="text-xs text-muted">{entry.order.id}</div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">My queue</h2>
        {(board?.mine || []).length === 0 ? (
          <p className="text-sm text-muted">Nothing assigned to you yet.</p>
        ) : (
          <ul className="space-y-3">
            {(board?.mine || []).map((o) => (
              <OrderCard
                key={o.id}
                o={o}
                meId={board?.tech_id}
                meName={board?.tech_name}
              />
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
          Other techs
        </h2>
        {(board?.by_tech || []).length === 0 ? (
          <p className="text-sm text-muted">No assignments for other technicians.</p>
        ) : (
          (board?.by_tech || []).map((bucket) => (
            <div key={bucket.id || bucket.name} className="space-y-2">
              <h3 className="text-sm font-medium">
                {bucket.name}
                {bucket.current ? (
                  <span className="ml-2 font-normal text-accent">
                    · on {bucket.current.vehicle || bucket.current.id}
                  </span>
                ) : null}
              </h3>
              <ul className="space-y-3">
                {bucket.orders.map((o) => (
                  <OrderCard key={`${bucket.name}-${o.id}`} o={o} />
                ))}
              </ul>
            </div>
          ))
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">
          Unassigned (open)
        </h2>
        {(board?.unassigned || []).length === 0 ? (
          <p className="text-sm text-muted">All open jobs have an assignee.</p>
        ) : (
          <ul className="space-y-3">
            {(board?.unassigned || []).map((o) => (
              <OrderCard key={o.id} o={o} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
