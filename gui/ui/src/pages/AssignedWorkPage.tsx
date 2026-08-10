import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import {
  api,
  type AssignedBoard,
  type AssignedJobSummary,
  type AssignedOrderSummary,
  type FoundIssueSummary,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  formatDataSource,
  formatDurationMinutes,
  formatShopTime,
  formatStatus,
  formatWorkedMinutes,
} from "@/lib/utils";

type QueueAct =
  | "add"
  | "remove"
  | "complete"
  | "complete_item"
  | "billed_out"
  | "reopen"
  | "waiting_parts"
  | "request_parts"
  | "item_waiting_parts"
  | "waiting_customer"
  | "request_approval"
  | "item_waiting_customer";

function jobTiming(j: AssignedJobSummary): string {
  const bits: string[] = [];
  if (j.worked_first_at) bits.push(`first ${formatShopTime(j.worked_first_at)}`);
  if (j.worked_last_at) bits.push(`last ${formatShopTime(j.worked_last_at)}`);
  if (j.timer_started_at) bits.push("timer on");
  return bits.join(" · ");
}

function jobWaitAge(j: AssignedJobSummary): string {
  const st = (j.item_status || "").toLowerCase();
  if (st === "waiting_parts" || st === "waiting_customer") {
    const live = Number(j.stage_live_minutes) || 0;
    if (live > 0) return `waiting ${formatDurationMinutes(live)}`;
  }
  const parts = Number(j.waiting_parts_minutes) || 0;
  const cust = Number(j.waiting_customer_minutes) || 0;
  const bits: string[] = [];
  if (parts > 0) bits.push(`parts wait ${formatDurationMinutes(parts)}`);
  if (cust > 0) bits.push(`customer wait ${formatDurationMinutes(cust)}`);
  return bits.join(" · ");
}

function roTiming(o: AssignedOrderSummary): string {
  const bits: string[] = [];
  if (o.parts_requested_at) {
    bits.push(
      `parts ${formatShopTime(o.parts_requested_at)}${
        o.parts_requested_by ? ` (${o.parts_requested_by})` : ""
      }`,
    );
  }
  if (o.approval_requested_at) {
    bits.push(
      `approval ${formatShopTime(o.approval_requested_at)}${
        o.approval_requested_by ? ` (${o.approval_requested_by})` : ""
      }`,
    );
  }
  if (o.done_at) bits.push(`done ${formatShopTime(o.done_at)}`);
  if (o.billed_out_at) bits.push(`billed ${formatShopTime(o.billed_out_at)}`);
  if (o.worked_minutes) bits.push(`worked ${formatWorkedMinutes(o.worked_minutes)}`);
  return bits.join(" · ");
}

function JobCard({
  j,
  actions,
}: {
  j: AssignedJobSummary;
  actions?: ReactNode;
}) {
  const timing = jobTiming(j);
  const waitAge = jobWaitAge(j);
  const worked = Number(j.worked_minutes) || 0;
  const req = j.next_day_request;
  return (
    <li className="rounded-xl border border-border bg-surface px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap gap-1.5">
            {j.waiter ? (
              <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">
                Waiter
              </span>
            ) : null}
            {j.urgent ? (
              <span className="rounded bg-danger/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-danger">
                Urgent
              </span>
            ) : null}
            {j.queue_lane && j.queue_lane !== "daily" ? (
              <span className="rounded bg-border/80 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted">
                {j.queue_lane === "next_day" ? "Next day" : "Long-term"}
              </span>
            ) : null}
            {j.pending_queue_lane ? (
              <span className="rounded bg-border/80 px-1.5 py-0.5 text-[10px] font-medium text-muted">
                Push {j.pending_queue_lane === "next_day" ? "next day" : j.pending_queue_lane} on clock-out
              </span>
            ) : null}
            {req?.status === "pending" ? (
              <span className="rounded bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                Next-day requested{req.read_at ? "" : " · unread"}
              </span>
            ) : null}
          </div>
          <Link
            to={`/ro/${j.ro_id}`}
            className="font-medium text-accent hover:underline"
          >
            {j.item_id}
            <span className="font-normal text-muted"> · {j.ro_id}</span>
          </Link>
          <div className="mt-0.5 text-sm">{j.concern || "(no concern)"}</div>
          <div className="text-sm text-muted">
            {j.vehicle} · {j.customer}
          </div>
          <div className="mt-1 text-sm font-medium tabular-nums">
            Worked {formatWorkedMinutes(worked)}
          </div>
          {Number(j.downtime_minutes) > 0 ? (
            <div className="text-xs text-muted">
              Downtime {formatDurationMinutes(j.downtime_minutes)}
            </div>
          ) : null}
          {waitAge ? <div className="text-xs text-muted">{waitAge}</div> : null}
          {timing ? <div className="mt-0.5 text-xs text-muted">{timing}</div> : null}
        </div>
        <div className="text-right text-xs text-muted">
          <div className="font-medium text-fg/80">{formatStatus(j.item_status)}</div>
          {j.assigned_to_name ? <div>Queue → {j.assigned_to_name}</div> : null}
          {j.is_current && j.current_tech_name ? (
            <div className="mt-0.5 font-medium text-accent">
              Now: {j.current_tech_name}
            </div>
          ) : null}
        </div>
      </div>
      {actions ? <div className="mt-3 flex flex-wrap gap-2">{actions}</div> : null}
    </li>
  );
}

function OrderCard({
  o,
  actions,
}: {
  o: AssignedOrderSummary;
  actions?: ReactNode;
}) {
  const timing = roTiming(o);
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
        </div>
      </div>
      {(o.work_items || []).length > 0 ? (
        <ul className="mt-2 space-y-1 border-t border-border/60 pt-2 text-xs text-muted">
          {o.work_items.map((w) => (
            <li key={w.id}>
              <span className="font-mono">{w.id}</span> · {formatStatus(w.status)}
              {w.worked_minutes ? ` · ${formatWorkedMinutes(w.worked_minutes)}` : ""}
              {w.concern ? ` — ${w.concern}` : ""}
            </li>
          ))}
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

  const meId = board?.tech_id || "";
  const meName = board?.tech_name || "";
  const loggedIn = !!(meId || meName);
  const myCurrentId = board?.my_current?.item_id || board?.my_current?.id || "";

  async function runQueue(roId: string, action: QueueAct, itemId?: string) {
    setActingId(itemId || roId);
    setErr("");
    try {
      await api.queueAction(roId, action, itemId);
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Queue update failed");
    } finally {
      setActingId(null);
    }
  }

  async function runCurrent(roId: string, itemId: string, active: boolean) {
    setActingId(itemId);
    setErr("");
    try {
      await api.setCurrentTask(roId, active, active ? itemId : undefined);
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not update current work");
    } finally {
      setActingId(null);
    }
  }

  function btn(
    id: string,
    label: string,
    action: () => void,
    variant: "default" | "secondary" | "ghost" = "secondary",
  ) {
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

  function currentItemActions(roId: string, itemId: string) {
    return (
      <>
        {btn(itemId, "Completed", () => void runQueue(roId, "complete_item", itemId))}
        {btn(itemId, "Wait for parts", () =>
          void runQueue(roId, "item_waiting_parts", itemId),
        )}
        {btn(itemId, "Waiting on customer", () =>
          void runQueue(roId, "item_waiting_customer", itemId),
        )}
        {btn(itemId, "Stop working", () => void runCurrent(roId, itemId, false), "ghost")}
      </>
    );
  }

  function mineActions(j: AssignedJobSummary) {
    const isCurrent = j.is_current || j.item_id === myCurrentId;
    const reqPending = j.next_day_request?.status === "pending";
    return (
      <>
        {!isCurrent
          ? btn(j.item_id, "Start work", () => void runCurrent(j.ro_id, j.item_id, true))
          : currentItemActions(j.ro_id, j.item_id)}
        {!isCurrent && !reqPending && j.queue_lane !== "next_day"
          ? btn(j.item_id, "Request next day", () =>
              void (async () => {
                setActingId(j.item_id);
                setErr("");
                try {
                  await api.requestNextDay(j.ro_id, j.item_id);
                  await refresh();
                } catch (e) {
                  setErr(e instanceof Error ? e.message : "Request failed");
                } finally {
                  setActingId(null);
                }
              })(),
            "ghost")
          : null}
        {!isCurrent
          ? btn(j.item_id, "Remove from queue", () =>
              void runQueue(j.ro_id, "remove", j.item_id),
            "ghost")
          : null}
      </>
    );
  }

  function waitingActions(j: AssignedJobSummary) {
    return (
      <>
        {btn(j.item_id, "Start work", () => void runCurrent(j.ro_id, j.item_id, true), "default")}
      </>
    );
  }

  function unassignedActions(j: AssignedJobSummary) {
    return (
      <>
        {btn(j.item_id, "Add to my queue", () => void runQueue(j.ro_id, "add", j.item_id))}
        {btn(j.item_id, "Start work", () => void runCurrent(j.ro_id, j.item_id, true), "default")}
      </>
    );
  }

  function readyActions(o: AssignedOrderSummary) {
    return (
      <>
        {btn(o.id, "Reopen", () => void runQueue(o.id, "reopen"))}
        {btn(o.id, "Mark billed out", () => void runQueue(o.id, "billed_out"), "default")}
      </>
    );
  }

  function billedActions(o: AssignedOrderSummary) {
    return (
      <>
        {btn(o.id, "Reopen", () => void runQueue(o.id, "reopen"))}
        <Link
          to={`/history?${new URLSearchParams({
            ...(o.vin ? { vin: o.vin } : {}),
            exclude: o.id,
          }).toString()}`}
          className="inline-flex h-8 items-center justify-center rounded-lg border border-border bg-surface px-3 text-xs font-medium hover:bg-border/40"
        >
          VIN history
        </Link>
      </>
    );
  }

  function jobSection(
    title: string,
    items: AssignedJobSummary[] | undefined,
    empty: string,
    actionFor?: (j: AssignedJobSummary) => ReactNode,
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
            {list.map((j) => (
              <JobCard key={j.id} j={j} actions={actionFor?.(j)} />
            ))}
          </ul>
        )}
      </section>
    );
  }

  function roSection(
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
              <OrderCard key={o.id} o={o} actions={actionFor?.(o)} />
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
            Queue and current work are per work item (each concern billed separately). The RO is the
            car — itemize problems so diag fees stay with the right job.
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
          <p className="text-sm text-muted">No tech has a current work item.</p>
        ) : (
          <ul className="space-y-2">
            {(board?.now_working || []).map((entry) => (
              <li
                key={`${entry.tech_id || entry.tech_name}-${entry.item_id || entry.order.id}`}
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
                    {entry.job?.item_id || entry.item_id || "—"}
                  </Link>
                  <span className="text-muted">
                    {" "}
                    · {entry.job?.concern || entry.order.vehicle}
                  </span>
                  {entry.job ? (
                    <div className="mt-0.5 text-xs text-muted">
                      Worked {formatWorkedMinutes(entry.job.worked_minutes)}
                      {entry.job.timer_started_at ? " · timer on" : ""}
                    </div>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="text-xs text-muted">{entry.order.id}</div>
                  {entry.is_me && entry.item_id
                    ? currentItemActions(entry.order.id, entry.item_id)
                    : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {jobSection(
        "Today (my daily queue)",
        board?.mine_daily ?? board?.mine,
        "Nothing in today's queue. Add from Unassigned or ask an advisor to assign.",
        loggedIn ? mineActions : undefined,
      )}

      {jobSection(
        "Next day (mine)",
        board?.mine_next_day,
        "No jobs parked for tomorrow.",
        loggedIn ? mineActions : undefined,
      )}

      {jobSection(
        "Long-term (mine)",
        board?.mine_long_term,
        "No long-term pool jobs on your queue.",
        loggedIn ? mineActions : undefined,
        false,
      )}

      {jobSection(
        "Waiting on parts",
        board?.waiting_parts,
        "No jobs waiting on a parts order.",
        loggedIn ? waitingActions : undefined,
      )}

      {jobSection(
        "Awaiting customer approval",
        board?.waiting_customer,
        "No jobs waiting on customer approval.",
        loggedIn ? waitingActions : undefined,
      )}

      <section className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
          Found issues awaiting approval
          {(board?.found_issues_pending || []).length
            ? ` · ${(board?.found_issues_pending || []).length}`
            : ""}
        </h2>
        {(board?.found_issues_pending || []).length === 0 ? (
          <p className="text-sm text-muted">No pending found-issue requests.</p>
        ) : (
          <ul className="space-y-3">
            {(board?.found_issues_pending || []).map((fi: FoundIssueSummary) => (
              <li
                key={`${fi.ro_id}-${fi.id}`}
                className="rounded-xl border border-border bg-surface px-4 py-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <Link
                      to={`/ro/${fi.ro_id}`}
                      className="font-medium text-accent hover:underline"
                    >
                      {fi.id}
                      <span className="font-normal text-muted"> · {fi.ro_id}</span>
                    </Link>
                    <div className="mt-0.5 text-sm">{fi.description || "(no description)"}</div>
                    <div className="text-sm text-muted">
                      {fi.vehicle} · {fi.customer}
                      {fi.found_by ? ` · found by ${fi.found_by}` : ""}
                      {(fi.photo_count || 0) > 0
                        ? ` · ${fi.photo_count} photo${fi.photo_count === 1 ? "" : "s"}`
                        : ""}
                    </div>
                  </div>
                  {loggedIn ? (
                    <div className="flex flex-wrap gap-2">
                      {btn(fi.id, "Approve → work item", () =>
                        void (async () => {
                          setActingId(fi.id);
                          setErr("");
                          try {
                            await api.approveFoundIssue(fi.ro_id, fi.id, "repair");
                            await refresh();
                          } catch (e) {
                            setErr(e instanceof Error ? e.message : "Approve failed");
                          } finally {
                            setActingId(null);
                          }
                        })(),
                      "default")}
                      {btn(fi.id, "Decline", () =>
                        void (async () => {
                          setActingId(fi.id);
                          setErr("");
                          try {
                            await api.declineFoundIssue(fi.ro_id, fi.id);
                            await refresh();
                          } catch (e) {
                            setErr(e instanceof Error ? e.message : "Decline failed");
                          } finally {
                            setActingId(null);
                          }
                        })(),
                      )}
                    </div>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {roSection(
        "Ready to bill (advisor queue)",
        board?.ready_to_bill,
        "No finished jobs waiting for billing.",
        loggedIn ? readyActions : undefined,
      )}

      {roSection(
        "Billed out (closed history)",
        board?.billed_out,
        "No billed-out jobs in the local/shop cache yet.",
        loggedIn ? billedActions : undefined,
        false,
      )}

      <section className="space-y-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
          Other techs
        </h2>
        {(board?.by_tech || []).length === 0 ? (
          <p className="text-sm text-muted">No work items assigned to other technicians.</p>
        ) : (
          (board?.by_tech || []).map((bucket) => (
            <div key={bucket.id || bucket.name} className="space-y-2">
              <h3 className="text-sm font-medium">{bucket.name}</h3>
              <ul className="space-y-3">
                {(bucket.jobs || []).map((j) => (
                  <JobCard key={`${bucket.name}-${j.id}`} j={j} />
                ))}
              </ul>
            </div>
          ))
        )}
      </section>

      {jobSection(
        "Unassigned work items",
        board?.unassigned,
        "All open concerns have an assignee.",
        loggedIn ? unassignedActions : undefined,
      )}
    </div>
  );
}
