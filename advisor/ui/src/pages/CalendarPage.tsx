import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import {
  api,
  type Appointment,
  type CalendarPartEvent,
  type CalendarPayload,
  type RepairOrder,
  type ServiceDueItem,
  type Technician,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn, formatShopClock, formatStatus } from "@/lib/utils";

const TAGS = [
  { value: "diag", label: "Diag" },
  { value: "service", label: "Service" },
  { value: "repair", label: "Repair" },
  { value: "si_im", label: "SI/IM" },
  { value: "si_only", label: "SI only" },
  { value: "other", label: "Other" },
] as const;
const PA_TAG_VALUES = new Set(["si_im", "si_only"]);
const INSPECTION_CONCERN_TEXT: Record<string, string> = {
  si_im: "State Inspection and Emissions Testing",
  si_only: "State Inspection Only",
};

function concernForTag(tag: string): string {
  return INSPECTION_CONCERN_TEXT[tag] || "";
}

function applyTagToAppointmentDraft(d: Appointment, tag: string): Appointment {
  const autoConcern = concernForTag(tag);
  const cur = (d.notes || "").trim();
  const prevAuto = concernForTag(d.tag || "");
  const next: Appointment = {
    ...d,
    tag,
    service_plan_enroll:
      tag === "si_im" || tag === "si_only" ? d.service_plan_enroll || "" : "",
  };
  if (autoConcern && (!cur || (prevAuto && cur === prevAuto))) {
    next.notes = autoConcern;
  }
  return next;
}

function visibleTags(paEnabled: boolean) {
  return TAGS.filter((t) => paEnabled || !PA_TAG_VALUES.has(t.value));
}

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;
const MONTH_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function isoDate(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function parseDay(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

function addDays(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

function startOfWeekMonday(d: Date): Date {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const day = x.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  x.setDate(x.getDate() + diff);
  return x;
}

function apptDay(a: Appointment): string {
  return (a.scheduled_at || "").slice(0, 10);
}

function apptTime(a: Appointment): string {
  if (a.all_day) return "";
  const m = (a.scheduled_at || "").match(/T(\d{2}:\d{2})/);
  return m ? m[1] : "";
}

function apptName(a: Appointment): string {
  const n = `${a.last_name || ""}, ${a.first_name || ""}`.replace(/^,\s*|,\s*$/g, "").trim();
  return n || "(no name)";
}

function apptVehicle(a: Appointment): string {
  return [a.year, a.make, a.model].filter(Boolean).join(" ").trim();
}

function tagLabel(tag?: string): string {
  const hit = TAGS.find((t) => t.value === tag);
  return hit?.label || formatStatus(tag || "other");
}

function confirmLabel(status?: string, attempts?: number): string {
  const st = (status || "").toLowerCase();
  if (st === "confirmed") return "Called · confirmed";
  if (st === "canceled") return "Called · canceled";
  if (st === "skip") return "Called · skip cycle";
  if (st === "veto_next") return "Didn't call · tomorrow";
  if (st === "veto") return "Didn't call · next cycle";
  if (st === "no_answer") {
    const n = attempts || 0;
    return n > 1 ? `Called · no answer (${n})` : "Called · no answer";
  }
  return "Not called";
}

function confirmChipClass(status?: string): string {
  const st = (status || "").toLowerCase();
  if (st === "confirmed") return "bg-emerald-500/25 text-fg";
  if (st === "canceled" || st === "skip") return "bg-rose-500/20 text-fg";
  if (st === "no_answer") return "bg-amber-500/25 text-fg";
  if (st === "veto_next" || st === "veto") return "bg-border text-muted";
  return "bg-border/60 text-muted";
}

function emptyDraft(day: string, time = ""): Appointment {
  return {
    id: "",
    scheduled_at: time ? `${day}T${time}` : day,
    all_day: !time,
    first_name: "",
    last_name: "",
    phone: "",
    year: "",
    make: "",
    model: "",
    vin: "",
    notes: "",
    tag: "other",
    requested_tech_id: "",
    requested_tech_name: "",
    prior_ro_id: "",
    service_plan_id: "",
    service_plan_line_id: "",
    service_plan_enroll: "",
    waiter: false,
    urgent: false,
    status: "scheduled",
  };
}

function fromDue(due: ServiceDueItem, day: string): Appointment {
  return {
    ...emptyDraft(day),
    first_name: due.first_name || "",
    last_name: due.last_name || "",
    phone: due.phone || "",
    year: due.year || "",
    make: due.make || "",
    model: due.model || "",
    vin: due.vin || "",
    tag: due.tag || "service",
    notes: due.notes || due.label || "",
    service_plan_id: due.plan_id,
    service_plan_line_id: due.line_id,
  };
}

function fromPrior(order: RepairOrder, day: string): Appointment {
  return {
    ...emptyDraft(day),
    first_name: order.first_name || "",
    last_name: order.last_name || "",
    phone: order.phone || "",
    year: order.year || "",
    make: order.make || "",
    model: order.model || "",
    vin: order.vin || "",
    prior_ro_id: order.id,
  };
}

type DialogState =
  | { kind: "create"; day: string; time?: string; prefill?: Appointment }
  | { kind: "edit"; appt: Appointment };

export function CalendarPage() {
  const nav = useNavigate();
  const [view, setView] = useState<"week" | "month">("week");
  const [anchor, setAnchor] = useState(() => new Date());
  const [layers, setLayers] = useState({
    appointments: true,
    ordered: true,
    received: true,
  });
  const [data, setData] = useState<CalendarPayload | null>(null);
  const [techs, setTechs] = useState<Technician[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [dialog, setDialog] = useState<DialogState | null>(null);

  const range = useMemo(() => {
    if (view === "week") {
      const mon = startOfWeekMonday(anchor);
      return { start: isoDate(mon), end: isoDate(addDays(mon, 5)) };
    }
    const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    const last = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
    return { start: isoDate(first), end: isoDate(last) };
  }, [view, anchor]);

  const load = useCallback(async () => {
    setBusy(true);
    setErr("");
    try {
      const [cal, t] = await Promise.all([
        api.calendar(range.start, range.end),
        techs.length ? Promise.resolve({ technicians: techs }) : api.listTechs(),
      ]);
      setData(cal);
      if (!techs.length) setTechs(t.technicians || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load calendar");
    } finally {
      setBusy(false);
    }
  }, [range.start, range.end, techs.length]);

  useEffect(() => {
    void load();
  }, [load]);

  function shift(dir: number) {
    if (view === "week") setAnchor((a) => addDays(a, dir * 7));
    else setAnchor((a) => new Date(a.getFullYear(), a.getMonth() + dir, 1));
  }

  const weekDays = useMemo(() => {
    const mon = startOfWeekMonday(anchor);
    return WEEKDAYS.map((_, i) => isoDate(addDays(mon, i)));
  }, [anchor]);

  const monthCells = useMemo(() => {
    const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    const last = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
    const gridStart = startOfWeekMonday(first);
    const lastSunday = addDays(startOfWeekMonday(last), 6);
    const cells: string[] = [];
    for (let d = new Date(gridStart); d <= lastSunday; d = addDays(d, 1)) {
      cells.push(isoDate(d));
    }
    return cells;
  }, [anchor]);

  const apptsByDay = useMemo(() => {
    const map = new Map<string, Appointment[]>();
    for (const a of data?.appointments || []) {
      const day = apptDay(a);
      if (!map.has(day)) map.set(day, []);
      map.get(day)!.push(a);
    }
    for (const list of map.values()) {
      list.sort((a, b) => (a.scheduled_at || "").localeCompare(b.scheduled_at || ""));
    }
    return map;
  }, [data]);

  const partsByDay = useMemo(() => {
    const map = new Map<string, CalendarPartEvent[]>();
    for (const p of data?.parts || []) {
      if (p.kind === "ordered" && !layers.ordered) continue;
      if (p.kind === "received" && !layers.received) continue;
      if (p.kind !== "ordered" && p.kind !== "received") continue;
      const day = (p.day || p.at || "").slice(0, 10);
      if (!map.has(day)) map.set(day, []);
      map.get(day)!.push(p);
    }
    return map;
  }, [data, layers.ordered, layers.received]);

  const heading =
    view === "week"
      ? `${range.start} – ${range.end}`
      : new Date(anchor.getFullYear(), anchor.getMonth(), 1).toLocaleString(undefined, {
          month: "long",
          year: "numeric",
        });

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">Calendar</h1>
        <div className="flex rounded-lg border border-border p-0.5">
          {(["week", "month"] as const).map((v) => (
            <button
              key={v}
              type="button"
              className={cn(
                "rounded-md px-3 py-1 text-xs font-medium capitalize",
                view === v ? "bg-accent text-accent-fg" : "text-muted hover:text-fg",
              )}
              onClick={() => setView(v)}
            >
              {v}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          <Button variant="secondary" size="icon" className="h-8 w-8" onClick={() => shift(-1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setAnchor(new Date())}>
            Today
          </Button>
          <Button variant="secondary" size="icon" className="h-8 w-8" onClick={() => shift(1)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <p className="text-sm text-muted">{heading}</p>
        <Button
          size="sm"
          onClick={() => setDialog({ kind: "create", day: isoDate(new Date()) })}
        >
          New appointment
        </Button>
        <div className="ml-auto flex flex-wrap items-center gap-3 text-sm">
          {(
            [
              ["appointments", "Appointments"],
              ["ordered", "Parts ordered"],
              ["received", "Parts received"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex items-center gap-1.5 text-fg">
              <input
                type="checkbox"
                checked={layers[key]}
                onChange={(e) => setLayers((l) => ({ ...l, [key]: e.target.checked }))}
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {busy && !data ? <p className="text-sm text-muted">Loading…</p> : null}

      {view === "week" ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {weekDays.map((day) => (
            <DayColumn
              key={day}
              day={day}
              weekday={WEEKDAYS[parseDay(day).getDay() === 0 ? 6 : parseDay(day).getDay() - 1]}
              appointments={layers.appointments ? apptsByDay.get(day) || [] : []}
              parts={partsByDay.get(day) || []}
              onCreate={() => setDialog({ kind: "create", day })}
              onEdit={(appt) => setDialog({ kind: "edit", appt })}
              onPart={(p) => nav(`/ro/${p.ro_id}`)}
            />
          ))}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border">
          <div className="grid min-w-[720px] grid-cols-7 border-b border-border bg-surface">
            {MONTH_WEEKDAYS.map((d) => (
              <div key={d} className="px-2 py-1.5 text-center text-xs font-semibold uppercase text-muted">
                {d}
              </div>
            ))}
          </div>
          <div className="grid min-w-[720px] grid-cols-7">
            {monthCells.map((day) => {
              const inMonth = parseDay(day).getMonth() === anchor.getMonth();
              return (
                <button
                  key={day}
                  type="button"
                  className={cn(
                    "min-h-[110px] border-b border-r border-border p-1.5 text-left align-top hover:bg-border/20",
                    !inMonth && "bg-surface/50 text-muted",
                    day === isoDate(new Date()) && "ring-1 ring-inset ring-accent/50",
                  )}
                  onClick={() => setDialog({ kind: "create", day })}
                >
                  <div className="mb-1 text-xs font-semibold">{parseDay(day).getDate()}</div>
                  <div className="space-y-0.5">
                    {layers.appointments
                      ? (apptsByDay.get(day) || []).map((a) => (
                          <div
                            key={a.id}
                            role="presentation"
                            className="truncate rounded bg-accent/15 px-1 py-0.5 text-[11px] text-fg"
                            onClick={(e) => {
                              e.stopPropagation();
                              setDialog({ kind: "edit", appt: a });
                            }}
                          >
                            {apptTime(a) ? `${apptTime(a)} ` : ""}
                            {a.waiter ? "W " : ""}
                            {a.urgent ? "! " : ""}
                            {a.confirm_status === "confirmed"
                              ? "✓ "
                              : a.confirm_status === "no_answer"
                                ? "? "
                                : ""}
                            {apptName(a)}
                          </div>
                        ))
                      : null}
                    {(partsByDay.get(day) || []).map((p) => (
                      <div
                        key={`${p.kind}-${p.ro_id}-${p.part_id}-${p.at}`}
                        role="presentation"
                        className={cn(
                          "truncate rounded px-1 py-0.5 text-[11px]",
                          p.kind === "ordered"
                            ? "bg-amber-500/20 text-fg"
                            : "bg-emerald-500/20 text-fg",
                        )}
                        onClick={(e) => {
                          e.stopPropagation();
                          nav(`/ro/${p.ro_id}`);
                        }}
                      >
                        {p.kind === "ordered" ? "Ord" : "Rcv"} {p.description || p.ro_id}
                      </div>
                    ))}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      <ServiceDueList
        items={data?.due_calls || []}
        onBook={(due) =>
          setDialog({
            kind: "create",
            day: due.next_due || isoDate(new Date()),
            prefill: fromDue(due, due.next_due || isoDate(new Date())),
          })
        }
        onCall={async (due, outcome) => {
          await api.servicePlanCall(due.plan_id, due.line_id, outcome);
          await load();
        }}
      />

      <ConfirmCallList
        tomorrow={data?.tomorrow || ""}
        tomorrowCalls={data?.tomorrow_calls || []}
        todayOpen={data?.today_open || []}
        onEdit={(appt) => setDialog({ kind: "edit", appt })}
        onConfirm={async (id, outcome) => {
          if (outcome === "delete") {
            await api.archiveAppointment(id, "canceled");
          } else {
            await api.confirmAppointment(id, outcome);
          }
          await load();
        }}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <ArchiveList
          title="Canceled"
          items={data?.canceled || []}
          onRestore={async (id) => {
            await api.restoreAppointment(id);
            await load();
          }}
          onConvert={async (id) => {
            const r = await api.convertAppointment(id);
            nav(`/ro/${r.order.id}`);
          }}
          onEdit={(appt) => setDialog({ kind: "edit", appt })}
        />
        <ArchiveList
          title="No-shows"
          items={data?.no_show || []}
          onRestore={async (id) => {
            await api.restoreAppointment(id);
            await load();
          }}
          onConvert={async (id) => {
            const r = await api.convertAppointment(id);
            nav(`/ro/${r.order.id}`);
          }}
          onEdit={(appt) => setDialog({ kind: "edit", appt })}
        />
      </div>

      {dialog ? (
        <AppointmentDialog
          state={dialog}
          techs={techs}
          onClose={() => setDialog(null)}
          onSaved={async () => {
            setDialog(null);
            await load();
          }}
          onConverted={(roId) => {
            setDialog(null);
            nav(`/ro/${roId}`);
          }}
        />
      ) : null}
    </div>
  );
}

function DayColumn({
  day,
  weekday,
  appointments,
  parts,
  onCreate,
  onEdit,
  onPart,
}: {
  day: string;
  weekday: string;
  appointments: Appointment[];
  parts: CalendarPartEvent[];
  onCreate: () => void;
  onEdit: (a: Appointment) => void;
  onPart: (p: CalendarPartEvent) => void;
}) {
  const today = day === isoDate(new Date());
  return (
    <div
      className={cn(
        "min-h-[220px] rounded-xl border border-border bg-surface p-2",
        today && "ring-1 ring-accent/40",
      )}
    >
      <button
        type="button"
        className="mb-2 flex w-full items-baseline justify-between rounded-md px-1 py-0.5 text-left hover:bg-border/30"
        onClick={onCreate}
      >
        <span className="text-xs font-semibold uppercase text-muted">{weekday}</span>
        <span className="text-sm font-medium">{parseDay(day).getDate()}</span>
      </button>
      <button
        type="button"
        className="mb-2 w-full rounded-md border border-dashed border-border px-2 py-1 text-left text-[11px] text-muted hover:border-accent/50 hover:text-fg"
        onClick={onCreate}
      >
        + Add appointment
      </button>
      <div className="space-y-1">
        {appointments.map((a) => (
          <button
            key={a.id}
            type="button"
            className="w-full rounded-lg bg-accent/15 px-2 py-1.5 text-left text-xs hover:bg-accent/25"
            onClick={() => onEdit(a)}
          >
            <div className="font-medium">
              {apptTime(a) || "All day"} · {tagLabel(a.tag)}
              {a.waiter ? " · Waiter" : ""}
              {a.urgent ? " · Urgent" : ""}
            </div>
            <div className="mb-0.5 mt-0.5">
              <span className={cn("rounded px-1 py-px text-[10px] font-medium", confirmChipClass(a.confirm_status))}>
                {confirmLabel(a.confirm_status, a.confirm_attempts)}
              </span>
            </div>
            <div className="truncate">{apptName(a)}</div>
            {apptVehicle(a) ? <div className="truncate text-muted">{apptVehicle(a)}</div> : null}
            {a.requested_tech_name ? (
              <div className="truncate text-muted">{a.requested_tech_name}</div>
            ) : null}
          </button>
        ))}
        {parts.map((p) => (
          <button
            key={`${p.kind}-${p.ro_id}-${p.part_id}-${p.at}`}
            type="button"
            className={cn(
              "w-full rounded-lg px-2 py-1.5 text-left text-xs",
              p.kind === "ordered" ? "bg-amber-500/20 hover:bg-amber-500/30" : "bg-emerald-500/20 hover:bg-emerald-500/30",
            )}
            onClick={() => onPart(p)}
          >
            <div className="font-medium">
              {p.kind === "ordered" ? "Ordered" : "Received"}
              {formatShopClock(p.at) ? ` · ${formatShopClock(p.at)}` : ""}
            </div>
            <div className="truncate">{p.description || p.ro_id}</div>
            <div className="truncate text-muted">
              {p.ro_id}
              {p.vehicle ? ` · ${p.vehicle}` : ""}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function ServiceDueList({
  items,
  onBook,
  onCall,
}: {
  items: ServiceDueItem[];
  onBook: (due: ServiceDueItem) => void;
  onCall: (
    due: ServiceDueItem,
    outcome: "confirmed" | "no_answer" | "skip" | "veto_next" | "veto",
  ) => Promise<void>;
}) {
  const [busyKey, setBusyKey] = useState("");
  return (
    <section className="rounded-xl border border-border bg-surface p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">
          Service due <span className="font-normal text-muted">({items.length})</span>
        </h2>
        <Link to="/plans" className="text-xs text-accent hover:underline">
          Edit plans
        </Link>
      </div>
      <p className="mt-0.5 text-xs text-muted">
        Call when due, then book. Veto if you did not call — tomorrow, or forget until the next cycle.
      </p>
      {!items.length ? (
        <p className="mt-3 text-sm text-muted">Nothing due in the next 30 days.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {items.map((d) => {
            const key = `${d.plan_id}-${d.line_id}`;
            return (
              <li
                key={key}
                className="flex flex-wrap items-center gap-2 rounded-lg border border-border px-2 py-1.5 text-sm"
              >
                <div className="min-w-0 flex-1">
                  <div className="font-medium">
                    {d.customer}
                    {d.overdue ? <span className="ml-1 text-xs text-danger">Overdue</span> : null}
                  </div>
                  <div className="text-muted">
                    {d.label} · due {d.next_due}
                    {d.vehicle ? ` · ${d.vehicle}` : ""}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-2">
                    <span className={cn("rounded px-1.5 py-px text-[11px] font-medium", confirmChipClass(d.call_status))}>
                      {confirmLabel(d.call_status, d.call_attempts)}
                    </span>
                    {d.phone ? (
                      <a href={`tel:${d.phone.replace(/[^\d+]/g, "")}`} className="text-xs text-accent hover:underline">
                        {d.phone}
                      </a>
                    ) : (
                      <span className="text-xs text-muted">No phone</span>
                    )}
                  </div>
                </div>
                <Button
                  size="xs"
                  variant={d.call_status === "confirmed" ? "default" : "secondary"}
                  disabled={busyKey === key}
                  onClick={async () => {
                    setBusyKey(key);
                    try {
                      await onCall(d, "confirmed");
                    } finally {
                      setBusyKey("");
                    }
                  }}
                >
                  Confirmed
                </Button>
                <Button
                  size="xs"
                  variant="secondary"
                  disabled={busyKey === key}
                  onClick={async () => {
                    setBusyKey(key);
                    try {
                      await onCall(d, "no_answer");
                    } finally {
                      setBusyKey("");
                    }
                  }}
                >
                  No answer
                </Button>
                <Button
                  size="xs"
                  variant="secondary"
                  disabled={busyKey === key}
                  onClick={async () => {
                    setBusyKey(key);
                    try {
                      await onCall(d, "skip");
                    } finally {
                      setBusyKey("");
                    }
                  }}
                >
                  Skip cycle
                </Button>
                <Button
                  size="xs"
                  variant="secondary"
                  disabled={busyKey === key}
                  onClick={async () => {
                    setBusyKey(key);
                    try {
                      await onCall(d, "veto_next");
                    } finally {
                      setBusyKey("");
                    }
                  }}
                >
                  Veto → tomorrow
                </Button>
                <Button
                  size="xs"
                  variant="secondary"
                  disabled={busyKey === key}
                  onClick={async () => {
                    setBusyKey(key);
                    try {
                      await onCall(d, "veto");
                    } finally {
                      setBusyKey("");
                    }
                  }}
                >
                  Veto till next
                </Button>
                <Button size="xs" disabled={busyKey === key} onClick={() => onBook(d)}>
                  Book
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function ConfirmCallList({
  tomorrow,
  tomorrowCalls,
  todayOpen,
  onEdit,
  onConfirm,
}: {
  tomorrow: string;
  tomorrowCalls: Appointment[];
  todayOpen: Appointment[];
  onEdit: (a: Appointment) => void;
  onConfirm: (
    id: string,
    outcome: "confirmed" | "canceled" | "no_answer" | "veto_next" | "delete",
  ) => Promise<void>;
}) {
  const pendingTomorrow = tomorrowCalls.filter((a) => (a.confirm_status || "") !== "confirmed").length;
  return (
    <section className="rounded-xl border border-border bg-surface p-3">
      <h2 className="text-sm font-semibold">Confirm calls</h2>
      <p className="mt-0.5 text-xs text-muted">
        Call the day before. Mark the outcome — or veto until tomorrow if you did not call. Delete removes the
        appointment from the calendar.
        {tomorrow ? ` Tomorrow ${tomorrow}` : ""}
        {tomorrowCalls.length
          ? ` · ${pendingTomorrow} still need a yes`
          : " · nothing booked tomorrow"}
      </p>
      <CallGroup title="Tomorrow" items={tomorrowCalls} onEdit={onEdit} onConfirm={onConfirm} />
      {todayOpen.length ? (
        <CallGroup
          title="Today — still open"
          items={todayOpen}
          onEdit={onEdit}
          onConfirm={onConfirm}
        />
      ) : null}
    </section>
  );
}

function CallGroup({
  title,
  items,
  onEdit,
  onConfirm,
}: {
  title: string;
  items: Appointment[];
  onEdit: (a: Appointment) => void;
  onConfirm: (
    id: string,
    outcome: "confirmed" | "canceled" | "no_answer" | "veto_next" | "delete",
  ) => Promise<void>;
}) {
  const [busyId, setBusyId] = useState("");
  if (!items.length) {
    return <p className="mt-3 text-sm text-muted">{title}: none</p>;
  }
  return (
    <div className="mt-3">
      <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">{title}</h3>
      <ul className="space-y-2">
        {items.map((a) => (
          <li
            key={a.id}
            className="flex flex-wrap items-center gap-2 rounded-lg border border-border px-2 py-1.5 text-sm"
          >
            <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onEdit(a)}>
              <span className="font-medium">{apptName(a)}</span>
              <span className="text-muted">
                {" "}
                · {apptTime(a) || "All day"}
                {apptVehicle(a) ? ` · ${apptVehicle(a)}` : ""}
                {a.waiter ? " · Waiter" : ""}
                {a.urgent ? " · Urgent" : ""}
              </span>
              <div className="mt-0.5 flex flex-wrap items-center gap-2">
                <span className={cn("rounded px-1.5 py-px text-[11px] font-medium", confirmChipClass(a.confirm_status))}>
                  {confirmLabel(a.confirm_status, a.confirm_attempts)}
                </span>
                {a.phone ? (
                  <a
                    href={`tel:${a.phone.replace(/[^\d+]/g, "")}`}
                    className="text-xs text-accent hover:underline"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {a.phone}
                  </a>
                ) : (
                  <span className="text-xs text-muted">No phone</span>
                )}
              </div>
            </button>
            {(["confirmed", "no_answer", "canceled", "veto_next", "delete"] as const).map((outcome) => (
              <Button
                key={outcome}
                size="xs"
                variant={a.confirm_status === outcome ? "default" : "secondary"}
                disabled={busyId === a.id}
                onClick={async () => {
                  setBusyId(a.id);
                  try {
                    await onConfirm(a.id, outcome);
                  } finally {
                    setBusyId("");
                  }
                }}
              >
                {outcome === "confirmed"
                  ? "Confirmed"
                  : outcome === "no_answer"
                    ? "No answer"
                    : outcome === "canceled"
                      ? "Canceled"
                      : outcome === "veto_next"
                        ? "Veto → tomorrow"
                        : "Delete"}
              </Button>
            ))}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ArchiveList({
  title,
  items,
  onRestore,
  onConvert,
  onEdit,
}: {
  title: string;
  items: Appointment[];
  onRestore: (id: string) => Promise<void>;
  onConvert: (id: string) => Promise<void>;
  onEdit: (a: Appointment) => void;
}) {
  const [busyId, setBusyId] = useState("");
  return (
    <section className="rounded-xl border border-border bg-surface p-3">
      <h2 className="mb-2 text-sm font-semibold">
        {title} <span className="font-normal text-muted">({items.length})</span>
      </h2>
      {!items.length ? (
        <p className="text-sm text-muted">None</p>
      ) : (
        <ul className="space-y-2">
          {items.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-border px-2 py-1.5 text-sm">
              <button type="button" className="min-w-0 flex-1 text-left hover:underline" onClick={() => onEdit(a)}>
                <span className="font-medium">{apptName(a)}</span>
                <span className="text-muted">
                  {" "}
                  · {apptDay(a)}
                  {apptVehicle(a) ? ` · ${apptVehicle(a)}` : ""}
                </span>
              </button>
              <Button
                size="xs"
                variant="secondary"
                disabled={busyId === a.id}
                onClick={async () => {
                  setBusyId(a.id);
                  try {
                    await onRestore(a.id);
                  } finally {
                    setBusyId("");
                  }
                }}
              >
                Restore to calendar
              </Button>
              <Button
                size="xs"
                disabled={busyId === a.id}
                onClick={async () => {
                  setBusyId(a.id);
                  try {
                    await onConvert(a.id);
                  } finally {
                    setBusyId("");
                  }
                }}
              >
                Make work order
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function AppointmentDialog({
  state,
  techs,
  onClose,
  onSaved,
  onConverted,
}: {
  state: DialogState;
  techs: Technician[];
  onClose: () => void;
  onSaved: () => Promise<void>;
  onConverted: (roId: string) => void;
}) {
  const initial =
    state.kind === "edit"
      ? state.appt
      : { ...emptyDraft(state.day, state.time), ...(state.prefill || {}) };
  const [draft, setDraft] = useState<Appointment>(initial);
  const [date, setDate] = useState(apptDay(initial) || isoDate(new Date()));
  const [time, setTime] = useState(apptTime(initial));
  const [allDay, setAllDay] = useState(Boolean(initial.all_day) || !apptTime(initial));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [histVin, setHistVin] = useState("");
  const [histName, setHistName] = useState("");
  const [hits, setHits] = useState<RepairOrder[]>([]);
  const [histNote, setHistNote] = useState("");
  const [paInspectionTypes, setPaInspectionTypes] = useState(true);

  useEffect(() => {
    void api
      .getConfig()
      .then((c) => setPaInspectionTypes(c.pa_inspection_types !== false))
      .catch(() => undefined);
  }, []);

  function schedulePayload(): { scheduled_at: string; all_day: boolean } {
    if (allDay || !time.trim()) {
      return { scheduled_at: date, all_day: true };
    }
    return { scheduled_at: `${date}T${time}`, all_day: false };
  }

  async function save() {
    setBusy(true);
    setErr("");
    try {
      if (
        (draft.tag === "si_im" || draft.tag === "si_only") &&
        !draft.service_plan_id &&
        draft.service_plan_enroll !== "yes" &&
        draft.service_plan_enroll !== "no"
      ) {
        setErr("Choose whether to enroll this customer in a yearly service plan");
        setBusy(false);
        return;
      }
      const { scheduled_at, all_day } = schedulePayload();
      await api.saveAppointment({
        ...draft,
        scheduled_at,
        all_day,
        waiter: Boolean(draft.waiter),
        urgent: Boolean(draft.urgent),
        requested_tech_name:
          techs.find((t) => t.id === draft.requested_tech_id)?.name || draft.requested_tech_name || "",
      });
      await onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save");
      setBusy(false);
    }
  }

  async function archive(status: "canceled" | "no_show") {
    if (!draft.id) return;
    setBusy(true);
    setErr("");
    try {
      await api.archiveAppointment(draft.id, status);
      await onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not update");
      setBusy(false);
    }
  }

  async function convert() {
    if (!draft.id) {
      await save();
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const { scheduled_at, all_day } = schedulePayload();
      await api.saveAppointment({
        ...draft,
        scheduled_at,
        all_day,
        waiter: Boolean(draft.waiter),
        urgent: Boolean(draft.urgent),
        requested_tech_name:
          techs.find((t) => t.id === draft.requested_tech_id)?.name || draft.requested_tech_name || "",
      });
      const r = await api.convertAppointment(draft.id);
      onConverted(r.order.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not convert");
      setBusy(false);
    }
  }

  async function lookup() {
    if (!histVin.trim() && !histName.trim()) {
      setErr("Enter a VIN and/or customer name or phone");
      return;
    }
    setBusy(true);
    setErr("");
    setHistNote("");
    try {
      const r = await api.history(histVin, histName, undefined, true);
      setHits(r.orders || []);
      setHistNote(r.note || (r.orders?.length ? "" : "No prior jobs found"));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Lookup failed");
      setHits([]);
    } finally {
      setBusy(false);
    }
  }

  const isEdit = state.kind === "edit" && Boolean(draft.id);
  const converted = (draft.status || "") === "converted";

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="Close" onClick={onClose} />
      <div className="relative z-10 max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-border bg-surface p-5 shadow-lg">
        <h2 className="text-lg font-semibold tracking-tight">
          {isEdit ? "Appointment" : "New appointment"}
        </h2>
        <p className="mt-1 text-sm text-muted">
          Phone booking only — not a work order until you convert it.
        </p>

        <div className="mt-4 rounded-xl border border-border p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">From prior car</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Input
              placeholder="VIN"
              className="h-8 w-28"
              value={histVin}
              onChange={(e) => setHistVin(e.target.value)}
            />
            <Input
              placeholder="Name or phone"
              className="h-8 min-w-[8rem] flex-1"
              value={histName}
              onChange={(e) => setHistName(e.target.value)}
            />
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => void lookup()}>
              Search
            </Button>
          </div>
          {histNote ? <p className="mt-2 text-xs text-muted">{histNote}</p> : null}
          {hits.length ? (
            <ul className="mt-2 max-h-32 space-y-1 overflow-y-auto text-sm">
              {hits.map((o) => (
                <li key={o.id}>
                  <button
                    type="button"
                    className="w-full rounded-md px-2 py-1 text-left hover:bg-border/40"
                    onClick={() => {
                      setDraft(fromPrior(o, date));
                      setHits([]);
                    }}
                  >
                    <span className="font-medium">
                      {o.last_name}, {o.first_name}
                    </span>
                    <span className="text-muted">
                      {" "}
                      · {[o.year, o.make, o.model].filter(Boolean).join(" ")}
                      {o.vin ? ` · ${o.vin}` : ""}
                      {" · last visit "}
                      {o.id}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label htmlFor="appt-first">First name</Label>
            <Input
              id="appt-first"
              value={draft.first_name || ""}
              onChange={(e) => setDraft((d) => ({ ...d, first_name: e.target.value }))}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="appt-last">Last name</Label>
            <Input
              id="appt-last"
              value={draft.last_name || ""}
              onChange={(e) => setDraft((d) => ({ ...d, last_name: e.target.value }))}
            />
          </div>
          <div className="col-span-2 space-y-1">
            <Label htmlFor="appt-phone">Phone</Label>
            <Input
              id="appt-phone"
              value={draft.phone || ""}
              onChange={(e) => setDraft((d) => ({ ...d, phone: e.target.value }))}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="appt-year">Year</Label>
            <Input
              id="appt-year"
              value={draft.year || ""}
              onChange={(e) => setDraft((d) => ({ ...d, year: e.target.value }))}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="appt-make">Make</Label>
            <Input
              id="appt-make"
              value={draft.make || ""}
              onChange={(e) => setDraft((d) => ({ ...d, make: e.target.value }))}
            />
          </div>
          <div className="col-span-2 space-y-1">
            <Label htmlFor="appt-model">Model</Label>
            <Input
              id="appt-model"
              value={draft.model || ""}
              onChange={(e) => setDraft((d) => ({ ...d, model: e.target.value }))}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="appt-date">Date</Label>
            <Input id="appt-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="appt-time">Time (optional)</Label>
            <Input
              id="appt-time"
              type="time"
              disabled={allDay}
              value={allDay ? "" : time}
              onChange={(e) => {
                const v = e.target.value;
                setTime(v);
                if (v) setAllDay(false);
              }}
            />
          </div>
          <label className="col-span-2 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={allDay}
              onChange={(e) => {
                const on = e.target.checked;
                setAllDay(on);
                if (on) setTime("");
              }}
            />
            All day
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={Boolean(draft.waiter)}
              onChange={(e) => setDraft((d) => ({ ...d, waiter: e.target.checked }))}
            />
            Waiter
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={Boolean(draft.urgent)}
              onChange={(e) => setDraft((d) => ({ ...d, urgent: e.target.checked }))}
            />
            Urgent
          </label>
          <div className="col-span-2 space-y-1">
            <Label>Tag</Label>
            <div className="flex flex-wrap gap-1.5">
              {visibleTags(paInspectionTypes).map((t) => (
                <button
                  key={t.value}
                  type="button"
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs font-medium",
                    draft.tag === t.value
                      ? "border-accent bg-accent text-accent-fg"
                      : "border-border text-muted hover:text-fg",
                  )}
                  onClick={() => setDraft((d) => applyTagToAppointmentDraft(d, t.value))}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          {(draft.tag === "si_im" || draft.tag === "si_only") && !draft.service_plan_id ? (
            <div className="col-span-2 rounded-lg border border-border p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">Service plan</p>
              <p className="mt-1 text-sm">
                Enroll this customer in a yearly {draft.tag === "si_only" ? "SI only" : "SI/IM"} plan? We will call when it is due.
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant={draft.service_plan_enroll === "yes" ? "default" : "secondary"}
                  onClick={() => setDraft((d) => ({ ...d, service_plan_enroll: "yes" }))}
                >
                  Enroll
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={draft.service_plan_enroll === "no" ? "default" : "secondary"}
                  onClick={() => setDraft((d) => ({ ...d, service_plan_enroll: "no" }))}
                >
                  Not now
                </Button>
              </div>
            </div>
          ) : null}
          <div className="col-span-2 space-y-1">
            <Label htmlFor="appt-notes">Notes</Label>
            <textarea
              id="appt-notes"
              className="min-h-[72px] w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-fg"
              value={draft.notes || ""}
              onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
            />
          </div>
          <div className="col-span-2 space-y-1">
            <Label htmlFor="appt-tech">Requested tech</Label>
            <select
              id="appt-tech"
              className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
              value={draft.requested_tech_id || ""}
              onChange={(e) => {
                const id = e.target.value;
                const t = techs.find((x) => x.id === id);
                setDraft((d) => ({
                  ...d,
                  requested_tech_id: id,
                  requested_tech_name: t?.name || "",
                }));
              }}
            >
              <option value="">Any / unassigned</option>
              {techs.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {isEdit && !converted ? (
          <div className="mt-4 rounded-xl border border-border p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">Confirm call</p>
            <p className="mt-0.5 text-xs text-muted">
              {confirmLabel(draft.confirm_status, draft.confirm_attempts)}
              {draft.confirm_by ? ` · ${draft.confirm_by}` : ""}
              {draft.phone ? (
                <>
                  {" · "}
                  <a href={`tel:${(draft.phone || "").replace(/[^\d+]/g, "")}`} className="text-accent hover:underline">
                    {draft.phone}
                  </a>
                </>
              ) : null}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {(["confirmed", "no_answer", "canceled", "veto_next"] as const).map((outcome) => (
                <Button
                  key={outcome}
                  size="sm"
                  variant={draft.confirm_status === outcome ? "default" : "secondary"}
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    setErr("");
                    try {
                      await api.confirmAppointment(draft.id, outcome);
                      await onSaved();
                    } catch (e) {
                      setErr(e instanceof Error ? e.message : "Could not update call");
                      setBusy(false);
                    }
                  }}
                >
                  {outcome === "confirmed"
                    ? "Confirmed"
                    : outcome === "no_answer"
                      ? "No answer"
                      : outcome === "canceled"
                        ? "Canceled"
                        : "Veto → tomorrow"}
                </Button>
              ))}
              <Button
                size="sm"
                variant="secondary"
                disabled={busy}
                onClick={() => void archive("canceled")}
              >
                Delete appointment
              </Button>
            </div>
          </div>
        ) : null}

        {err ? <p className="mt-3 text-sm text-danger">{err}</p> : null}

        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Close
          </Button>
          {isEdit && !converted ? (
            <>
              <Button variant="secondary" disabled={busy} onClick={() => void archive("no_show")}>
                No show
              </Button>
              <Button variant="secondary" disabled={busy} onClick={() => void archive("canceled")}>
                Cancel
              </Button>
              <Button disabled={busy} onClick={() => void convert()}>
                Make work order
              </Button>
            </>
          ) : null}
          {converted && draft.converted_ro_id ? (
            <Button onClick={() => onConverted(draft.converted_ro_id!)}>Open work order</Button>
          ) : (
            <Button variant={isEdit ? "secondary" : "default"} disabled={busy} onClick={() => void save()}>
              {isEdit ? "Save" : "Book"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
