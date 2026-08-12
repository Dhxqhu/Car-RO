import { useCallback, useEffect, useMemo, useState, type DragEvent, type ReactNode } from "react";
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
  turnOrdinal,
} from "@/lib/utils";

const DESK_TAB_KEY = "carro-advisor-desk-tab";
const DESK_DENSITY_KEY = "carro-advisor-desk-density";
type DeskTab = "floor" | "queues" | "assign" | "punches";
type DeskDensity = "comfortable" | "compact";

type PlanDragPayload =
  | { type: "job"; ro_id: string; item_id: string }
  | {
      type: "car";
      tech_id: string;
      tech_name: string;
      lane: "daily" | "next_day";
      ro_id: string;
      index: number;
    };

type PlanDropTarget =
  | { kind: "pool" }
  | { kind: "parking"; lane: "next_day" | "long_term" }
  | { kind: "tech"; techId: string; lane: "daily" | "next_day" };

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

/** Local calendar YYYY-MM-DD for a punch timestamp (handles UTC/+0000 stamps). */
function localDayIso(iso: string | null | undefined): string {
  const raw = (iso || "").trim();
  if (!raw) return "";
  const normalized = raw.replace(/([+-]\d{2})(\d{2})$/, "$1:$2");
  const d = new Date(normalized);
  if (Number.isNaN(d.getTime())) {
    const m = raw.match(/^(\d{4}-\d{2}-\d{2})/);
    return m ? m[1] : "";
  }
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
  onCarTurn,
}: {
  j: AssignedJobSummary;
  actions?: ReactNode;
  density?: DeskDensity;
  onCarTurn?: (turn: number) => void;
}) {
  const compact = density === "compact";
  const timing = jobTiming(j);
  const waitAge = jobWaitAge(j);
  const worked = Number(j.worked_minutes) || 0;
  const req = j.next_day_request;
  const showLaneChip = !compact && j.queue_lane && j.queue_lane !== "daily";
  const showPendingLane = !compact && !!j.pending_queue_lane;
  const showNextDayReq = req?.status === "pending";

  const chip = (label: string, kind: "accent" | "danger" | "muted" = "muted") => (
    <span
      className={cn(
        "rounded font-semibold uppercase tracking-wide",
        compact ? "px-1 py-px text-[9px]" : "px-1.5 py-0.5 text-[10px]",
        kind === "accent" && "bg-accent/15 text-accent",
        kind === "danger" && "bg-danger/15 text-danger",
        kind === "muted" && "bg-border/80 font-medium text-muted",
      )}
    >
      {label}
    </span>
  );

  return (
    <li
      className={cn(
        "border border-border bg-surface",
        compact ? "rounded-md px-2 py-1" : "rounded-xl px-4 py-3",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {compact ? (
            <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs leading-snug">
              {j.waiter ? chip("Waiter", "accent") : null}
              {j.urgent ? chip("Urgent", "danger") : null}
              {j.due_eod ? chip("EOD", "danger") : null}
              {j.waiting_on_car
                ? chip(
                    `Wait · ${j.car_held_by_name || "other tech"} first`,
                    "danger",
                  )
                : null}
              {j.split_ro && j.car_turn
                ? chip(turnOrdinal(j.car_turn), "muted")
                : null}
              {showNextDayReq ? chip(req?.read_at ? "Next-day" : "Next-day · unread", "accent") : null}
              <Link to={`/ro/${j.ro_id}`} className="font-medium text-accent hover:underline">
                {j.item_id}
                <span className="font-normal text-muted"> · {j.ro_id}</span>
              </Link>
              <span className="min-w-0 truncate text-fg/90">{j.concern || "(no concern)"}</span>
              <span className="min-w-0 truncate text-muted">
                {[j.vehicle, j.customer].filter(Boolean).join(" · ")}
                {j.assigned_to_name ? ` · ${j.assigned_to_name}` : ""}
                {` · ${formatStatus(j.item_status)}`}
                {` · ${formatWorkedMinutes(worked)}`}
                {j.is_current && j.current_tech_name ? ` · Now ${j.current_tech_name}` : ""}
              </span>
            </div>
          ) : (
            <>
              {(j.waiter || j.urgent || j.due_eod || showLaneChip || showPendingLane || showNextDayReq) ? (
                <div className="mb-1 flex flex-wrap gap-1.5">
                  {j.waiter ? chip("Waiter", "accent") : null}
                  {j.urgent ? chip("Urgent", "danger") : null}
                  {j.due_eod ? chip("EOD", "danger") : null}
                  {j.waiting_on_car
                    ? chip(
                        `Wait — ${j.car_held_by_name || "another tech"} has the car first`,
                        "danger",
                      )
                    : null}
                  {j.split_ro && j.car_turn
                    ? chip(`Car ${turnOrdinal(j.car_turn)}`, "muted")
                    : null}
                  {showLaneChip
                    ? chip(j.queue_lane === "next_day" ? "Next day" : "Long-term")
                    : null}
                  {showPendingLane
                    ? chip(
                        `Push ${j.pending_queue_lane === "next_day" ? "next day" : j.pending_queue_lane} on clock-out`,
                      )
                    : null}
                  {showNextDayReq
                    ? chip(`Next-day requested${req?.read_at ? "" : " · unread"}`, "accent")
                    : null}
                </div>
              ) : null}
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
      {onCarTurn || actions ? (
        <div className={cn("flex flex-wrap items-center", compact ? "mt-1 gap-1" : "mt-3 gap-2")}>
          {onCarTurn && (j.car_turn_count || 0) > 1 ? (
            <label
              className={cn(
                "flex items-center gap-1 text-muted",
                compact ? "text-[11px]" : "text-xs",
              )}
            >
              Car turn
              <select
                className={cn(
                  "rounded-md border border-border bg-surface text-fg",
                  compact ? "h-6 px-1.5 text-[11px]" : "h-8 px-2 text-xs",
                )}
                value={j.car_turn || 1}
                onChange={(e) => onCarTurn(Number(e.target.value))}
                aria-label="Car turn"
              >
                {Array.from({ length: Math.max(1, j.car_turn_count || 1) }, (_, i) => i + 1).map(
                  (n) => (
                    <option key={n} value={n}>
                      {turnOrdinal(n)}
                    </option>
                  ),
                )}
              </select>
            </label>
          ) : null}
          {actions}
        </div>
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
        "border border-border bg-surface",
        compact ? "rounded-md px-2 py-1" : "rounded-xl px-4 py-3",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {compact ? (
            <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs leading-snug">
              <Link to={`/ro/${o.id}`} className="font-medium text-accent hover:underline">
                {o.id}
              </Link>
              <span className="truncate">{o.customer}</span>
              <span className="truncate text-muted">
                {[o.vehicle, formatStatus(o.status)].filter(Boolean).join(" · ")}
                {total > 0 ? ` · ${done}/${total} done` : ""}
                {openN > 0 ? ` · ${openN} open` : ""}
              </span>
            </div>
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
          {!compact ? <OrderWorkedBreakdown o={o} emphasize={emphasizeWorked} /> : null}
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
        <div className={cn("flex flex-wrap", compact ? "mt-1 gap-1" : "mt-3 gap-2")}>
          {actions}
        </div>
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
  const [dayPlan, setDayPlan] = useState<Awaited<ReturnType<typeof api.dayPlan>> | null>(null);
  const [sendingPlan, setSendingPlan] = useState(false);
  const [planDrag, setPlanDrag] = useState<PlanDragPayload | null>(null);
  const [planDropTarget, setPlanDropTarget] = useState<string | null>(null);

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
      const [b, who, shifts, dayShifts, roster, parts, plan] = await Promise.all([
        api.assignedBoard(),
        api.advisorWhoami().catch(() => ({ advisor: null })),
        api.shiftsActive().catch(() => ({ shifts: [] as TechShift[] })),
        // Over-fetch; filter by local start date (older UTC `day` stamps drift).
        api.listShifts({ limit: 400 }).catch(() => ({ shifts: [] as TechShift[] })),
        api.listTechs().catch(() => ({ technicians: [] as Technician[] })),
        api
          .listParts({ include_received: false, source: "auto" })
          .catch(() => ({ parts: [] as PartsSheetRow[] })),
        api.dayPlan().catch(() => null),
      ]);
      setBoard(b);
      setDayPlan(plan);
      setAdvisorOn(!!who.advisor);
      const priv =
        !!(who as { working_privilege?: boolean }).working_privilege ||
        !!who.advisor?.working_privilege;
      setWorkingPrivilege(priv);
      setAdvisorId(who.advisor?.id || "");
      setAdvisorName(who.advisor?.name || "");
      setActiveShifts(shifts.shifts || []);
      setTodayShifts(
        (dayShifts.shifts || []).filter((s) => {
          const localDay = localDayIso(s.started_at) || String(s.day || "");
          return localDay === day;
        }),
      );
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

  async function sendDayPlan(techIds?: string[]) {
    setSendingPlan(true);
    setErr("");
    try {
      const res = await api.sendDayPlan(techIds);
      setDayPlan(res.view as Awaited<ReturnType<typeof api.dayPlan>>);
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not send day plan");
    } finally {
      setSendingPlan(false);
    }
  }

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
        size={density === "compact" ? "xs" : "sm"}
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
          ? btn(j.item_id, "Push next day", () => void pushJobNextDay(j))
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

  async function pushJobNextDay(j: AssignedJobSummary) {
    if (!j.item_id) return;
    setActingId(j.item_id);
    setErr("");
    const pickId = assignPick[j.item_id] || "";
    const pickTech = techs.find((t) => t.id === pickId);
    const unassigned = !(j.assigned_to_id || j.assigned_to_name);
    const willAssignBeforePush = Boolean(pickId && unassigned);
    try {
      if (willAssignBeforePush) {
        await api.assignRo(j.ro_id, {
          assigned_to_id: pickId,
          assigned_to_name: pickTech?.name || "",
          item_id: j.item_id,
        });
      }
      await api.setWorkItemQueueLane(j.ro_id, j.item_id, "next_day", true);
      setAssignPick((prev) => {
        const next = { ...prev };
        delete next[j.item_id];
        return next;
      });
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Push failed");
    } finally {
      setActingId(null);
    }
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
    const compactActs = density === "compact";
    return (
      <div
        className={cn(
          "flex flex-wrap",
          compactActs ? "items-center gap-1" : "w-full items-end gap-2",
        )}
      >
        {workingPrivilege ? (
          <>
            {!assignedToMe ? (
              <Button
                type="button"
                size={compactActs ? "xs" : "sm"}
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
        {compactActs ? (
          <select
            className="h-6 min-w-[7.5rem] rounded-md border border-border bg-surface px-1.5 text-[11px] text-fg"
            value={pick}
            onChange={(e) =>
              setAssignPick((prev) => ({ ...prev, [j.item_id]: e.target.value }))
            }
            aria-label={assigned ? "Reassign to" : "Assign to"}
          >
            <option value="">{assigned ? "Reassign…" : "Assign…"}</option>
            {techs.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name || t.id}
              </option>
            ))}
          </select>
        ) : (
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
        )}
        <label
          className={cn(
            "flex cursor-pointer items-center gap-1.5 text-muted",
            compactActs ? "text-[11px]" : "pb-2 text-xs",
          )}
        >
          <input
            type="checkbox"
            className={cn(
              "accent-[var(--accent)]",
              compactActs ? "h-3.5 w-3.5" : "h-4 w-4",
            )}
            checked={dueEod}
            onChange={(e) =>
              setDueEodPick((prev) => ({ ...prev, [j.item_id]: e.target.checked }))
            }
          />
          {compactActs ? "EOD" : "Done by EOD"}
        </label>
        <Button
          type="button"
          size={compactActs ? "xs" : "sm"}
          disabled={!pick || actingId === `assign:${j.item_id}`}
          onClick={() => void assignItemToTech(j, pick)}
        >
          Assign
        </Button>
        {assigned ? (
          <Button
            type="button"
            size={compactActs ? "xs" : "sm"}
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
    const compactActs = density === "compact";
    return (
      <div
        className={cn(
          "flex flex-wrap",
          compactActs ? "items-center gap-1" : "w-full items-end gap-2",
        )}
      >
        {compactActs ? (
          <select
            className="h-6 min-w-[7.5rem] rounded-md border border-border bg-surface px-1.5 text-[11px] text-fg"
            value={pick}
            onChange={(e) =>
              setFiApprovePick((prev) => ({ ...prev, [fi.id]: e.target.value }))
            }
            aria-label="Assign to (optional)"
          >
            <option value="">Tech…</option>
            {techs.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name || t.id}
              </option>
            ))}
          </select>
        ) : (
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
        )}
        {btn(
          `fi-unass:${fi.id}`,
          compactActs ? "→ Unassigned" : "Approve → Unassigned",
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
          size={compactActs ? "xs" : "sm"}
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
          {compactActs ? "→ Assign" : "Approve → Assign"}
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
      <div
        className={cn(
          "flex flex-wrap",
          density === "compact" ? "items-center gap-1" : "w-full items-end gap-2",
        )}
      >
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
        (board?.needs_work_item || []).length +
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

  const planPoolJobs = useMemo(
    () =>
      (board?.unassigned || []).filter((j) => {
        const lane = (j.queue_lane || "daily").toLowerCase();
        return lane !== "long_term" && lane !== "next_day";
      }),
    [board?.unassigned],
  );

  const planTechBuckets = useMemo(() => {
    const map = new Map<
      string,
      { id: string; name: string; daily: AssignedJobSummary[]; next: AssignedJobSummary[] }
    >();
    for (const t of techs) {
      if (!t.id) continue;
      map.set(t.id, { id: t.id, name: t.name, daily: [], next: [] });
    }
    for (const b of board?.daily_by_tech || []) {
      const key = b.id || b.name;
      const existing = map.get(key);
      if (existing) existing.daily = b.jobs || [];
      else {
        map.set(key, {
          id: b.id,
          name: b.name,
          daily: b.jobs || [],
          next: [],
        });
      }
    }
    for (const b of board?.next_day_by_tech || []) {
      const key = b.id || b.name;
      const existing = map.get(key);
      if (existing) existing.next = b.jobs || [];
      else {
        map.set(key, {
          id: b.id,
          name: b.name,
          daily: [],
          next: b.jobs || [],
        });
      }
    }
    return [...map.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [techs, board?.daily_by_tech, board?.next_day_by_tech]);

  const stagedByItem = useMemo(() => {
    const map = new Map<
      string,
      NonNullable<Awaited<ReturnType<typeof api.dayPlan>>["staged"]>[number]
    >();
    for (const row of dayPlan?.staged || []) {
      map.set(`${row.ro_id}:${row.item_id}`, row);
    }
    return map;
  }, [dayPlan?.staged]);

  const stagedCount = dayPlan?.staged_count ?? (dayPlan?.staged || []).length;


  async function runCarTurn(j: AssignedJobSummary, turn: number) {
    setActingId(`turn:${j.item_id}`);
    setErr("");
    try {
      await api.setWorkItemCarTurn(j.ro_id, j.item_id, turn);
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not set car turn");
    } finally {
      setActingId(null);
    }
  }

  async function restackTechQueue(
    techId: string,
    techName: string,
    lane: "daily" | "next_day",
    groups: QueueCarGroup[],
    fromIdx: number,
    toIdx: number,
  ) {
    if (toIdx < 0 || toIdx >= groups.length || fromIdx === toIdx) return;
    const next = [...groups];
    const [moved] = next.splice(fromIdx, 1);
    next.splice(toIdx, 0, moved);
    setActingId(`q:${techId}:${lane}`);
    setErr("");
    try {
      await api.setTechQueue(
        techId || techName,
        lane,
        next.map((g) => g.ro_id),
        techName,
      );
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not reorder queue");
    } finally {
      setActingId(null);
    }
  }

  async function jumpTechQueue(
    techId: string,
    techName: string,
    lane: "daily" | "next_day",
    groups: QueueCarGroup[],
    fromIdx: number,
    dest: number,
  ) {
    const toIdx = Math.max(0, Math.min(groups.length - 1, dest - 1));
    await restackTechQueue(techId, techName, lane, groups, fromIdx, toIdx);
  }

  async function moveCarLane(j: AssignedJobSummary, lane: "daily" | "next_day" | "long_term") {
    setActingId(`lane:${j.ro_id}`);
    setErr("");
    try {
      await api.setWorkItemQueueLane(j.ro_id, j.item_id, lane, lane === "next_day");
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not move car");
    } finally {
      setActingId(null);
    }
  }

  async function planStageLane(
    j: AssignedJobSummary,
    lane: "daily" | "next_day",
    techId?: string,
  ) {
    const pickId = techId || assignPick[j.item_id] || "";
    if (!j.item_id || !pickId) return;
    const tech = techs.find((t) => t.id === pickId);
    const acting = lane === "daily" ? `plan-today:${j.item_id}` : `plan-nd:${j.item_id}`;
    setActingId(acting);
    setErr("");
    try {
      const res = await api.stageDayPlan({
        ro_id: j.ro_id,
        item_id: j.item_id,
        tech_id: pickId,
        tech_name: tech?.name || "",
        lane,
        concern: j.concern || "",
        vehicle: j.vehicle || "",
        customer: j.customer || "",
      });
      setDayPlan(res.view as Awaited<ReturnType<typeof api.dayPlan>>);
      // Keep tech selected so Plan today/tomorrow stay usable and show choice.
      setAssignPick((prev) => ({ ...prev, [j.item_id]: pickId }));
      const plan = await api.dayPlan().catch(() => null);
      if (plan) setDayPlan(plan);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not stage day plan");
    } finally {
      setActingId(null);
    }
  }

  async function planAssignToday(j: AssignedJobSummary, techId?: string) {
    await planStageLane(j, "daily", techId);
  }

  async function planAssignNextDay(j: AssignedJobSummary, techId?: string) {
    await planStageLane(j, "next_day", techId);
  }

  async function planUnstage(j: { ro_id: string; item_id: string }) {
    if (!j.item_id) return;
    setActingId(`unstage:${j.item_id}`);
    setErr("");
    try {
      const res = await api.unstageDayPlan({ ro_id: j.ro_id, item_id: j.item_id });
      setDayPlan(res.view as Awaited<ReturnType<typeof api.dayPlan>>);
      const plan = await api.dayPlan().catch(() => null);
      if (plan) setDayPlan(plan);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not unstage");
    } finally {
      setActingId(null);
    }
  }

  async function planParkUnassignedNextDay(j: AssignedJobSummary) {
    if (!j.item_id) return;
    setActingId(`plan-park-nd:${j.item_id}`);
    setErr("");
    try {
      if (j.assigned_to_id || j.assigned_to_name) {
        await api.assignRo(j.ro_id, {
          assigned_to_id: "",
          assigned_to_name: "",
          item_id: j.item_id,
        });
      }
      await api.setWorkItemQueueLane(j.ro_id, j.item_id, "next_day", true);
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Park next day failed");
    } finally {
      setActingId(null);
    }
  }

  async function planParkLongTerm(j: AssignedJobSummary) {
    if (!j.item_id) return;
    setActingId(`plan-lt:${j.item_id}`);
    setErr("");
    try {
      await api.setWorkItemQueueLane(j.ro_id, j.item_id, "long_term");
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Park long-term failed");
    } finally {
      setActingId(null);
    }
  }

  async function planReturnToPool(j: AssignedJobSummary) {
    if (!j.item_id) return;
    setActingId(`plan-pool:${j.item_id}`);
    setErr("");
    try {
      if (j.assigned_to_id || j.assigned_to_name) {
        await api.assignRo(j.ro_id, {
          assigned_to_id: "",
          assigned_to_name: "",
          item_id: j.item_id,
        });
      }
      await api.setWorkItemQueueLane(j.ro_id, j.item_id, "daily");
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Return to pool failed");
    } finally {
      setActingId(null);
    }
  }

  function onPlanDragStart(e: DragEvent, payload: PlanDragPayload) {
    e.dataTransfer.setData("application/x-carro-plan", JSON.stringify(payload));
    e.dataTransfer.effectAllowed = "move";
    setPlanDrag(payload);
  }

  function onPlanDragEnd() {
    setPlanDrag(null);
    setPlanDropTarget(null);
  }

  function readPlanDrag(e: DragEvent): PlanDragPayload | null {
    try {
      const raw = e.dataTransfer.getData("application/x-carro-plan");
      if (!raw) return planDrag;
      return JSON.parse(raw) as PlanDragPayload;
    } catch {
      return planDrag;
    }
  }

  async function handlePlanDrop(target: PlanDropTarget, e: DragEvent) {
    e.preventDefault();
    const payload = readPlanDrag(e);
    setPlanDropTarget(null);
    setPlanDrag(null);
    if (!payload) return;

    if (payload.type === "car") {
      if (target.kind !== "tech" || target.lane !== payload.lane || target.techId !== payload.tech_id) {
        return;
      }
      return;
    }

    const job =
      (board?.unassigned || []).find((j) => j.item_id === payload.item_id) ||
      (board?.next_day_unassigned || []).find((j) => j.item_id === payload.item_id) ||
      (board?.long_term_unassigned || []).find((j) => j.item_id === payload.item_id) ||
      (board?.long_term || []).find((j) => j.item_id === payload.item_id) ||
      [...(board?.daily_by_tech || []), ...(board?.next_day_by_tech || [])]
        .flatMap((b) => b.jobs || [])
        .find((j) => j.item_id === payload.item_id);
    if (!job) return;

    if (target.kind === "pool") {
      await planReturnToPool(job);
      return;
    }
    if (target.kind === "parking") {
      if (target.lane === "next_day") await planParkUnassignedNextDay(job);
      else await planParkLongTerm(job);
      return;
    }
    if (target.kind === "tech") {
      if (target.lane === "daily") await planAssignToday(job, target.techId);
      else await planAssignNextDay(job, target.techId);
    }
  }

  function planDropProps(target: PlanDropTarget) {
    const key =
      target.kind === "tech"
        ? `tech:${target.techId}:${target.lane}`
        : target.kind === "parking"
          ? `parking:${target.lane}`
          : "pool";
    const active = planDropTarget === key;
    return {
      onDragOver: (e: DragEvent) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setPlanDropTarget(key);
      },
      onDragLeave: () => {
        setPlanDropTarget((cur) => (cur === key ? null : cur));
      },
      onDrop: (e: DragEvent) => void handlePlanDrop(target, e),
      className: cn(
        "rounded-lg border border-dashed transition-colors",
        active ? "border-accent bg-accent/10" : "border-transparent",
      ),
    };
  }

  function planJobControls(j: AssignedJobSummary, opts?: { fromParking?: boolean }) {
    const staged = stagedByItem.get(`${j.ro_id}:${j.item_id}`);
    const pick = assignPick[j.item_id] || staged?.tech_id || "";
    const compact = density === "compact";
    const stagedToday = staged?.lane === "daily";
    const stagedTomorrow = staged?.lane === "next_day";
    return (
      <div className={cn("flex flex-wrap items-center", compact ? "gap-1" : "gap-2")}>
        <select
          className={cn(
            "rounded-md border border-border bg-surface text-fg",
            compact ? "h-7 max-w-[9rem] px-1 text-[11px]" : "h-8 max-w-[12rem] px-2 text-xs",
          )}
          value={pick}
          onChange={(e) =>
            setAssignPick((prev) => ({ ...prev, [j.item_id]: e.target.value }))
          }
          aria-label={`Tech for ${j.item_id}`}
        >
          <option value="">Select tech…</option>
          {techs.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
        <Button
          type="button"
          size={compact ? "xs" : "sm"}
          variant={stagedTomorrow ? "secondary" : "default"}
          disabled={!pick || actingId === `plan-today:${j.item_id}`}
          onClick={() => void planAssignToday(j)}
          aria-pressed={stagedToday}
        >
          {stagedToday ? (compact ? "Today ✓" : "Planned today") : compact ? "Plan today" : "Plan today"}
        </Button>
        <Button
          type="button"
          size={compact ? "xs" : "sm"}
          variant={stagedTomorrow ? "default" : "secondary"}
          disabled={!pick || actingId === `plan-nd:${j.item_id}`}
          onClick={() => void planAssignNextDay(j)}
          aria-pressed={stagedTomorrow}
        >
          {stagedTomorrow
            ? compact
              ? "Tomorrow ✓"
              : "Planned tomorrow"
            : compact
              ? "Plan tomorrow"
              : "Plan tomorrow"}
        </Button>
        {staged ? (
          <span className="inline-flex items-center gap-1 rounded border border-accent/30 bg-accent/10 px-1.5 py-0.5 text-[11px] text-accent">
            Planned · {staged.tech_name || "tech"} ·{" "}
            {staged.lane === "next_day" ? "Tomorrow" : "Today"}
            <button
              type="button"
              className="underline disabled:opacity-50"
              disabled={actingId === `unstage:${j.item_id}`}
              onClick={() => void planUnstage(j)}
            >
              Unstage
            </button>
          </span>
        ) : null}
        {!opts?.fromParking ? (
          <>
            <Button
              type="button"
              size={compact ? "xs" : "sm"}
              variant="ghost"
              disabled={actingId === `plan-park-nd:${j.item_id}`}
              onClick={() => void planParkUnassignedNextDay(j)}
            >
              {compact ? "Park ND" : "→ Unassigned ND"}
            </Button>
            <Button
              type="button"
              size={compact ? "xs" : "sm"}
              variant="ghost"
              disabled={actingId === `plan-lt:${j.item_id}`}
              onClick={() => void planParkLongTerm(j)}
            >
              {compact ? "LT" : "Long-term"}
            </Button>
          </>
        ) : (
          <Button
            type="button"
            size={compact ? "xs" : "sm"}
            variant="ghost"
            disabled={actingId === `plan-pool:${j.item_id}`}
            onClick={() => void planReturnToPool(j)}
          >
            {compact ? "Pool" : "Back to pool"}
          </Button>
        )}
      </div>
    );
  }

  function queuePathList(
    title: string,
    jobs: AssignedJobSummary[] | undefined,
    empty: string,
    techId: string,
    techName: string,
    lane: "daily" | "next_day",
    actionFor?: (j: AssignedJobSummary) => ReactNode,
  ) {
    const groups = groupJobsByCar(jobs);
    const compact = density === "compact";
    return (
      <div className={compact ? "space-y-1" : "space-y-2"}>
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted">
          {title}
          {groups.length ? ` · ${groups.length}` : ""}
        </h4>
        {groups.length === 0 ? (
          <p className="text-sm text-muted">{empty}</p>
        ) : (
          <ol className={compact ? "space-y-1" : "space-y-2"}>
            {groups.map((g, idx) => {
              const n = g.queue_order || idx + 1;
              const first = g.jobs[0];
              return (
                <li
                  key={`${lane}-${g.ro_id}`}
                  className={cn(
                    "border border-border bg-surface",
                    compact ? "rounded-md px-2 py-1.5" : "rounded-xl px-3 py-2.5",
                  )}
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                        <span className="font-semibold tabular-nums text-accent">#{n}</span>
                        <Link
                          to={`/ro/${g.ro_id}`}
                          className="font-medium text-accent hover:underline"
                        >
                          {g.ro_id}
                        </Link>
                        <span className="text-sm text-fg/90">
                          {g.vehicle}
                          {g.customer ? ` · ${g.customer}` : ""}
                        </span>
                        {g.waiter ? (
                          <span className="rounded bg-accent/15 px-1 py-px text-[9px] font-semibold uppercase tracking-wide text-accent">
                            Waiter
                          </span>
                        ) : null}
                        {g.urgent ? (
                          <span className="rounded bg-danger/15 px-1 py-px text-[9px] font-semibold uppercase tracking-wide text-danger">
                            Urgent
                          </span>
                        ) : null}
                      </div>
                      <ul className={cn("mt-1 text-sm", compact ? "space-y-0.5" : "space-y-1")}>
                        {g.jobs.map((j) => (
                          <li key={j.id} className="flex flex-wrap items-baseline gap-x-2">
                            <span className="font-medium">{j.item_id}</span>
                            <span className="text-fg/90">{j.concern || "(no concern)"}</span>
                            <span className="text-xs text-muted">
                              {[j.item_type, formatStatus(j.item_status)]
                                .filter(Boolean)
                                .join(" · ")}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                    {advisorOn ? (
                      <div className="flex flex-wrap items-center gap-1">
                        {btn(
                          `up:${g.ro_id}`,
                          "Up",
                          () =>
                            void restackTechQueue(
                              techId,
                              techName,
                              lane,
                              groups,
                              idx,
                              idx - 1,
                            ),
                          "ghost",
                        )}
                        {btn(
                          `down:${g.ro_id}`,
                          "Down",
                          () =>
                            void restackTechQueue(
                              techId,
                              techName,
                              lane,
                              groups,
                              idx,
                              idx + 1,
                            ),
                          "ghost",
                        )}
                        <label className="flex items-center gap-1 text-[11px] text-muted">
                          #
                          <Input
                            className="h-7 w-12 px-1.5 text-xs"
                            defaultValue={String(n)}
                            inputMode="numeric"
                            onBlur={(e) => {
                              const dest = Number(e.target.value);
                              if (!dest || dest === n) return;
                              void jumpTechQueue(
                                techId,
                                techName,
                                lane,
                                groups,
                                idx,
                                dest,
                              );
                            }}
                            aria-label={`Queue number for ${g.ro_id}`}
                          />
                        </label>
                        {lane === "daily"
                          ? btn(
                              `nd:${g.ro_id}`,
                              "To next day",
                              () => void moveCarLane(first, "next_day"),
                            )
                          : btn(
                              `td:${g.ro_id}`,
                              "To today",
                              () => void moveCarLane(first, "daily"),
                            )}
                      </div>
                    ) : null}
                  </div>
                  {actionFor
                    ? g.jobs.map((j) => (
                        <div
                          key={`act-${j.id}`}
                          className={cn(
                            "flex flex-wrap items-center border-t border-border/60",
                            compact ? "mt-1 gap-1 pt-1" : "mt-2 gap-2 pt-2",
                          )}
                        >
                          <span className="text-[11px] text-muted">{j.item_id}</span>
                          {actionFor(j)}
                        </div>
                      ))
                    : null}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    );
  }

  function jobSection(
    title: string,
    items: AssignedJobSummary[] | undefined,
    empty: string,
    actionFor?: (j: AssignedJobSummary) => ReactNode,
    accent = true,
    hideWhenEmpty = false,
  ) {
    const list = items || [];
    if (hideWhenEmpty && list.length === 0) return null;
    return (
      <section className={density === "compact" ? "space-y-1.5" : "space-y-3"}>
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
          <ul className={density === "compact" ? "space-y-1" : "space-y-3"}>
            {list.map((j) => (
              <JobCard
                key={j.id}
                j={j}
                density={density}
                actions={actionFor?.(j)}
                onCarTurn={
                  advisorOn && j.split_ro
                    ? (turn) => void runCarTurn(j, turn)
                    : undefined
                }
              />
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
    hideWhenEmpty = false,
  ) {
    const list = items || [];
    if (hideWhenEmpty && list.length === 0) return null;
    return (
      <section className={density === "compact" ? "space-y-1.5" : "space-y-3"}>
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
          <ul className={density === "compact" ? "space-y-1" : "space-y-3"}>
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
    <div className={density === "compact" ? "space-y-4" : "space-y-8"}>
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
      <div
        className={cn(
          "rounded-2xl border border-accent/30 bg-accent/5",
          density === "compact" ? "space-y-3 p-3" : "space-y-6 p-4 sm:p-5",
        )}
      >
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-[family-name:var(--font-display)] text-xl font-semibold tracking-tight">
            Needs attention
            {tabCounts.attention ? (
              <span className="ml-2 text-sm font-normal text-muted">· {tabCounts.attention}</span>
            ) : null}
          </h2>
        </div>

        {tabCounts.attention === 0 ? (
          <p className="text-sm text-muted">All caught up — nothing waiting on the desk.</p>
        ) : null}

        {waiterUrgentJobs.length ? (
          <section className={density === "compact" ? "space-y-1.5" : "space-y-3"}>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-danger">
              Waiters &amp; urgent · {waiterUrgentJobs.length}
            </h3>
            <ul className={density === "compact" ? "space-y-1" : "space-y-3"}>
              {waiterUrgentJobs.map((j) => (
                <JobCard
                  key={`att-${j.item_id || j.id}`}
                  j={j}
                  density={density}
                  actions={advisorOn ? deskJobActions(j) : undefined}
                  onCarTurn={
                    advisorOn && j.split_ro
                      ? (turn) => void runCarTurn(j, turn)
                      : undefined
                  }
                />
              ))}
            </ul>
          </section>
        ) : null}

        {jobSection(
          "Next-day requests",
          attentionNextDayRequests,
          "No pending next-day requests — Approve to park next day, or Decline → due EOD.",
          advisorOn ? deskJobActions : undefined,
          true,
          true,
        )}

        {(board?.found_issues_pending || []).length ? (
          <section className={density === "compact" ? "space-y-1.5" : "space-y-3"}>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Found issues & repair requests · {(board?.found_issues_pending || []).length}
            </h2>
            <ul className={density === "compact" ? "space-y-1" : "space-y-3"}>
              {(board?.found_issues_pending || []).map((fi: FoundIssueSummary) => (
                <li
                  key={`${fi.ro_id}-${fi.id}`}
                  className={cn(
                    "border border-border bg-surface",
                    density === "compact" ? "rounded-md px-2 py-1" : "rounded-xl px-4 py-3",
                  )}
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      {density === "compact" ? (
                        <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs leading-snug">
                          <span className="text-[9px] font-semibold uppercase tracking-wide text-muted">
                            {fi.kind === "diag_complete" ? "Repair" : "Found"}
                          </span>
                          <Link
                            to={`/ro/${fi.ro_id}`}
                            className="font-medium text-accent hover:underline"
                          >
                            {fi.id}
                            <span className="font-normal text-muted"> · {fi.ro_id}</span>
                          </Link>
                          <span className="truncate">{fi.description || "(no description)"}</span>
                          <span className="truncate text-muted">
                            {[fi.vehicle, fi.customer].filter(Boolean).join(" · ")}
                            {fi.found_by ? ` · ${fi.found_by}` : ""}
                            {(fi.photo_count || 0) > 0
                              ? ` · ${fi.photo_count} photo${fi.photo_count === 1 ? "" : "s"}`
                              : ""}
                          </span>
                        </div>
                      ) : (
                        <>
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
                        </>
                      )}
                    </div>
                    {advisorOn ? foundIssueApproveActions(fi) : null}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {roSection(
          "Waiting on other items",
          board?.waiting_other_items,
          "No cars with a mix of finished and still-open work.",
          advisorOn ? waitingOtherActions : undefined,
          true,
          false,
          true,
        )}

        {roSection(
          "Ready to bill",
          board?.ready_to_bill,
          "No finished jobs waiting for billing.",
          advisorOn ? readyActions : loggedIn ? readyReopenActions : undefined,
          true,
          true,
          true,
        )}

        {neededParts.total ? (
          <section className={density === "compact" ? "space-y-1.5" : "space-y-3"}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-accent">
                Needed parts · {neededParts.total}
              </h3>
              <Link to="/parts" className="text-xs text-accent hover:underline">
                Open parts board
              </Link>
            </div>
            <div className={density === "compact" ? "space-y-2" : "space-y-4"}>
              {(
                [
                  ["To order", neededParts.toOrder],
                  ["On order", neededParts.onOrder],
                ] as const
              ).map(([label, list]) =>
                list.length ? (
                  <div key={label} className={density === "compact" ? "space-y-1" : "space-y-2"}>
                    <h4 className="text-[11px] font-medium uppercase tracking-wide text-muted">
                      {label} · {list.length}
                    </h4>
                    <ul className={density === "compact" ? "space-y-1" : "space-y-2"}>
                      {list.map((row) => {
                        const key = `${row.ro_id}:${row.part_id}`;
                        const wrongN = Number(row.wrong_count) || 0;
                        const s = (row.status || "").toLowerCase();
                        return (
                          <li
                            key={key}
                            className={cn(
                              "border border-border bg-surface",
                              density === "compact"
                                ? "rounded-md px-2 py-1"
                                : "rounded-xl px-4 py-3",
                            )}
                          >
                            <div className="flex flex-wrap items-start justify-between gap-2">
                              <div className="min-w-0">
                                {density === "compact" ? (
                                  <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs leading-snug">
                                    <span className="font-medium">
                                      {row.description || row.part_number || row.part_id}
                                    </span>
                                    {wrongN > 0 ? (
                                      <span className="rounded bg-amber-500/15 px-1 py-px text-[9px] font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-200">
                                        Wrong ×{wrongN}
                                      </span>
                                    ) : null}
                                    <span className="truncate text-muted">
                                      <Link
                                        to={`/ro/${row.ro_id}`}
                                        className="text-accent hover:underline"
                                      >
                                        {row.ro_id}
                                      </Link>
                                      {row.work_item_id ? ` / ${row.work_item_id}` : ""}
                                      {row.part_number ? ` · ${row.part_number}` : ""}
                                      {row.supplier ? ` · ${row.supplier}` : ""}
                                      {row.vehicle ? ` · ${row.vehicle}` : ""}
                                    </span>
                                  </div>
                                ) : (
                                  <>
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
                                  </>
                                )}
                                {row.wrong_note ? (
                                  <div className="mt-0.5 text-xs text-amber-700 dark:text-amber-300">
                                    {row.wrong_note}
                                  </div>
                                ) : null}
                              </div>
                              {advisorOn ? (
                                <div
                                  className={cn(
                                    "flex flex-wrap",
                                    density === "compact" ? "gap-1" : "gap-2",
                                  )}
                                >
                                  {s !== "ordered" ? (
                                    <Button
                                      type="button"
                                      size={density === "compact" ? "xs" : "sm"}
                                      disabled={actingId === key}
                                      onClick={() => void runPartStatus(row, "ordered")}
                                    >
                                      Ordered
                                    </Button>
                                  ) : null}
                                  <Button
                                    type="button"
                                    size={density === "compact" ? "xs" : "sm"}
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
          </section>
        ) : null}

        {jobSection(
          "Waiting on parts",
          attentionWaitingParts,
          "No jobs waiting on a parts order.",
          advisorOn ? deskJobActions : undefined,
          true,
          true,
        )}

        {jobSection(
          "Awaiting customer approval",
          attentionWaitingCustomer,
          "No jobs waiting on customer approval.",
          advisorOn ? deskJobActions : undefined,
          true,
          true,
        )}

        {roSection(
          "Needs a work item",
          board?.needs_work_item,
          "Every open RO has at least one concern.",
          (o) => (
            <Link
              to={`/ro/${o.id}`}
              className="inline-flex h-8 items-center justify-center rounded-lg border border-border bg-surface px-3 text-xs font-medium hover:bg-border/40"
            >
              Open RO — add concern
            </Link>
          ),
          true,
          false,
          true,
        )}

        {jobSection(
          "Unassigned work items",
          attentionUnassigned,
          "All open concerns have an assignee — or approve a found issue into this lane.",
          advisorOn ? unassignedDeskActions : loggedIn ? unassignedActions : undefined,
          true,
          true,
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
        <div className={density === "compact" ? "space-y-4" : "space-y-8"}>
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

      <section className={density === "compact" ? "space-y-1.5" : "space-y-3"}>
        {queuePathList(
          workingPrivilege ? "My work (today)" : "Today (my daily queue)",
          board?.mine_daily ?? board?.mine,
          workingPrivilege
            ? "Nothing assigned to you yet — use Assign to me or Add to my queue."
            : "Nothing in today's queue for the signed-in tech session.",
          board?.tech_id || "",
          board?.tech_name || "",
          "daily",
          advisorOn ? deskJobActions : undefined,
        )}
      </section>

      <section className="space-y-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
          By technician
        </h2>
        <p className="text-sm text-muted">
          Numbered work path per tech — one number per car, items listed under it. Reorder
          cars or send the whole car to next day / today.
        </p>
        {!(board?.daily_by_tech || []).length && !(board?.next_day_by_tech || []).length ? (
          <p className="text-sm text-muted">No daily or next-day jobs assigned.</p>
        ) : (
          Array.from(
            (() => {
              const map = new Map<
                string,
                { id: string; name: string; daily: AssignedJobSummary[]; next: AssignedJobSummary[] }
              >();
              for (const b of board?.daily_by_tech || []) {
                map.set(b.id || b.name, {
                  id: b.id,
                  name: b.name,
                  daily: b.jobs || [],
                  next: [],
                });
              }
              for (const b of board?.next_day_by_tech || []) {
                const key = b.id || b.name;
                const existing = map.get(key);
                if (existing) existing.next = b.jobs || [];
                else {
                  map.set(key, {
                    id: b.id,
                    name: b.name,
                    daily: [],
                    next: b.jobs || [],
                  });
                }
              }
              return map.values();
            })(),
          )
            .sort((a, b) => a.name.localeCompare(b.name))
            .map((bucket) => (
              <div key={bucket.id || bucket.name} className="space-y-3">
                <h3 className="text-sm font-medium">{bucket.name}</h3>
                {queuePathList(
                  "Today",
                  bucket.daily,
                  "Nothing in today's queue.",
                  bucket.id,
                  bucket.name,
                  "daily",
                  advisorOn ? deskJobActions : undefined,
                )}
                {queuePathList(
                  "Next day",
                  bucket.next,
                  "Nothing parked for tomorrow.",
                  bucket.id,
                  bucket.name,
                  "next_day",
                  advisorOn ? deskJobActions : undefined,
                )}
              </div>
            ))
        )}
      </section>
        </div>
      ) : null}

      {deskTab === "queues" ? (
        <div className={density === "compact" ? "space-y-4" : "space-y-8"}>
        {advisorOn ? (
          <section className="space-y-3 rounded-lg border border-border/80 bg-panel/40 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
                  Day plan notify
                </h2>
                <p className="mt-1 max-w-xl text-sm text-muted">
                  Step 1: pick a tech and press <span className="font-medium text-fg">Plan today</span>{" "}
                  or <span className="font-medium text-fg">Plan tomorrow</span> (item stays unassigned
                  until send). Step 2: press{" "}
                  <span className="font-medium text-fg">Send day plan</span> — assigns staged work,
                  then one message per tech. Today goes out now; Next day waits until{" "}
                  {dayPlan?.next_day_notify_hour ?? 8}:00 AM.
                </p>
              </div>
              <button
                type="button"
                className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg disabled:opacity-50"
                disabled={
                  sendingPlan ||
                  !dayPlan ||
                  ((dayPlan.dirty || []).length === 0 && stagedCount === 0)
                }
                onClick={() => void sendDayPlan()}
                title="Apply staged plans and notify techs"
              >
                {sendingPlan
                  ? "Sending…"
                  : stagedCount || (dayPlan?.dirty || []).length
                    ? `Send day plan (${stagedCount + (dayPlan?.dirty || []).length})`
                    : "Send day plan"}
              </button>
            </div>
            {!dayPlan ? (
              <p className="text-sm text-danger">
                Day plan status unavailable — confirm you are logged in as an advisor, then Refresh.
              </p>
            ) : (dayPlan.dirty || []).length === 0 && stagedCount === 0 ? (
              <p className="text-sm text-muted">
                {(dayPlan.pending_next_day || []).length
                  ? "No new changes — next-day plans are already queued for 8:00 AM. Use Send plan on a tech below to update or re-notify."
                  : planPoolJobs.length
                    ? "Nothing staged yet. In the pool: pick a tech → Plan today / Plan tomorrow, then Send day plan."
                    : "No unsent plan changes. Stage work from the pool, or use Send plan on a tech who already has a Today / Next day path."}
              </p>
            ) : (
              <ul className="space-y-2 text-sm">
                {stagedCount > 0 ? (
                  <li className="text-xs text-muted">
                    Staged (unsent): {stagedCount} item{stagedCount === 1 ? "" : "s"} — Send applies
                    them onto tech queues, then notifies.
                  </li>
                ) : null}
                {(dayPlan.dirty || []).map((d) => (
                  <li
                    key={d.tech_id}
                    className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-2 last:border-0"
                  >
                    <div>
                      <div className="font-medium">{d.tech_name}</div>
                      <div className="text-xs text-muted">
                        {d.daily_changed
                          ? `Today · ${d.daily.length} car${d.daily.length === 1 ? "" : "s"} · notify now`
                          : null}
                        {d.daily_changed && d.next_day_changed ? " · " : null}
                        {d.next_day_changed
                          ? `Next day · ${d.next_day.length} car${d.next_day.length === 1 ? "" : "s"} · 8:00 AM`
                          : null}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="rounded-md border border-accent/40 bg-accent/10 px-2.5 py-1 text-xs font-medium text-accent disabled:opacity-50"
                      disabled={sendingPlan}
                      onClick={() => void sendDayPlan([d.tech_id])}
                    >
                      Send {d.tech_name.split(" ")[0] || "tech"}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {(dayPlan?.pending_next_day || []).length > 0 ? (
              <div className="text-xs text-muted">
                Scheduled for 8:00 AM:{" "}
                {(dayPlan?.pending_next_day || [])
                  .map((p) => `${p.tech_name} (${(p.cars || []).length})`)
                  .join(" · ")}
              </div>
            ) : null}
          </section>
        ) : null}

        <section className={density === "compact" ? "space-y-2" : "space-y-3"}>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Unassigned work
              {planPoolJobs.length ? ` · ${planPoolJobs.length}` : ""}
            </h2>
            <p className="text-xs text-muted">
              Pick a tech, then Plan today or Plan tomorrow. Staging does not move the job until you
              Send day plan.
            </p>
          </div>
          <div
            {...(() => {
              const p = planDropProps({ kind: "pool" });
              return {
                onDragOver: p.onDragOver,
                onDragLeave: p.onDragLeave,
                onDrop: p.onDrop,
                className: cn(
                  density === "compact" ? "space-y-1 p-2" : "space-y-2 p-3",
                  "min-h-[3rem] border border-border bg-surface",
                  density === "compact" ? "rounded-md" : "rounded-xl",
                  planDropTarget === "pool" ? "border-accent bg-accent/10" : "",
                ),
              };
            })()}
          >
              {planPoolJobs.length === 0 ? (
              <p className="text-sm text-muted">
                No unassigned work to plan — park returns or new Needs attention items show here.
              </p>
            ) : (
              <ul className={density === "compact" ? "space-y-1" : "space-y-2"}>
                {planPoolJobs.map((j) => (
                  <li
                    key={`pool-${j.id}`}
                    draggable={advisorOn}
                    onDragStart={(e) =>
                      onPlanDragStart(e, { type: "job", ro_id: j.ro_id, item_id: j.item_id })
                    }
                    onDragEnd={onPlanDragEnd}
                    className={cn(
                      "border border-border bg-panel/30",
                      density === "compact" ? "rounded-md px-2 py-1.5" : "rounded-lg px-3 py-2",
                      advisorOn ? "cursor-grab active:cursor-grabbing" : "",
                    )}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <Link
                          to={`/ro/${j.ro_id}`}
                          className="font-medium text-accent hover:underline"
                        >
                          {j.ro_id}
                        </Link>
                        <span className="text-sm text-fg/90">
                          {" "}
                          · {j.vehicle}
                          {j.customer ? ` · ${j.customer}` : ""}
                        </span>
                        <div className="mt-0.5 text-sm">
                          <span className="font-medium">{j.item_id}</span>{" "}
                          {j.concern || "(no concern)"}
                          <span className="text-xs text-muted">
                            {" "}
                            · {[j.item_type, formatStatus(j.item_status)].filter(Boolean).join(" · ")}
                          </span>
                        </div>
                      </div>
                      {advisorOn ? planJobControls(j) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <section className={density === "compact" ? "space-y-2" : "space-y-3"}>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">Parking</h2>
          <p className="text-sm text-muted">
            Park here to pull work out of the selectable pool (unassigned next day or long-term).
          </p>
          <div className={cn("grid gap-3", density === "compact" ? "lg:grid-cols-2" : "lg:grid-cols-2")}>
            {(
              [
                {
                  key: "next_day" as const,
                  title: "Unassigned next day",
                  items: board?.next_day_unassigned || [],
                  empty: "Drop or park jobs for tomorrow without a tech.",
                },
                {
                  key: "long_term" as const,
                  title: "Long-term",
                  items: (() => {
                    const seen = new Set<string>();
                    const out: AssignedJobSummary[] = [];
                    for (const j of [
                      ...(board?.long_term_unassigned || []),
                      ...((board?.long_term_by_tech || []).flatMap((b) => b.jobs || []) ||
                        []),
                    ]) {
                      const id = j.id || `${j.ro_id}:${j.item_id}`;
                      if (seen.has(id)) continue;
                      seen.add(id);
                      out.push(j);
                    }
                    return out;
                  })(),
                  empty: "Multi-day park — removed from the day plan pool.",
                },
              ] as const
            ).map((lane) => (
              <div
                key={lane.key}
                onDragOver={(e) => {
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "move";
                  setPlanDropTarget(`parking:${lane.key}`);
                }}
                onDragLeave={() =>
                  setPlanDropTarget((cur) => (cur === `parking:${lane.key}` ? null : cur))
                }
                onDrop={(e) => void handlePlanDrop({ kind: "parking", lane: lane.key }, e)}
                className={cn(
                  "border border-border bg-surface",
                  density === "compact" ? "rounded-md p-2" : "rounded-xl p-3",
                  planDropTarget === `parking:${lane.key}`
                    ? "border-accent bg-accent/10"
                    : "border-dashed border-border/80",
                )}
              >
                <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                  {lane.title}
                  {lane.items.length ? ` · ${lane.items.length}` : ""}
                </h3>
                {lane.items.length === 0 ? (
                  <p className="mt-2 text-sm text-muted">{lane.empty}</p>
                ) : (
                  <ul className={cn("mt-2", density === "compact" ? "space-y-1" : "space-y-2")}>
                    {lane.items.map((j) => (
                      <li
                        key={`park-${lane.key}-${j.id}`}
                        draggable={advisorOn}
                        onDragStart={(e) =>
                          onPlanDragStart(e, {
                            type: "job",
                            ro_id: j.ro_id,
                            item_id: j.item_id,
                          })
                        }
                        onDragEnd={onPlanDragEnd}
                        className={cn(
                          "border border-border/70 bg-panel/20",
                          density === "compact" ? "rounded px-2 py-1" : "rounded-lg px-2.5 py-1.5",
                          advisorOn ? "cursor-grab active:cursor-grabbing" : "",
                        )}
                      >
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div className="min-w-0 text-sm">
                            <Link to={`/ro/${j.ro_id}`} className="font-medium text-accent hover:underline">
                              {j.ro_id}
                            </Link>
                            <span className="text-muted">
                              {" "}
                              · {j.vehicle} · {j.item_id}
                            </span>
                            {j.assigned_to_name ? (
                              <span className="text-muted"> · {j.assigned_to_name}</span>
                            ) : null}
                          </div>
                          {advisorOn ? planJobControls(j, { fromParking: true }) : null}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </section>

        <section className={density === "compact" ? "space-y-3" : "space-y-4"}>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
            Technicians
          </h2>
          <p className="text-sm text-muted">
            Live Today / Next day paths plus planned (unsent) staging.{" "}
            <span className="font-medium text-fg">Send plan</span> applies staged items for that tech,
            then notifies. Unfinished Today work returns to Needs attention at end of day.
          </p>
          {planTechBuckets.length === 0 ? (
            <p className="text-sm text-muted">No technicians in the roster yet.</p>
          ) : (
            <div className={density === "compact" ? "space-y-3" : "space-y-5"}>
              {planTechBuckets.map((bucket) => {
                const techStaged = (dayPlan?.staged || []).filter(
                  (s) => s.tech_id === bucket.id,
                );
                const stagedDaily = techStaged.filter((s) => s.lane !== "next_day");
                const stagedNext = techStaged.filter((s) => s.lane === "next_day");
                return (
                <div
                  key={bucket.id || bucket.name}
                  className={cn(
                    "border border-border bg-surface",
                    density === "compact" ? "space-y-2 rounded-md p-2" : "space-y-3 rounded-xl p-3",
                  )}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-sm font-medium">{bucket.name}</h3>
                    <button
                      type="button"
                      className="rounded-md border border-accent/40 bg-accent/10 px-2.5 py-1 text-xs font-medium text-accent disabled:opacity-50"
                      disabled={
                        sendingPlan ||
                        !bucket.id ||
                        (bucket.daily.length === 0 &&
                          bucket.next.length === 0 &&
                          techStaged.length === 0)
                      }
                      onClick={() => void sendDayPlan([bucket.id])}
                      title="Apply staged + notify this tech's Today / Next day plan"
                    >
                      {sendingPlan ? "Sending…" : "Send plan"}
                    </button>
                  </div>
                  {techStaged.length > 0 ? (
                    <div
                      className={cn(
                        "border border-dashed border-accent/40 bg-accent/5",
                        density === "compact" ? "rounded-md p-2" : "rounded-lg p-2.5",
                      )}
                    >
                      <h4 className="text-[11px] font-semibold uppercase tracking-wide text-accent">
                        Planned (unsent)
                        {techStaged.length ? ` · ${techStaged.length}` : ""}
                      </h4>
                      <ul
                        className={cn(
                          "mt-1.5 text-sm",
                          density === "compact" ? "space-y-1" : "space-y-1.5",
                        )}
                      >
                        {[...stagedDaily, ...stagedNext].map((s) => (
                          <li
                            key={s.key || `${s.ro_id}:${s.item_id}`}
                            className="flex flex-wrap items-center justify-between gap-2"
                          >
                            <span>
                              <Link
                                to={`/ro/${s.ro_id}`}
                                className="font-medium text-accent hover:underline"
                              >
                                {s.ro_id}
                              </Link>
                              <span className="text-muted">
                                {" "}
                                · {s.item_id}
                                {s.vehicle ? ` · ${s.vehicle}` : ""}
                                {" · "}
                                {s.lane === "next_day" ? "Tomorrow" : "Today"}
                              </span>
                            </span>
                            <button
                              type="button"
                              className="text-xs text-accent underline disabled:opacity-50"
                              disabled={actingId === `unstage:${s.item_id}`}
                              onClick={() =>
                                void planUnstage({ ro_id: s.ro_id, item_id: s.item_id })
                              }
                            >
                              Unstage
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  <div
                    onDragOver={(e) => {
                      e.preventDefault();
                      e.dataTransfer.dropEffect = "move";
                      setPlanDropTarget(`tech:${bucket.id}:daily`);
                    }}
                    onDragLeave={() =>
                      setPlanDropTarget((cur) =>
                        cur === `tech:${bucket.id}:daily` ? null : cur,
                      )
                    }
                    onDrop={(e) =>
                      void handlePlanDrop(
                        { kind: "tech", techId: bucket.id, lane: "daily" },
                        e,
                      )
                    }
                    className={cn(
                      planDropTarget === `tech:${bucket.id}:daily`
                        ? "rounded-md border border-dashed border-accent bg-accent/10 p-1"
                        : "",
                    )}
                  >
                    {queuePathList(
                      "Today",
                      bucket.daily,
                      "Nothing in today's queue — drop here or Plan today from the pool.",
                      bucket.id,
                      bucket.name,
                      "daily",
                      advisorOn
                        ? (j) => (
                            <>
                              {btn(
                                `pool:${j.item_id}`,
                                density === "compact" ? "Pool" : "Back to pool",
                                () => void planReturnToPool(j),
                                "ghost",
                              )}
                              {deskJobActions(j)}
                            </>
                          )
                        : undefined,
                    )}
                  </div>
                  <div
                    onDragOver={(e) => {
                      e.preventDefault();
                      e.dataTransfer.dropEffect = "move";
                      setPlanDropTarget(`tech:${bucket.id}:next_day`);
                    }}
                    onDragLeave={() =>
                      setPlanDropTarget((cur) =>
                        cur === `tech:${bucket.id}:next_day` ? null : cur,
                      )
                    }
                    onDrop={(e) =>
                      void handlePlanDrop(
                        { kind: "tech", techId: bucket.id, lane: "next_day" },
                        e,
                      )
                    }
                    className={cn(
                      planDropTarget === `tech:${bucket.id}:next_day`
                        ? "rounded-md border border-dashed border-accent bg-accent/10 p-1"
                        : "",
                    )}
                  >
                    {queuePathList(
                      "Next day",
                      bucket.next,
                      "Nothing for tomorrow — drop here or Plan tomorrow from the pool.",
                      bucket.id,
                      bucket.name,
                      "next_day",
                      advisorOn
                        ? (j) => (
                            <>
                              {btn(
                                `pool:${j.item_id}`,
                                density === "compact" ? "Pool" : "Back to pool",
                                () => void planReturnToPool(j),
                                "ghost",
                              )}
                              {deskJobActions(j)}
                            </>
                          )
                        : undefined,
                    )}
                  </div>
                </div>
                );
              })}
            </div>
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
          <ul className={density === "compact" ? "space-y-1" : "space-y-3"}>
            {(board?.found_issues_pending || []).map((fi: FoundIssueSummary) => (
              <li
                key={`${fi.ro_id}-${fi.id}`}
                className={cn(
                  "border border-border bg-surface",
                  density === "compact" ? "rounded-md px-2 py-1" : "rounded-xl px-4 py-3",
                )}
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
        <div className={density === "compact" ? "space-y-4" : "space-y-8"}>
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
            {!(board?.daily_by_tech || []).length && !(board?.next_day_by_tech || []).length ? (
              <p className="text-sm text-muted">No work items assigned to other technicians.</p>
            ) : (
              Array.from(
                (() => {
                  const map = new Map<
                    string,
                    {
                      id: string;
                      name: string;
                      daily: AssignedJobSummary[];
                      next: AssignedJobSummary[];
                    }
                  >();
                  for (const b of board?.daily_by_tech || []) {
                    map.set(b.id || b.name, {
                      id: b.id,
                      name: b.name,
                      daily: b.jobs || [],
                      next: [],
                    });
                  }
                  for (const b of board?.next_day_by_tech || []) {
                    const key = b.id || b.name;
                    const existing = map.get(key);
                    if (existing) existing.next = b.jobs || [];
                    else {
                      map.set(key, {
                        id: b.id,
                        name: b.name,
                        daily: [],
                        next: b.jobs || [],
                      });
                    }
                  }
                  return map.values();
                })(),
              )
                .sort((a, b) => a.name.localeCompare(b.name))
                .map((bucket) => (
                  <div key={bucket.id || bucket.name} className="space-y-3">
                    <h3 className="text-sm font-medium">{bucket.name}</h3>
                    {queuePathList(
                      "Today",
                      bucket.daily,
                      "Nothing in today's queue.",
                      bucket.id,
                      bucket.name,
                      "daily",
                      advisorOn ? deskJobActions : undefined,
                    )}
                    {queuePathList(
                      "Next day",
                      bucket.next,
                      "Nothing parked for tomorrow.",
                      bucket.id,
                      bucket.name,
                      "next_day",
                      advisorOn ? deskJobActions : undefined,
                    )}
                  </div>
                ))
            )}
          </section>
        </div>
      ) : null}

      {deskTab === "punches" ? (
        <div className={density === "compact" ? "space-y-4" : "space-y-8"}>
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
