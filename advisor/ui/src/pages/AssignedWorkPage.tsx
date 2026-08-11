import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import {
  api,
  type AssignedBoard,
  type AssignedJobSummary,
  type AssignedOrderSummary,
  type FoundIssueSummary,
  type PartsSheetRow,
  type Technician,
  type TechShift,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  formatDataSource,
  formatDurationMinutes,
  formatShopTime,
  formatStatus,
  formatWorkedHours,
  formatWorkedMinutes,
  cn,
} from "@/lib/utils";

const DESK_TAB_KEY = "carro-advisor-desk-tab";
const DESK_DENSITY_KEY = "carro-advisor-desk-density";
type DeskTab = "floor" | "queues" | "assign" | "punches";
type DeskDensity = "comfortable" | "compact";

function loadDeskTab(): DeskTab {
  try {
    const v = sessionStorage.getItem(DESK_TAB_KEY);
    if (v === "floor" || v === "queues" || v === "assign" || v === "punches") return v;
  } catch {
    /* ignore */
  }
  return "floor";
}

function loadDeskDensity(): DeskDensity {
  try {
    const v = localStorage.getItem(DESK_DENSITY_KEY);
    if (v === "comfortable" || v === "compact") return v;
  } catch {
    /* ignore */
  }
  return "comfortable";
}

function floorSortJobs(a: AssignedJobSummary, b: AssignedJobSummary): number {
  const wa = a.waiter ? 0 : 1;
  const wb = b.waiter ? 0 : 1;
  if (wa !== wb) return wa - wb;
  const ua = a.urgent ? 0 : 1;
  const ub = b.urgent ? 0 : 1;
  if (ua !== ub) return ua - ub;
  return String(b.updated || "").localeCompare(String(a.updated || ""));
}
function todayLocalIso(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** ISO → value for `<input type="datetime-local">`. */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

type QueueAct =
  | "add"
  | "remove"
  | "complete"
  | "complete_item"
  | "billed_out"
  | "canceled"
  | "no_call_no_show"
  | "reopen"
  | "waiting_parts"
  | "request_parts"
  | "item_waiting_parts"
  | "waiting_customer"
  | "request_approval"
  | "item_waiting_customer"
  | "item_release_wait"
  | "item_return_to_requester";

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
  if (o.canceled_at) bits.push(`canceled ${formatShopTime(o.canceled_at)}`);
  if (o.no_call_no_show_at)
    bits.push(`no call / no show ${formatShopTime(o.no_call_no_show_at)}`);
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
  density = "comfortable",
}: {
  j: AssignedJobSummary;
  actions?: ReactNode;
  density?: DeskDensity;
}) {
  const compact = density === "compact";
  const timing = jobTiming(j);
  const waitAge = jobWaitAge(j);
  const worked = Number(j.worked_minutes) || 0;
  const req = j.next_day_request;
  const showLaneChip = !compact && j.queue_lane && j.queue_lane !== "daily";
  const showPendingLane = !compact && !!j.pending_queue_lane;
  const showNextDayReq = req?.status === "pending";

  return (
    <li
      className={cn(
        "rounded-xl border border-border bg-surface",
        compact ? "px-3 py-2" : "px-4 py-3",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {(j.waiter || j.urgent || j.due_eod || showLaneChip || showPendingLane || showNextDayReq) ? (
            <div className={cn("flex flex-wrap gap-1.5", compact ? "mb-0.5" : "mb-1")}>
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
              {j.due_eod ? (
                <span className="rounded bg-danger/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-danger">
                  EOD
                </span>
              ) : null}
              {showLaneChip ? (
                <span className="rounded bg-border/80 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted">
                  {j.queue_lane === "next_day" ? "Next day" : "Long-term"}
                </span>
              ) : null}
              {showPendingLane ? (
                <span className="rounded bg-border/80 px-1.5 py-0.5 text-[10px] font-medium text-muted">
                  Push {j.pending_queue_lane === "next_day" ? "next day" : j.pending_queue_lane} on
                  clock-out
                </span>
              ) : null}
              {showNextDayReq ? (
                <span className="rounded bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                  Next-day requested{req?.read_at ? "" : " · unread"}
                </span>
              ) : null}
            </div>
          ) : null}
          {compact ? (
            <>
              <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <Link
                  to={`/ro/${j.ro_id}`}
                  className="font-medium text-accent hover:underline"
                >
                  {j.item_id}
                  <span className="font-normal text-muted"> · {j.ro_id}</span>
                </Link>
                <span className="truncate text-sm text-fg/90">
                  {j.concern || "(no concern)"}
                </span>
              </div>
              <div className="mt-0.5 truncate text-xs text-muted">
                {[j.vehicle, j.customer].filter(Boolean).join(" · ")}
                {j.assigned_to_name ? ` · ${j.assigned_to_name}` : ""}
                {` · ${formatStatus(j.item_status)}`}
                {` · ${formatWorkedMinutes(worked)}`}
                {j.is_current && j.current_tech_name ? ` · Now ${j.current_tech_name}` : ""}
              </div>
            </>
          ) : (
            <>
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
              {j.queue_lane !== "long_term" && Number(j.downtime_minutes) > 0 ? (
                <div className="text-xs text-muted">
                  Downtime {formatDurationMinutes(j.downtime_minutes)}
                </div>
              ) : null}
              {waitAge ? <div className="text-xs text-muted">{waitAge}</div> : null}
              {timing ? <div className="mt-0.5 text-xs text-muted">{timing}</div> : null}
            </>
          )}
        </div>
        {!compact ? (
          <div className="text-right text-xs text-muted">
            <div className="font-medium text-fg/80">{formatStatus(j.item_status)}</div>
            {j.assigned_to_name ? <div>Queue → {j.assigned_to_name}</div> : null}
            {j.is_current && j.current_tech_name ? (
              <div className="mt-0.5 font-medium text-accent">
                Now: {j.current_tech_name}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
      {actions ? (
        <div className={cn("flex flex-wrap gap-2", compact ? "mt-2" : "mt-3")}>{actions}</div>
      ) : null}
    </li>
  );
}

function OrderCard({
  o,
  actions,
  density = "comfortable",
  emphasizeWorked = false,
}: {
  o: AssignedOrderSummary;
  actions?: ReactNode;
  density?: DeskDensity;
  emphasizeWorked?: boolean;
}) {
  const compact = density === "compact";
  const timing = roTiming(o);
  const total = Number(o.items_total) || (o.work_items || []).length;
  const done = Number(o.items_done) || 0;
  const open = Number(o.items_open);
  const openN = Number.isFinite(open)
    ? open
    : (o.work_items || []).filter((w) => {
        const s = (w.status || "").toLowerCase();
        return s !== "done" && s !== "declined";
      }).length;
  return (
    <li
      className={cn(
        "rounded-xl border border-border bg-surface",
        compact ? "px-3 py-2" : "px-4 py-3",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {compact ? (
            <>
              <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <Link to={`/ro/${o.id}`} className="font-medium text-accent hover:underline">
                  {o.id}
                </Link>
                <span className="truncate text-sm">{o.customer}</span>
              </div>
              <div className="mt-0.5 truncate text-xs text-muted">
                {[o.vehicle, formatStatus(o.status)].filter(Boolean).join(" · ")}
                {total > 0 ? ` · ${done}/${total} done` : ""}
                {openN > 0 ? ` · ${openN} open` : ""}
              </div>
            </>
          ) : (
            <>
              <Link to={`/ro/${o.id}`} className="font-medium text-accent hover:underline">
                {o.id}
              </Link>
              <div className="text-sm">{o.customer}</div>
              <div className="text-sm text-muted">{o.vehicle}</div>
              {total > 0 ? (
                <div className="mt-1 text-xs text-muted tabular-nums">
                  Items {done}/{total} done
                  {openN > 0 ? ` · ${openN} still open` : ""}
                </div>
              ) : null}
              {(o.open_concerns || []).length > 0 ? (
                <div className="mt-0.5 text-xs text-muted">
                  Open: {(o.open_concerns || []).slice(0, 3).join(" · ")}
                </div>
              ) : null}
              {timing ? <div className="mt-1 text-xs text-muted">{timing}</div> : null}
            </>
          )}
          <OrderWorkedBreakdown o={o} emphasize={emphasizeWorked && !compact} />
        </div>
        {!compact ? (
          <div className="text-right text-xs text-muted">
            <div className="font-medium text-fg/80">{formatStatus(o.status)}</div>
          </div>
        ) : null}
      </div>
      {!compact && (o.work_items || []).length > 0 ? (
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
      {actions ? (
        <div className={cn("flex flex-wrap gap-2", compact ? "mt-2" : "mt-3")}>{actions}</div>
      ) : null}
    </li>
  );
}

export function AssignedWorkPage() {
  const nav = useNavigate();
  const [board, setBoard] = useState<AssignedBoard | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [actingId, setActingId] = useState<string | null>(null);
  const [advisorOn, setAdvisorOn] = useState(false);
  const [workingPrivilege, setWorkingPrivilege] = useState(false);
  const [advisorId, setAdvisorId] = useState("");
  const [advisorName, setAdvisorName] = useState("");
  const [activeShifts, setActiveShifts] = useState<TechShift[]>([]);
  const [todayShifts, setTodayShifts] = useState<TechShift[]>([]);
  const [techs, setTechs] = useState<Technician[]>([]);
  const [clockInTechId, setClockInTechId] = useState("");
  const [clockInAt, setClockInAt] = useState("");
  const [showClockInTime, setShowClockInTime] = useState(false);
  const [editingShiftId, setEditingShiftId] = useState<number | null>(null);
  const [editStart, setEditStart] = useState("");
  const [editEnd, setEditEnd] = useState("");
  const [deskTab, setDeskTab] = useState<DeskTab>(() => loadDeskTab());
  const [density, setDensityState] = useState<DeskDensity>(() => loadDeskDensity());
  /** Per work-item tech id chosen in Assign controls */
  const [assignPick, setAssignPick] = useState<Record<string, string>>({});
  const [dueEodPick, setDueEodPick] = useState<Record<string, boolean>>({});
  /** Per found-issue tech id for Approve → Assign */
  const [fiApprovePick, setFiApprovePick] = useState<Record<string, string>>({});
  const [openParts, setOpenParts] = useState<PartsSheetRow[]>([]);

  const setTab = useCallback((t: DeskTab) => {
    setDeskTab(t);
    try {
      sessionStorage.setItem(DESK_TAB_KEY, t);
    } catch {
      /* ignore */
    }
  }, []);

  const setDensity = useCallback((d: DeskDensity) => {
    setDensityState(d);
    try {
      localStorage.setItem(DESK_DENSITY_KEY, d);
    } catch {
      /* ignore */
    }
  }, []);

  const refresh = useCallback(async () => {
    setBusy(true);
    setErr("");
    const day = todayLocalIso();
    try {
      const [b, who, shifts, dayShifts, roster, parts] = await Promise.all([
        api.assignedBoard(),
        api.advisorWhoami().catch(() => ({ advisor: null })),
        api.shiftsActive().catch(() => ({ shifts: [] as TechShift[] })),
        api
          .listShifts({ day_from: day, day_to: day, limit: 200 })
          .catch(() => ({ shifts: [] as TechShift[] })),
        api.listTechs().catch(() => ({ technicians: [] as Technician[] })),
        api
          .listParts({ include_received: false, source: "auto" })
          .catch(() => ({ parts: [] as PartsSheetRow[] })),
      ]);
      setBoard(b);
      setAdvisorOn(!!who.advisor);
      const priv =
        !!(who as { working_privilege?: boolean }).working_privilege ||
        !!who.advisor?.working_privilege;
      setWorkingPrivilege(priv);
      setAdvisorId(who.advisor?.id || "");
      setAdvisorName(who.advisor?.name || "");
      setActiveShifts(shifts.shifts || []);
      setTodayShifts(dayShifts.shifts || []);
      setTechs(roster.technicians || []);
      setOpenParts(parts.parts || []);
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
  const loggedIn = advisorOn || !!(meId || meName);
  const myCurrentId = board?.my_current?.item_id || board?.my_current?.id || "";

  const offClockTechs = useMemo(() => {
    const on = new Set(activeShifts.map((s) => s.tech_id));
    return techs.filter((t) => t.id && !on.has(t.id));
  }, [techs, activeShifts]);

  async function clockInTech() {
    if (!clockInTechId) return;
    const tech = techs.find((t) => t.id === clockInTechId);
    setActingId(`in:${clockInTechId}`);
    setErr("");
    try {
      await api.shiftStart({
        tech_id: clockInTechId,
        tech_name: tech?.name || "",
        started_at: clockInAt || undefined,
      });
      setClockInTechId("");
      setClockInAt("");
      setShowClockInTime(false);
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not clock in");
    } finally {
      setActingId(null);
    }
  }

  async function clockOutTech(s: TechShift, endedAt?: string) {
    setActingId(`out:${s.id}`);
    setErr("");
    try {
      await api.shiftEnd({
        tech_id: s.tech_id,
        shift_id: s.id,
        ended_at: endedAt || undefined,
      });
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not clock out");
    } finally {
      setActingId(null);
    }
  }

  function beginEditShift(s: TechShift) {
    setEditingShiftId(s.id);
    setEditStart(toLocalInput(s.started_at));
    setEditEnd(toLocalInput(s.ended_at));
  }

  async function saveEditShift(s: TechShift) {
    setActingId(`edit:${s.id}`);
    setErr("");
    try {
      const body: {
        started_at?: string;
        ended_at?: string | null;
        clear_end?: boolean;
      } = {};
      if (editStart) body.started_at = editStart;
      if (!s.ended_at && !editEnd) {
        // still open — leave end alone
      } else if (editEnd) {
        body.ended_at = editEnd;
      } else {
        body.clear_end = true;
      }
      await api.updateShift(s.id, body);
      setEditingShiftId(null);
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save punch");
    } finally {
      setActingId(null);
    }
  }

  async function reopenShift(s: TechShift) {
    setActingId(`reopen:${s.id}`);
    setErr("");
    try {
      await api.updateShift(s.id, { clear_end: true });
      setEditingShiftId(null);
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not reopen punch");
    } finally {
      setActingId(null);
    }
  }

  async function removeShift(s: TechShift) {
    if (!window.confirm(`Delete punch for ${s.tech_name || s.tech_id}?`)) return;
    setActingId(`del:${s.id}`);
    setErr("");
    try {
      await api.deleteShift(s.id);
      if (editingShiftId === s.id) setEditingShiftId(null);
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not delete punch");
    } finally {
      setActingId(null);
    }
  }

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

  async function runPartStatus(row: PartsSheetRow, next: string) {
    const key = `${row.ro_id}:${row.part_id}`;
    setActingId(key);
    setErr("");
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
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Part update failed");
    } finally {
      setActingId(null);
    }
  }

  async function runCurrent(roId: string, itemId: string, active: boolean) {
    setActingId(itemId);
    setErr("");
    try {
      await api.setCurrentTask(roId, active, active ? itemId : undefined);
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

  function advisorLaneActions(j: AssignedJobSummary) {
    const reqPending = j.next_day_request?.status === "pending";
    return (
      <>
        {reqPending
          ? btn(j.item_id, "Approve next day", () =>
              void (async () => {
                setActingId(j.item_id);
                setErr("");
                try {
                  await api.decideNextDayRequest(j.ro_id, j.item_id, true);
                  await refresh();
                } catch (e) {
                  setErr(e instanceof Error ? e.message : "Approve failed");
                } finally {
                  setActingId(null);
                }
              })(),
            "default")
          : null}
        {reqPending
          ? btn(j.item_id, "Decline → due EOD", () =>
              void (async () => {
                setActingId(j.item_id);
                setErr("");
                try {
                  await api.decideNextDayRequest(j.ro_id, j.item_id, false);
                  await refresh();
                } catch (e) {
                  setErr(e instanceof Error ? e.message : "Decline failed");
                } finally {
                  setActingId(null);
                }
              })(),
            "ghost")
          : null}
        {reqPending && !j.next_day_request?.read_at
          ? btn(j.item_id, "Mark request read", () =>
              void (async () => {
                setActingId(j.item_id);
                try {
                  await api.markNextDayRequestRead(j.ro_id, j.item_id);
                  await refresh();
                } catch (e) {
                  setErr(e instanceof Error ? e.message : "Mark read failed");
                } finally {
                  setActingId(null);
                }
              })(),
            "ghost")
          : null}
        {j.queue_lane !== "next_day"
          ? btn(j.item_id, "Push next day", () =>
              void (async () => {
                setActingId(j.item_id);
                setErr("");
                try {
                  await api.setWorkItemQueueLane(j.ro_id, j.item_id, "next_day", true);
                  await refresh();
                } catch (e) {
                  setErr(e instanceof Error ? e.message : "Push failed");
                } finally {
                  setActingId(null);
                }
              })(),
            )
          : null}
        {j.queue_lane !== "long_term"
          ? btn(j.item_id, "Back to long-term", () =>
              void (async () => {
                setActingId(j.item_id);
                setErr("");
                try {
                  await api.setWorkItemQueueLane(j.ro_id, j.item_id, "long_term");
                  await refresh();
                } catch (e) {
                  setErr(e instanceof Error ? e.message : "Move failed");
                } finally {
                  setActingId(null);
                }
              })(),
            "ghost")
          : null}
        {j.queue_lane === "long_term"
          ? btn(j.item_id, "Unmark long-term", () =>
              void (async () => {
                setActingId(j.item_id);
                setErr("");
                try {
                  await api.setWorkItemQueueLane(j.ro_id, j.item_id, "daily");
                  await refresh();
                } catch (e) {
                  setErr(e instanceof Error ? e.message : "Move failed");
                } finally {
                  setActingId(null);
                }
              })(),
            "ghost")
          : j.queue_lane !== "daily"
            ? btn(j.item_id, "To today", () =>
                void (async () => {
                  setActingId(j.item_id);
                  setErr("");
                  try {
                    await api.setWorkItemQueueLane(j.ro_id, j.item_id, "daily");
                    await refresh();
                  } catch (e) {
                    setErr(e instanceof Error ? e.message : "Move failed");
                  } finally {
                    setActingId(null);
                  }
                })(),
              "ghost")
            : null}
        {btn(
          `${j.ro_id}-waiter`,
          j.waiter ? "Clear waiter" : "Mark waiter",
          () =>
            void (async () => {
              setActingId(`${j.ro_id}-waiter`);
              setErr("");
              try {
                await api.setRoFlags(j.ro_id, { waiter: !j.waiter });
                await refresh();
              } catch (e) {
                setErr(e instanceof Error ? e.message : "Flag failed");
              } finally {
                setActingId(null);
              }
            })(),
          "ghost",
        )}
        {btn(
          `${j.ro_id}-urgent`,
          j.urgent ? "Clear urgent" : "Mark urgent",
          () =>
            void (async () => {
              setActingId(`${j.ro_id}-urgent`);
              setErr("");
              try {
                await api.setRoFlags(j.ro_id, { urgent: !j.urgent });
                await refresh();
              } catch (e) {
                setErr(e instanceof Error ? e.message : "Flag failed");
              } finally {
                setActingId(null);
              }
            })(),
          "ghost",
        )}
      </>
    );
  }

  async function assignItemToSelf(j: AssignedJobSummary) {
    if (!advisorId || !j.item_id) return;
    setActingId(`assign-me:${j.item_id}`);
    setErr("");
    const dueEod = dueEodPick[j.item_id] ?? Boolean(j.due_eod);
    try {
      await api.assignRo(j.ro_id, {
        assigned_to_id: advisorId,
        assigned_to_name: advisorName || advisorId,
        item_id: j.item_id,
        due_eod: dueEod,
      });
      setDueEodPick((prev) => {
        const next = { ...prev };
        delete next[j.item_id];
        return next;
      });
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Assign to me failed");
    } finally {
      setActingId(null);
    }
  }

  async function assignItemToTech(j: AssignedJobSummary, techId: string) {
    const tech = techs.find((t) => t.id === techId);
    if (!techId || !j.item_id) return;
    setActingId(`assign:${j.item_id}`);
    setErr("");
    const dueEod = dueEodPick[j.item_id] ?? Boolean(j.due_eod);
    try {
      await api.assignRo(j.ro_id, {
        assigned_to_id: techId,
        assigned_to_name: tech?.name || "",
        item_id: j.item_id,
        due_eod: dueEod,
      });
      setAssignPick((prev) => {
        const next = { ...prev };
        delete next[j.item_id];
        return next;
      });
      setDueEodPick((prev) => {
        const next = { ...prev };
        delete next[j.item_id];
        return next;
      });
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Assign failed");
    } finally {
      setActingId(null);
    }
  }

  async function unassignItem(j: AssignedJobSummary) {
    if (!j.item_id) return;
    setActingId(`unassign:${j.item_id}`);
    setErr("");
    try {
      await api.assignRo(j.ro_id, {
        assigned_to_id: "",
        assigned_to_name: "",
        item_id: j.item_id,
      });
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Unassign failed");
    } finally {
      setActingId(null);
    }
  }

  function assignActions(j: AssignedJobSummary) {
    const pick = assignPick[j.item_id] || "";
    const dueEod = dueEodPick[j.item_id] ?? Boolean(j.due_eod);
    const assigned = !!(j.assigned_to_id || j.assigned_to_name);
    const assignedToMe =
      !!advisorId &&
      (j.assigned_to_id === advisorId ||
        (j.assigned_to_name || "").toLowerCase() === (advisorName || "").toLowerCase());
    return (
      <div className="flex w-full flex-wrap items-end gap-2">
        {workingPrivilege ? (
          <>
            {!assignedToMe ? (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                disabled={actingId === `assign-me:${j.item_id}`}
                onClick={() => void assignItemToSelf(j)}
              >
                Assign to me
              </Button>
            ) : null}
            {btn(j.item_id, "Add to my queue", () => void runQueue(j.ro_id, "add", j.item_id))}
            {myCurrentId === j.item_id
              ? btn(j.item_id, "Stop working", () => void runCurrent(j.ro_id, j.item_id, false), "ghost")
              : btn(
                  j.item_id,
                  "Start work",
                  () => void runCurrent(j.ro_id, j.item_id, true),
                  "default",
                )}
          </>
        ) : null}
        <label className="min-w-[10rem] flex-1 text-xs text-muted">
          {assigned ? "Reassign to" : "Assign to"}
          <select
            className="mt-1 flex h-9 w-full rounded-lg border border-border bg-surface px-2 text-sm text-fg"
            value={pick}
            onChange={(e) =>
              setAssignPick((prev) => ({ ...prev, [j.item_id]: e.target.value }))
            }
          >
            <option value="">Select tech…</option>
            {techs.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name || t.id}
              </option>
            ))}
          </select>
        </label>
        <label className="flex cursor-pointer items-center gap-1.5 pb-2 text-xs text-muted">
          <input
            type="checkbox"
            className="h-4 w-4 accent-[var(--accent)]"
            checked={dueEod}
            onChange={(e) =>
              setDueEodPick((prev) => ({ ...prev, [j.item_id]: e.target.checked }))
            }
          />
          Done by EOD
        </label>
        <Button
          type="button"
          size="sm"
          disabled={!pick || actingId === `assign:${j.item_id}`}
          onClick={() => void assignItemToTech(j, pick)}
        >
          Assign
        </Button>
        {assigned ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={actingId === `unassign:${j.item_id}`}
            onClick={() => void unassignItem(j)}
          >
            Unassign
          </Button>
        ) : null}
      </div>
    );
  }

  function deskJobActions(j: AssignedJobSummary) {
    return (
      <>
        {waitReleaseActions(j)}
        {assignActions(j)}
        {advisorLaneActions(j)}
        {j.from_found_issue_id
          ? btn(
              `undo-fi:${j.item_id}`,
              "Undo approval",
              () =>
                void (async () => {
                  if (
                    !window.confirm(
                      "Undo approval? The work item is removed and the found issue returns to pending.",
                    )
                  ) {
                    return;
                  }
                  setActingId(`undo-fi:${j.item_id}`);
                  setErr("");
                  try {
                    await api.undoFoundIssueApproval(j.ro_id, j.from_found_issue_id!);
                    await refresh();
                  } catch (e) {
                    setErr(e instanceof Error ? e.message : "Undo approval failed");
                  } finally {
                    setActingId(null);
                  }
                })(),
              "ghost",
            )
          : null}
      </>
    );
  }

  function foundIssueApproveActions(fi: FoundIssueSummary) {
    const pick = fiApprovePick[fi.id] || "";
    const tech = techs.find((t) => t.id === pick);
    return (
      <div className="flex w-full flex-wrap items-end gap-2">
        <label className="min-w-[10rem] flex-1 text-xs text-muted">
          Assign to (optional)
          <select
            className="mt-1 flex h-9 w-full rounded-lg border border-border bg-surface px-2 text-sm text-fg"
            value={pick}
            onChange={(e) =>
              setFiApprovePick((prev) => ({ ...prev, [fi.id]: e.target.value }))
            }
          >
            <option value="">Select tech…</option>
            {techs.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name || t.id}
              </option>
            ))}
          </select>
        </label>
        {btn(
          `fi-unass:${fi.id}`,
          "Approve → Unassigned",
          () =>
            void (async () => {
              setActingId(`fi-unass:${fi.id}`);
              setErr("");
              try {
                await api.approveFoundIssue(fi.ro_id, fi.id, "repair");
                setFiApprovePick((prev) => {
                  const next = { ...prev };
                  delete next[fi.id];
                  return next;
                });
                await refresh();
              } catch (e) {
                setErr(e instanceof Error ? e.message : "Approve failed");
              } finally {
                setActingId(null);
              }
            })(),
          "default",
        )}
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={!pick || actingId === `fi-ass:${fi.id}` || busy}
          onClick={() =>
            void (async () => {
              if (!pick) return;
              setActingId(`fi-ass:${fi.id}`);
              setErr("");
              try {
                await api.approveFoundIssue(fi.ro_id, fi.id, "repair", {
                  assign_to_id: pick,
                  assign_to_name: tech?.name || "",
                });
                setFiApprovePick((prev) => {
                  const next = { ...prev };
                  delete next[fi.id];
                  return next;
                });
                await refresh();
              } catch (e) {
                setErr(e instanceof Error ? e.message : "Approve failed");
              } finally {
                setActingId(null);
              }
            })()
          }
        >
          Approve → Assign
        </Button>
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
    );
  }

  function waitReleaseActions(j: AssignedJobSummary) {
    const st = (j.item_status || "").toLowerCase();
    if (st !== "waiting_customer" && st !== "waiting_parts") return null;
    const requester =
      (j.wait_requested_by || "").trim() ||
      (j.assigned_to_name || "").trim() ||
      "";
    const readyLabel =
      st === "waiting_customer" ? "Approved → Unassigned" : "Ready → Unassigned";
    return (
      <div className="flex w-full flex-wrap items-end gap-2">
        {btn(
          `release:${j.item_id}`,
          readyLabel,
          () => void runQueue(j.ro_id, "item_release_wait", j.item_id),
          "default",
        )}
        {requester
          ? btn(
              `return:${j.item_id}`,
              `Return to ${requester}`,
              () => void runQueue(j.ro_id, "item_return_to_requester", j.item_id),
            )
          : null}
      </div>
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

  function unassignedDeskActions(j: AssignedJobSummary) {
    if (advisorOn) {
      return (
        <>
          {assignActions(j)}
          {advisorLaneActions(j)}
          {j.from_found_issue_id
            ? btn(
                `undo-fi:${j.item_id}`,
                "Undo approval",
                () =>
                  void (async () => {
                    if (
                      !window.confirm(
                        "Undo approval? The work item is removed and the found issue returns to pending.",
                      )
                    ) {
                      return;
                    }
                    setActingId(`undo-fi:${j.item_id}`);
                    setErr("");
                    try {
                      await api.undoFoundIssueApproval(j.ro_id, j.from_found_issue_id!);
                      await refresh();
                    } catch (e) {
                      setErr(e instanceof Error ? e.message : "Undo approval failed");
                    } finally {
                      setActingId(null);
                    }
                  })(),
                "ghost",
              )
            : null}
        </>
      );
    }
    if (loggedIn) return unassignedActions(j);
    return undefined;
  }

  function readyActions(o: AssignedOrderSummary) {
    return (
      <>
        <Link
          to={`/ro/${o.id}?newItem=1`}
          className="inline-flex h-8 items-center justify-center rounded-lg border border-border bg-surface px-3 text-xs font-medium hover:bg-border/40"
        >
          More work requested
        </Link>
        {btn(o.id, "Reopen", () => void runQueue(o.id, "reopen"))}
        {btn(o.id, "Mark billed out", () => void runQueue(o.id, "billed_out"), "default")}
      </>
    );
  }

  /** Tech on advisor desk: reopen only — billed-out stays advisor. */
  function readyReopenActions(o: AssignedOrderSummary) {
    return <>{btn(o.id, "Reopen", () => void runQueue(o.id, "reopen"))}</>;
  }

  function waitingOtherActions(o: AssignedOrderSummary) {
    return (
      <Link
        to={`/ro/${o.id}`}
        className="inline-flex h-8 items-center justify-center rounded-lg border border-border bg-surface px-3 text-xs font-medium hover:bg-border/40"
      >
        Open RO
      </Link>
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

  const waiterUrgentJobs = useMemo(() => {
    const map = new Map<string, AssignedJobSummary>();
    const absorb = (jobs?: AssignedJobSummary[]) => {
      for (const j of jobs || []) {
        // Long-term / next-day stay in Queues only — not Needs attention until today.
        const lane = (j.queue_lane || "").toLowerCase();
        if (lane === "long_term" || lane === "next_day") continue;
        if (!j.waiter && !j.urgent) continue;
        const key = j.item_id || j.id || `${j.ro_id}-${j.concern}`;
        if (!map.has(key)) map.set(key, j);
      }
    };
    absorb(board?.waiting_parts);
    absorb(board?.waiting_customer);
    absorb(board?.unassigned);
    absorb(board?.mine_daily ?? board?.mine);
    for (const bucket of board?.daily_by_tech || []) absorb(bucket.jobs);
    for (const bucket of board?.by_tech || []) absorb(bucket.jobs);
    for (const entry of board?.now_working || []) {
      if (entry.job) absorb([entry.job]);
    }
    return [...map.values()].sort(floorSortJobs);
  }, [board]);

  const attentionWaitingParts = useMemo(
    () =>
      (board?.waiting_parts || []).filter((j) => {
        const lane = (j.queue_lane || "").toLowerCase();
        return lane !== "long_term" && lane !== "next_day";
      }),
    [board?.waiting_parts],
  );
  const attentionWaitingCustomer = useMemo(
    () =>
      (board?.waiting_customer || []).filter((j) => {
        const lane = (j.queue_lane || "").toLowerCase();
        return lane !== "long_term" && lane !== "next_day";
      }),
    [board?.waiting_customer],
  );
  const attentionUnassigned = useMemo(
    () =>
      (board?.unassigned || []).filter((j) => {
        const lane = (j.queue_lane || "").toLowerCase();
        return lane !== "long_term" && lane !== "next_day";
      }),
    [board?.unassigned],
  );
  const attentionNextDayRequests = useMemo(
    () =>
      (board?.defer_requests || []).filter(
        (j) => (j.next_day_request?.status || "").toLowerCase() === "pending",
      ),
    [board?.defer_requests],
  );

  const neededParts = useMemo(() => {
    const toOrder: PartsSheetRow[] = [];
    const onOrder: PartsSheetRow[] = [];
    for (const row of openParts) {
      const s = (row.status || "").toLowerCase();
      if (s === "ordered") onOrder.push(row);
      else toOrder.push(row);
    }
    return { toOrder, onOrder, total: openParts.length };
  }, [openParts]);

  const tabCounts = useMemo(() => {
    const dailyJobs = (board?.daily_by_tech || []).reduce(
      (n, b) => n + (b.jobs || []).length,
      0,
    );
    const otherJobs = (board?.by_tech || []).reduce((n, b) => n + (b.jobs || []).length, 0);
    return {
      floor:
        activeShifts.length + (board?.now_working || []).length + dailyJobs,
      queues:
        (board?.next_day || []).length +
        (board?.long_term || []).length +
        (board?.waiting_parts || []).length +
        (board?.waiting_customer || []).length +
        (board?.found_issues_pending || []).length +
        (board?.waiting_other_items || []).length +
        (board?.ready_to_bill || []).length +
        neededParts.total,
      assign: (board?.unassigned || []).length + otherJobs,
      punches: todayShifts.length,
      attention:
        waiterUrgentJobs.length +
        (board?.found_issues_pending || []).length +
        (board?.ready_to_bill || []).length +
        (board?.waiting_other_items || []).length +
        attentionWaitingParts.length +
        attentionWaitingCustomer.length +
        attentionUnassigned.length +
        attentionNextDayRequests.length +
        neededParts.total,
    };
  }, [
    board,
    activeShifts.length,
    todayShifts.length,
    waiterUrgentJobs.length,
    attentionWaitingParts.length,
    attentionWaitingCustomer.length,
    attentionUnassigned.length,
    attentionNextDayRequests.length,
    neededParts.total,
  ]);

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
          <ul className={cn("space-y-3", density === "compact" && "space-y-2")}>
            {list.map((j) => (
              <JobCard key={j.id} j={j} density={density} actions={actionFor?.(j)} />
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
          <ul className={cn("space-y-3", density === "compact" && "space-y-2")}>
            {list.map((o) => (
              <OrderCard
                key={o.id}
                o={o}
                density={density}
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
            Desk pool
          </h1>
          <p className="mt-1 max-w-xl text-sm text-muted">
            Priority items stay up top. Use the tabs below for floor presence, queues, assignment, and
            punch fixes.
          </p>
          {workingPrivilege ? (
            <p className="mt-2 text-xs text-accent">
              Working privilege on — you can Assign to me and Start work (job timers; no tech day
              clock).
              {board?.my_current
                ? ` On job: ${board.my_current.item_id || board.my_current.id || "—"}.`
                : " At desk."}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-border p-0.5">
            <button
              type="button"
              className={cn(
                "rounded-md px-2.5 py-1 text-xs",
                density === "comfortable"
                  ? "bg-accent text-accent-fg"
                  : "text-muted hover:bg-border/40",
              )}
              onClick={() => setDensity("comfortable")}
            >
              Comfortable
            </button>
            <button
              type="button"
              className={cn(
                "rounded-md px-2.5 py-1 text-xs",
                density === "compact"
                  ? "bg-accent text-accent-fg"
                  : "text-muted hover:bg-border/40",
              )}
              onClick={() => setDensity("compact")}
            >
              Compact
            </button>
          </div>
          <Button variant="secondary" disabled={busy} onClick={() => void refresh()}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        </div>
      </div>

      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {board?.source ? (
        <p className="text-xs text-muted">Source: {formatDataSource(board.source)}</p>
      ) : null}

      {/* —— Needs attention (always first) —— */}
      <div className="space-y-6 rounded-2xl border border-accent/30 bg-accent/5 p-4 sm:p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-[family-name:var(--font-display)] text-xl font-semibold tracking-tight">
            Needs attention
            {tabCounts.attention ? (
              <span className="ml-2 text-sm font-normal text-muted">· {tabCounts.attention}</span>
            ) : null}
          </h2>
        </div>

        <section className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-danger">
            Waiters &amp; urgent
            {waiterUrgentJobs.length ? ` · ${waiterUrgentJobs.length}` : ""}
          </h3>
          {waiterUrgentJobs.length === 0 ? (
            <p className="text-sm text-muted">No waiters or urgent ROs.</p>
          ) : (
            <ul className={cn("space-y-3", density === "compact" && "space-y-2")}>
              {waiterUrgentJobs.map((j) => (
                <JobCard
                  key={`att-${j.item_id || j.id}`}
                  j={j}
                  density={density}
                  actions={advisorOn ? deskJobActions(j) : undefined}
                />
              ))}
            </ul>
          )}
        </section>

        {jobSection(
          "Next-day requests",
          attentionNextDayRequests,
          "No pending next-day requests — Approve to park next day, or Decline → due EOD.",
          advisorOn ? deskJobActions : undefined,
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
                  </div>
                  {advisorOn ? foundIssueApproveActions(fi) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

        {roSection(
          "Waiting on other items",
          board?.waiting_other_items,
          "No cars with a mix of finished and still-open work.",
          advisorOn ? waitingOtherActions : undefined,
        )}

        {roSection(
          "Ready to bill",
          board?.ready_to_bill,
          "No finished jobs waiting for billing.",
          advisorOn ? readyActions : loggedIn ? readyReopenActions : undefined,
          true,
          true,
        )}

        <section className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Needed parts
              {neededParts.total ? ` · ${neededParts.total}` : ""}
            </h3>
            <Link to="/parts" className="text-xs text-accent hover:underline">
              Open parts board
            </Link>
          </div>
          {neededParts.total === 0 ? (
            <p className="text-sm text-muted">No parts waiting to order or receive.</p>
          ) : (
            <div className="space-y-4">
              {(
                [
                  ["To order", neededParts.toOrder],
                  ["On order", neededParts.onOrder],
                ] as const
              ).map(([label, list]) =>
                list.length ? (
                  <div key={label} className="space-y-2">
                    <h4 className="text-[11px] font-medium uppercase tracking-wide text-muted">
                      {label} · {list.length}
                    </h4>
                    <ul className="space-y-2">
                      {list.map((row) => {
                        const key = `${row.ro_id}:${row.part_id}`;
                        const wrongN = Number(row.wrong_count) || 0;
                        const s = (row.status || "").toLowerCase();
                        return (
                          <li
                            key={key}
                            className="rounded-xl border border-border bg-surface px-4 py-3"
                          >
                            <div className="flex flex-wrap items-start justify-between gap-2">
                              <div className="min-w-0">
                                <div className="font-medium">
                                  {row.description || row.part_number || row.part_id}
                                  {wrongN > 0 ? (
                                    <span className="ml-2 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-200">
                                      Wrong ×{wrongN}
                                    </span>
                                  ) : null}
                                </div>
                                <div className="mt-0.5 text-sm text-muted">
                                  <Link
                                    to={`/ro/${row.ro_id}`}
                                    className="text-accent hover:underline"
                                  >
                                    {row.ro_id}
                                  </Link>
                                  {row.work_item_id ? ` / ${row.work_item_id}` : ""}
                                  {row.part_number ? ` · Actual ${row.part_number}` : ""}
                                  {row.oem_part_number ? ` · OEM ${row.oem_part_number}` : ""}
                                  {row.supplier ? ` · ${row.supplier}` : ""}
                                  {row.vehicle ? ` · ${row.vehicle}` : ""}
                                </div>
                                {row.wrong_note ? (
                                  <div className="mt-1 text-xs text-amber-700 dark:text-amber-300">
                                    {row.wrong_note}
                                  </div>
                                ) : null}
                              </div>
                              {advisorOn ? (
                                <div className="flex flex-wrap gap-2">
                                  {s !== "ordered" ? (
                                    <Button
                                      type="button"
                                      size="sm"
                                      disabled={actingId === key}
                                      onClick={() => void runPartStatus(row, "ordered")}
                                    >
                                      Ordered
                                    </Button>
                                  ) : null}
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="secondary"
                                    disabled={actingId === key}
                                    onClick={() => void runPartStatus(row, "received")}
                                  >
                                    Received
                                  </Button>
                                </div>
                              ) : null}
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ) : null,
              )}
            </div>
          )}
        </section>

        {jobSection(
          "Waiting on parts",
          attentionWaitingParts,
          "No jobs waiting on a parts order.",
          advisorOn ? deskJobActions : undefined,
        )}

        {jobSection(
          "Awaiting customer approval",
          attentionWaitingCustomer,
          "No jobs waiting on customer approval.",
          advisorOn ? deskJobActions : undefined,
        )}

        {jobSection(
          "Unassigned work items",
          attentionUnassigned,
          "All open concerns have an assignee — or approve a found issue into this lane.",
          advisorOn ? unassignedDeskActions : loggedIn ? unassignedActions : undefined,
        )}
      </div>

      {/* —— Focus tabs —— */}
      <div className="sticky top-[4.5rem] z-10 -mx-1 space-y-4 bg-bg/90 px-1 py-2 backdrop-blur-md">
        <div className="flex flex-wrap gap-1">
          {(
            [
              ["floor", "Floor", tabCounts.floor],
              ["queues", "Queues", tabCounts.queues],
              ["assign", "Assign", tabCounts.assign],
              ["punches", "Punches", tabCounts.punches],
            ] as const
          ).map(([id, label, count]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-sm whitespace-nowrap",
                deskTab === id
                  ? "bg-accent text-accent-fg"
                  : "text-muted hover:bg-border/40",
              )}
            >
              {label}
              <span className="ml-1.5 opacity-80">{count}</span>
            </button>
          ))}
        </div>
      </div>

      {deskTab === "floor" ? (
        <div className="space-y-8">
<section className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
          Available techs (on the clock)
          {activeShifts.length ? ` · ${activeShifts.length}` : ""}
        </h2>
        {advisorOn ? (
          <div className="flex flex-wrap items-end gap-2 rounded-xl border border-border bg-surface px-4 py-3">
            <label className="min-w-[10rem] flex-1 text-xs text-muted">
              Clock in
              <select
                className="mt-1 flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-fg"
                value={clockInTechId}
                onChange={(e) => setClockInTechId(e.target.value)}
              >
                <option value="">Select tech…</option>
                {offClockTechs.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name || t.id}
                  </option>
                ))}
              </select>
            </label>
            {showClockInTime ? (
              <label className="text-xs text-muted">
                Start time
                <Input
                  type="datetime-local"
                  className="mt-1 h-10 min-w-[16.5rem] w-[16.5rem]"
                  value={clockInAt}
                  onChange={(e) => setClockInAt(e.target.value)}
                  autoFocus
                />
              </label>
            ) : null}
            <Button
              type="button"
              size="sm"
              variant={showClockInTime ? "secondary" : "ghost"}
              onClick={() => {
                setShowClockInTime((v) => {
                  if (v) setClockInAt("");
                  return !v;
                });
              }}
            >
              {showClockInTime ? "Use now" : "Set time"}
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={!clockInTechId || actingId?.startsWith("in:")}
              onClick={() => void clockInTech()}
            >
              Day start
            </Button>
          </div>
        ) : null}
        {activeShifts.length === 0 ? (
          <p className="text-sm text-muted">
            No technicians have day-started yet. Needs shop server for shared presence.
          </p>
        ) : (
          <ul className="space-y-2">
            {activeShifts.map((s) => {
              const working = (board?.now_working || []).find(
                (e) =>
                  e.tech_id === s.tech_id ||
                  (e.tech_name || "").toLowerCase() === (s.tech_name || "").toLowerCase(),
              );
              return (
                <li
                  key={s.id || s.tech_id || s.tech_name}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-surface px-4 py-3 text-sm"
                >
                  <div>
                    <span className="font-medium">{s.tech_name || s.tech_id}</span>
                    <span className="text-muted">
                      {" "}
                      · since {formatShopTime(s.started_at)}
                    </span>
                    {working ? (
                      <div className="mt-0.5 text-xs text-muted">
                        Working{" "}
                        <Link
                          to={`/ro/${working.order.id}`}
                          className="text-accent hover:underline"
                        >
                          {working.job?.item_id || working.item_id || working.order.id}
                        </Link>
                        {working.job?.concern ? ` — ${working.job.concern}` : ""}
                      </div>
                    ) : (
                      <div className="mt-0.5 text-xs text-muted">Available</div>
                    )}
                  </div>
                  {advisorOn ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={actingId === `out:${s.id}`}
                      onClick={() => void clockOutTech(s)}
                    >
                      Day end
                    </Button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>
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
        "Next-day requests",
        board?.defer_requests,
        "No pending next-day requests from techs.",
        advisorOn ? deskJobActions : undefined,
      )}

      {jobSection(
        workingPrivilege ? "My work (today)" : "Today (my daily queue)",
        board?.mine_daily ?? board?.mine,
        workingPrivilege
          ? "Nothing assigned to you yet — use Assign to me or Add to my queue."
          : "Nothing in today's queue for the signed-in tech session.",
        advisorOn ? deskJobActions : undefined,
      )}

      <section className="space-y-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
          Today by technician
        </h2>
        <p className="text-sm text-muted">
          Each tech&apos;s daily queue — assign or move lanes from the job row.
        </p>
        {(board?.daily_by_tech || []).length === 0 ? (
          <p className="text-sm text-muted">No daily-queue jobs assigned.</p>
        ) : (
          (board?.daily_by_tech || []).map((bucket) => (
            <div key={bucket.id || bucket.name} className="space-y-2">
              <h3 className="text-sm font-medium">{bucket.name}</h3>
              <ul className={cn("space-y-3", density === "compact" && "space-y-2")}>
                {(bucket.jobs || []).map((j) => (
                  <JobCard
                    key={`daily-${bucket.name}-${j.id}`}
                    j={j}
                    density={density}
                    actions={advisorOn ? deskJobActions(j) : undefined}
                  />
                ))}
              </ul>
            </div>
          ))
        )}
      </section>
        </div>
      ) : null}

      {deskTab === "queues" ? (
        <div className="space-y-8">
        <p className="text-sm text-muted">
          Shop-wide parking lanes: next-day rolls into daily overnight; long-term parks unassigned
          (no tech). Use Unmark long-term to put it on today&apos;s unassigned, or Back to long-term
          to park it again. Assign a tech when you plan to work it.
        </p>

        {jobSection(
          "Next day (shop)",
          board?.next_day,
          "Next-day pool is empty — push jobs here when they should wait until tomorrow.",
          advisorOn ? deskJobActions : undefined,
        )}

        {jobSection(
          "Unassigned long-term",
          board?.long_term_unassigned,
          "No unassigned long-term jobs — park multi-day work here without assigning a tech yet.",
          advisorOn ? deskJobActions : undefined,
          false,
        )}

        <section className="space-y-4">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">
            Long-term by technician
            {(board?.long_term_by_tech || []).reduce((n, b) => n + (b.jobs || []).length, 0)
              ? ` · ${(board?.long_term_by_tech || []).reduce((n, b) => n + (b.jobs || []).length, 0)}`
              : ""}
          </h2>
          <p className="text-sm text-muted">
            Each tech&apos;s parked long-term queue — assign or pull back to today from the job row.
          </p>
          {(board?.long_term_by_tech || []).length === 0 ? (
            <p className="text-sm text-muted">No long-term jobs assigned to technicians.</p>
          ) : (
            (board?.long_term_by_tech || []).map((bucket) => (
              <div key={`lt-${bucket.id || bucket.name}`} className="space-y-2">
                <h3 className="text-sm font-medium">{bucket.name}</h3>
                <ul className={cn("space-y-3", density === "compact" && "space-y-2")}>
                  {(bucket.jobs || []).map((j) => (
                    <JobCard
                      key={`lt-${bucket.name}-${j.id}`}
                      j={j}
                      density={density}
                      actions={advisorOn ? deskJobActions(j) : undefined}
                    />
                  ))}
                </ul>
              </div>
            ))
          )}
        </section>

        {jobSection(
          "Waiting on parts",
          board?.waiting_parts,
          "No jobs waiting on a parts order.",
          advisorOn ? deskJobActions : undefined,
        )}

        {jobSection(
          "Awaiting customer approval",
          board?.waiting_customer,
          "No jobs waiting on customer approval.",
          advisorOn ? deskJobActions : undefined,
        )}

        {roSection(
          "Waiting on other items",
          board?.waiting_other_items,
          "No cars with a mix of finished and still-open work.",
          advisorOn ? waitingOtherActions : undefined,
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
                  </div>
                  {advisorOn ? foundIssueApproveActions(fi) : null}
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
          advisorOn ? readyActions : loggedIn ? readyReopenActions : undefined,
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

        </div>
      ) : null}

      {deskTab === "assign" ? (
        <div className="space-y-8">
          <p className="text-sm text-muted">
            Dish work to a tech from Unassigned (or reassign from another tech). Techs can also pick
            up Unassigned items themselves on their Assigned page.
          </p>

          {jobSection(
            "Unassigned work items",
            board?.unassigned,
            "All open concerns have an assignee.",
            advisorOn ? unassignedDeskActions : loggedIn ? unassignedActions : undefined,
          )}

          <section className="space-y-4">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              On other techs
            </h2>
            {(board?.by_tech || []).length === 0 ? (
              <p className="text-sm text-muted">No work items assigned to other technicians.</p>
            ) : (
              (board?.by_tech || []).map((bucket) => (
                <div key={bucket.id || bucket.name} className="space-y-2">
                  <h3 className="text-sm font-medium">{bucket.name}</h3>
                  <ul className={cn("space-y-3", density === "compact" && "space-y-2")}>
                    {(bucket.jobs || []).map((j) => (
                      <JobCard
                        key={`${bucket.name}-${j.id}`}
                        j={j}
                        density={density}
                        actions={advisorOn ? deskJobActions(j) : undefined}
                      />
                    ))}
                  </ul>
                </div>
              ))
            )}
          </section>
        </div>
      ) : null}

      {deskTab === "punches" ? (
        <div className="space-y-8">
          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Today&apos;s punches
              {todayShifts.length ? ` · ${todayShifts.length}` : ""}
            </h2>
            <p className="text-sm text-muted">
              Fix forgotten or wrong punches — edit start/end, reopen (clear end), or delete.
            </p>
            {todayShifts.length === 0 ? (
              <p className="text-sm text-muted">No punches recorded for today yet.</p>
            ) : (
              <ul className="space-y-2">
                {todayShifts.map((s) => {
                  const editing = editingShiftId === s.id;
                  const open = !s.ended_at;
                  return (
                    <li
                      key={s.id}
                      className="rounded-xl border border-border bg-surface px-4 py-3 text-sm"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <span className="font-medium">{s.tech_name || s.tech_id}</span>
                          <span className="text-muted">
                            {" "}
                            · {formatShopTime(s.started_at)}
                            {" → "}
                            {open ? "on clock" : formatShopTime(s.ended_at || "")}
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {!editing ? (
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              onClick={() => beginEditShift(s)}
                            >
                              Edit
                            </Button>
                          ) : null}
                          {s.ended_at ? (
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              disabled={actingId === `reopen:${s.id}`}
                              onClick={() => void reopenShift(s)}
                            >
                              Reopen
                            </Button>
                          ) : null}
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            disabled={actingId === `del:${s.id}`}
                            onClick={() => void removeShift(s)}
                          >
                            Delete
                          </Button>
                        </div>
                      </div>
                      {editing ? (
                        <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-border pt-3">
                          <label className="text-xs text-muted">
                            Start
                            <Input
                              type="datetime-local"
                              className="mt-1 h-10 min-w-[16.5rem] w-[16.5rem]"
                              value={editStart}
                              onChange={(e) => setEditStart(e.target.value)}
                            />
                          </label>
                          <label className="text-xs text-muted">
                            End (blank = still open)
                            <Input
                              type="datetime-local"
                              className="mt-1 h-10 min-w-[16.5rem] w-[16.5rem]"
                              value={editEnd}
                              onChange={(e) => setEditEnd(e.target.value)}
                            />
                          </label>
                          <Button
                            type="button"
                            size="sm"
                            disabled={actingId === `edit:${s.id}`}
                            onClick={() => void saveEditShift(s)}
                          >
                            Save
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="secondary"
                            onClick={() => setEditingShiftId(null)}
                          >
                            Cancel
                          </Button>
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
}
