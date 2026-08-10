import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { api, type AssignedBoard, type AssignedOrderSummary } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { formatDataSource, formatShopTime, formatStatus } from "@/lib/utils";

type QueueAct =
  | "add"
  | "remove"
  | "complete"
  | "billed_out"
  | "waiting_parts"
  | "waiting_customer";

function timingLine(o: AssignedOrderSummary): string {
  const bits: string[] = [];
  if (o.waiting_since) bits.push(`waiting since ${formatShopTime(o.waiting_since)}`);
  if (o.started_at) bits.push(`started ${formatShopTime(o.started_at)}`);
  if (o.done_at) bits.push(`done ${formatShopTime(o.done_at)}`);
  if (o.billed_out_at) bits.push(`billed ${formatShopTime(o.billed_out_at)}`);
  return bits.join(" · ");
}

function OrderCard({
  o,
  meId,
  meName,
  actions,
}: {
  o: AssignedOrderSummary;
  meId?: string;
  meName?: string;
  actions?: ReactNode;
}) {
  const timing = timingLine(o);
  return (
    <li className="rounded-xl border border-border bg-surface px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <Link to={`/ro/${o.id}`} className="font-medium text-accent hover:underline">
            {o.id}
          </Link>
          <div className="text-sm">{o.customer}</div>
          <div className="text-sm text-muted">{o.vehicle}</div>
          {timing ? <div className="mt-1 text-xs text-muted">{timing}</div> : null}
        </div>
        <div className="text-right text-xs text-muted">
          <div className="font-medium text-fg/80">{formatStatus(o.status)}</div>
          {o.assigned_to_name ? <div>Queue → {o.assigned_to_name}</div> : null}
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
            return (
              <li key={w.id} className={mine ? "text-fg" : undefined}>
                <span className="font-mono">{w.id}</span> · {formatStatus(w.status)}
                {notesWho ? ` · notes: ${notesWho}` : ""}
                {w.concern ? ` — ${w.concern}` : ""}
              </li>
            );
          })}
        </ul>
      ) : null}
      {actions ? <div className="mt-3 flex flex-wrap gap-2">{actions}</div> : null}
    </li>
  );
}

export function AssignedWorkPage() {
  const [board, setBoard] = useState<AssignedBoard | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [actingId, setActingId] = useState<string | null>(null);

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

  async function runQueue(id: string, action: QueueAct) {
    setActingId(id);
    setErr("");
    try {
      await api.queueAction(id, action);
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Queue update failed");
    } finally {
      setActingId(null);
    }
  }

  async function runCurrent(id: string, active: boolean) {
    setActingId(id);
    setErr("");
    try {
      await api.setCurrentTask(id, active);
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not update current task");
    } finally {
      setActingId(null);
    }
  }

  const meId = board?.tech_id;
  const meName = board?.tech_name;
  const myCurrentId = board?.my_current?.id;
  const loggedIn = !!(meId || meName);

  function btn(id: string, label: string, action: () => void, variant: "default" | "secondary" | "ghost" = "secondary") {
    return (
      <Button
        type="button"
        size="sm"
        variant={variant}
        disabled={actingId === id || busy}
        onClick={action}
      >
        {label}
      </Button>
    );
  }

  function mineActions(o: AssignedOrderSummary) {
    const isCurrent = o.id === myCurrentId;
    return (
      <>
        {!isCurrent
          ? btn(o.id, "Start as current", () => void runCurrent(o.id, true))
          : btn(o.id, "Clear current", () => void runCurrent(o.id, false))}
        {btn(o.id, "Waiting on parts", () => void runQueue(o.id, "waiting_parts"))}
        {btn(o.id, "Waiting on customer", () => void runQueue(o.id, "waiting_customer"))}
        {btn(o.id, "Mark done", () => void runQueue(o.id, "complete"), "default")}
        {btn(o.id, "Remove from queue", () => void runQueue(o.id, "remove"), "ghost")}
      </>
    );
  }

  function waitingActions(o: AssignedOrderSummary) {
    return (
      <>
        {btn(o.id, "Resume as current", () => void runCurrent(o.id, true))}
        {btn(o.id, "Mark done", () => void runQueue(o.id, "complete"))}
      </>
    );
  }

  function readyActions(o: AssignedOrderSummary) {
    return btn(o.id, "Mark billed out", () => void runQueue(o.id, "billed_out"), "default");
  }

  function section(
    title: string,
    items: AssignedOrderSummary[] | undefined,
    empty: string,
    actionFor?: (o: AssignedOrderSummary) => ReactNode,
    accent = true,
  ) {
    const list = items || [];
    return (
      <section className="space-y-3">
        <h2
          className={`text-xs font-semibold uppercase tracking-wide ${
            accent ? "text-accent" : "text-muted"
          }`}
        >
          {title}
          {list.length ? ` · ${list.length}` : ""}
        </h2>
        {list.length === 0 ? (
          <p className="text-sm text-muted">{empty}</p>
        ) : (
          <ul className="space-y-3">
            {list.map((o) => (
              <OrderCard
                key={o.id}
                o={o}
                meId={meId}
                meName={meName}
                actions={actionFor?.(o)}
              />
            ))}
          </ul>
        )}
      </section>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight">
            Assigned work
          </h1>
          <p className="mt-1 max-w-xl text-sm text-muted">
            Planned queue, waiting parks, done vs billed out. Shop timing stays here — never on the
            customer PDF.
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
                <div className="flex flex-wrap items-center gap-2">
                  <div className="text-xs text-muted">{entry.order.id}</div>
                  {entry.is_me ? (
                    <>
                      {btn(entry.order.id, "Waiting on parts", () =>
                        void runQueue(entry.order.id, "waiting_parts"),
                      )}
                      {btn(entry.order.id, "Mark done", () =>
                        void runQueue(entry.order.id, "complete"),
                      )}
                      {btn(
                        entry.order.id,
                        "Clear current",
                        () => void runCurrent(entry.order.id, false),
                        "ghost",
                      )}
                    </>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {section(
        "My queue (planned)",
        board?.mine,
        "Nothing in your active queue. Add from Unassigned or Orders.",
        loggedIn ? mineActions : undefined,
      )}

      {section(
        "Waiting on parts",
        board?.waiting_parts,
        "No jobs waiting on parts.",
        loggedIn ? waitingActions : undefined,
      )}

      {section(
        "Waiting on customer",
        board?.waiting_customer,
        "No jobs waiting on customer verification.",
        loggedIn ? waitingActions : undefined,
      )}

      {section(
        "Ready to bill (done)",
        board?.ready_to_bill,
        "No finished jobs waiting to bill out.",
        loggedIn ? readyActions : undefined,
      )}

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

      {section(
        "Unassigned (open)",
        board?.unassigned,
        "All open jobs have an assignee.",
        loggedIn
          ? (o) => (
              <>
                {btn(o.id, "Add to my queue", () => void runQueue(o.id, "add"))}
                {btn(o.id, "Start as current", () => void runCurrent(o.id, true), "default")}
              </>
            )
          : undefined,
        false,
      )}
    </div>
  );
}
