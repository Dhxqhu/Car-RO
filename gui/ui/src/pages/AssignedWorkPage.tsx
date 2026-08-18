import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
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
  formatWorkedHours,
  formatWorkedMinutes,
  cn,
  turnOrdinal,
} from "@/lib/utils";

type QueueCarGroup = {
  ro_id: string;
  queue_order: number;
  vehicle: string;
  customer: string;
  waiter?: boolean;
  urgent?: boolean;
  jobs: AssignedJobSummary[];
};

function groupJobsByCar(jobs: AssignedJobSummary[] | undefined): QueueCarGroup[] {
  const map = new Map<string, QueueCarGroup>();
  for (const j of jobs || []) {
    const existing = map.get(j.ro_id);
    const qo = Number(j.queue_order) || 0;
    if (!existing) {
      map.set(j.ro_id, {
        ro_id: j.ro_id,
        queue_order: qo,
        vehicle: j.vehicle,
        customer: j.customer,
        waiter: j.waiter,
        urgent: j.urgent,
        jobs: [j],
      });
      continue;
    }
    existing.jobs.push(j);
    if (qo && (!existing.queue_order || qo < existing.queue_order)) {
      existing.queue_order = qo;
    }
    if (j.waiter) existing.waiter = true;
    if (j.urgent) existing.urgent = true;
  }
  return [...map.values()].sort((a, b) => {
    const ao = a.queue_order || 9999;
    const bo = b.queue_order || 9999;
    if (ao !== bo) return ao - bo;
    return a.ro_id.localeCompare(b.ro_id);
  });
}

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
  return bits.join(" · ");
}

function OrderWorkedBreakdown({
  o,
  emphasize = false,
}: {
  o: AssignedOrderSummary;
  emphasize?: boolean;
}) {
  const byTech = o.tech_worked || [];
  const total =
    Number(o.worked_minutes) ||
    byTech.reduce((sum, t) => sum + Math.max(0, Number(t.minutes) || 0), 0);
  if (total <= 0 && byTech.length === 0) return null;
  return (
    <div
      className={cn(
        emphasize
          ? "mt-2 rounded-lg border border-accent/25 bg-accent/5 px-3 py-2"
          : "mt-1 text-xs text-muted",
      )}
    >
      {emphasize ? (
        <>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">
            Time worked
          </div>
          <div className="mt-0.5 text-sm font-semibold tabular-nums text-fg">
            Total {formatWorkedHours(total)}
            <span className="ml-1 font-normal text-muted">({formatWorkedMinutes(total)})</span>
          </div>
          {byTech.length > 0 ? (
            <ul className="mt-1.5 space-y-0.5 text-xs text-muted">
              {byTech.map((t) => (
                <li
                  key={`${t.tech_id || ""}-${t.tech_name}`}
                  className="flex items-baseline justify-between gap-3"
                >
                  <span className="min-w-0 truncate">{t.tech_name || "Unknown"}</span>
                  <span className="shrink-0 tabular-nums text-fg/90">
                    {formatWorkedHours(t.minutes)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-xs text-muted">No per-tech time log on this RO yet.</p>
          )}
        </>
      ) : (
        <>
          Worked {formatWorkedMinutes(total)}
          {byTech.length
            ? ` · ${byTech.map((t) => `${t.tech_name} ${formatWorkedMinutes(t.minutes)}`).join(", ")}`
            : ""}
        </>
      )}
    </div>
  );
}

function JobCard({
  j,
  actions,
  nested = false,
}: {
  j: AssignedJobSummary;
  actions?: ReactNode;
  nested?: boolean;
}) {
  const timing = jobTiming(j);
  const waitAge = jobWaitAge(j);
  const worked = Number(j.worked_minutes) || 0;
  const req = j.next_day_request;
  return (
    <li className={nested ? "px-0 py-2" : "rounded-xl border border-border bg-surface px-4 py-3"}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap gap-1.5">
            {j.due_eod ? (
              <span className="rounded bg-danger/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-danger">
                EOD
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
            {j.waiting_on_car ? (
              <span className="rounded bg-danger/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-danger">
                Wait — {j.car_held_by_name || "another tech"} has the car first
              </span>
            ) : null}
            {j.split_ro && j.car_turn ? (
              <span className="rounded bg-border/80 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted">
                Car {turnOrdinal(j.car_turn)}
              </span>
            ) : null}
          </div>
          <Link
            to={`/ro/${j.ro_id}`}
            className="font-medium text-accent hover:underline"
          >
            {j.item_id}
            {nested ? null : <span className="font-normal text-muted"> · {j.ro_id}</span>}
          </Link>
          <div className="mt-0.5 text-sm">{j.concern || "(no concern)"}</div>
          {nested ? null : (
            <div className="text-sm text-muted">
              {j.vehicle} · {j.customer}
            </div>
          )}
          <div className="mt-1 text-sm font-medium tabular-nums">
            Worked {formatWorkedMinutes(worked)}
          </div>
          {j.queue_lane !== "long_term" && Number(j.downtime_minutes) > 0 ? (
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
  emphasizeWorked = false,
}: {
  o: AssignedOrderSummary;
  actions?: ReactNode;
  emphasizeWorked?: boolean;
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
          <OrderWorkedBreakdown o={o} emphasize={emphasizeWorked} />
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
  const nav = useNavigate();
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

  async function runCurrent(
    roId: string,
    itemId: string,
    active: boolean,
    override = false,
  ) {
    setActingId(itemId);
    setErr("");
    try {
      await api.setCurrentTask(roId, active, active ? itemId : undefined, override);
      if (active && itemId) {
        nav(`/ro/${encodeURIComponent(roId)}?bay=${encodeURIComponent(itemId)}`);
        return;
      }
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
          ? j.waiting_on_car
            ? btn(
                `${j.item_id}-ov`,
                "Override — work now",
                () => {
                  if (
                    !window.confirm(
                      "Work this item while another tech has the car? Both timers will run.",
                    )
                  ) {
                    return;
                  }
                  void runCurrent(j.ro_id, j.item_id, true, true);
                },
                "ghost",
              )
            : btn(j.item_id, "Start work", () => void runCurrent(j.ro_id, j.item_id, true))
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
    const groups = groupJobsByCar(items);
    return (
      <section className="space-y-3">
        <h2
          className={`text-xs font-semibold uppercase tracking-wide ${
            accent ? "text-accent" : "text-muted"
          }`}
        >
          {title}
          {groups.length ? ` · ${groups.length}` : ""}
        </h2>
        {groups.length === 0 ? (
          <p className="text-sm text-muted">{empty}</p>
        ) : (
          <ul className="space-y-3">
            {groups.map((g) => (
              <li
                key={g.ro_id}
                className="rounded-xl border border-border bg-surface px-4 py-3"
              >
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <Link
                    to={`/ro/${g.ro_id}`}
                    className="font-medium text-accent hover:underline"
                  >
                    {g.ro_id}
                  </Link>
                  <span className="text-sm">
                    {g.vehicle}
                    {g.customer ? ` · ${g.customer}` : ""}
                  </span>
                  {g.waiter ? (
                    <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">
                      Waiter
                    </span>
                  ) : null}
                  {g.urgent ? (
                    <span className="rounded bg-danger/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-danger">
                      Urgent
                    </span>
                  ) : null}
                </div>
                <ul className="mt-2 ml-1 space-y-1 border-l-2 border-border pl-3">
                  {g.jobs.map((j) => (
                    <JobCard key={j.id} j={j} nested actions={actionFor?.(j)} />
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </section>
    );
  }

  function queuePathSection(
    title: string,
    items: AssignedJobSummary[] | undefined,
    empty: string,
    actionFor?: (j: AssignedJobSummary) => ReactNode,
  ) {
    const groups = groupJobsByCar(items);
    return (
      <section className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
          {title}
          {groups.length ? ` · ${groups.length}` : ""}
        </h2>
        {groups.length === 0 ? (
          <p className="text-sm text-muted">{empty}</p>
        ) : (
          <ol className="space-y-3">
            {groups.map((g, idx) => {
              const n = g.queue_order || idx + 1;
              return (
                <li
                  key={g.ro_id}
                  className="rounded-xl border border-border bg-surface px-4 py-3"
                >
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                    <span className="font-semibold tabular-nums text-accent">#{n}</span>
                    <Link
                      to={`/ro/${g.ro_id}`}
                      className="font-medium text-accent hover:underline"
                    >
                      {g.ro_id}
                    </Link>
                    <span className="text-sm">
                      {g.vehicle}
                      {g.customer ? ` · ${g.customer}` : ""}
                    </span>
                    {g.waiter ? (
                      <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">
                        Waiter
                      </span>
                    ) : null}
                    {g.urgent ? (
                      <span className="rounded bg-danger/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-danger">
                        Urgent
                      </span>
                    ) : null}
                  </div>
                  <ul className="mt-2 ml-1 space-y-2 border-l-2 border-border pl-3">
                    {g.jobs.map((j) => (
                      <li key={j.id} className="pt-0.5">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="text-sm font-medium">
                              {j.item_id}
                              <span className="font-normal text-muted">
                                {" "}
                                · {j.concern || "(no concern)"}
                              </span>
                            </div>
                            <div className="text-xs text-muted">
                              {[j.item_type, formatStatus(j.item_status)]
                                .filter(Boolean)
                                .join(" · ")}
                              {j.waiting_on_car
                                ? ` · wait — ${j.car_held_by_name || "other tech"} has the car`
                                : ""}
                            </div>
                          </div>
                          {actionFor?.(j)}
                        </div>
                      </li>
                    ))}
                  </ul>
                </li>
              );
            })}
          </ol>
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
    emphasizeWorked = false,
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
                actions={actionFor?.(o)}
                emphasizeWorked={emphasizeWorked}
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

      {queuePathSection(
        "Today (my daily queue)",
        board?.mine_daily ?? board?.mine,
        "Nothing in today's queue. Add from Unassigned or ask an advisor to assign.",
        loggedIn ? mineActions : undefined,
      )}

      {queuePathSection(
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
          Found issues & repair requests
          {(board?.found_issues_pending || []).length
            ? ` · ${(board?.found_issues_pending || []).length}`
            : ""}
        </h2>
        {(board?.found_issues_pending || []).length === 0 ? (
          <p className="text-sm text-muted">No pending found-issue or diag repair requests.</p>
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
                    <div className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
                      {fi.kind === "diag_complete"
                        ? "Repair request (diag)"
                        : "Found issue"}
                    </div>
                    <div className="mt-0.5 text-sm">{fi.description || "(no description)"}</div>
                    <div className="text-sm text-muted">
                      {fi.vehicle} · {fi.customer}
                      {fi.found_by ? ` · found by ${fi.found_by}` : ""}
                      {(fi.photo_count || 0) > 0
                        ? ` · ${fi.photo_count} photo${fi.photo_count === 1 ? "" : "s"}`
                        : ""}
                    </div>
                    <p className="mt-1 text-xs text-muted">
                      Advisor approves or declines at the desk.
                    </p>
                  </div>
                  <Link
                    to={`/ro/${fi.ro_id}`}
                    className="inline-flex h-8 items-center justify-center rounded-lg border border-border bg-surface px-3 text-xs font-medium hover:bg-border/40"
                  >
                    Open RO
                  </Link>
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
        true,
        true,
      )}

      {roSection(
        "Billed out (closed history)",
        board?.billed_out,
        "No billed-out jobs in the local/shop cache yet.",
        loggedIn ? billedActions : undefined,
        false,
      )}

      {roSection(
        "Canceled",
        board?.canceled,
        "No canceled repair orders in the local/shop cache.",
        loggedIn ? billedActions : undefined,
        false,
      )}

      {roSection(
        "No call / no show",
        board?.no_call_no_show,
        "No no-call/no-show repair orders in the local/shop cache.",
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
            <div key={bucket.id || bucket.name}>
              {jobSection(
                bucket.name,
                bucket.jobs,
                "No work items on this queue.",
                undefined,
                false,
              )}
            </div>
          ))
        )}
      </section>

      {jobSection(
        "Unassigned work items",
        board?.unassigned,
        "Nothing unassigned — ask an advisor to dish work, or check your Today / Next day / Long-term queues above.",
        loggedIn ? unassignedActions : undefined,
      )}
    </div>
  );
}
