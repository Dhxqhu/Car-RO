import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type Advisor,
  type Technician,
  type TechShift,
  type WeeklyTechJob,
  type WeeklyTechReport,
  type WeeklyTechRow,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { formatShopTime, formatWorkedMinutes } from "@/lib/utils";

const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

type PersonOption = {
  id: string;
  name: string;
  kind: "tech" | "advisor";
};

type RoJobGroup = {
  ro_id: string;
  vehicle: string;
  customer: string;
  minutes: number;
  items: WeeklyTechJob[];
};

function shiftWeek(weekStart: string, deltaWeeks: number): string {
  const d = new Date(weekStart + "T12:00:00");
  d.setDate(d.getDate() + deltaWeeks * 7);
  return d.toISOString().slice(0, 10);
}

function matchesPerson(row: WeeklyTechRow, person: PersonOption): boolean {
  const rid = (row.tech_id || "").trim();
  const rname = (row.tech_name || "").trim().toLowerCase();
  if (person.id && rid && rid === person.id) return true;
  if (person.name && rname && rname === person.name.toLowerCase()) return true;
  return false;
}

function matchesShift(s: TechShift, person: PersonOption): boolean {
  if (person.id && s.tech_id === person.id) return true;
  if (
    person.name &&
    (s.tech_name || "").trim().toLowerCase() === person.name.toLowerCase()
  ) {
    return true;
  }
  return false;
}

function groupJobsByRo(jobs: WeeklyTechJob[] | undefined): RoJobGroup[] {
  const map = new Map<string, RoJobGroup>();
  for (const j of jobs || []) {
    const roId = (j.ro_id || "").trim() || "(no RO)";
    let g = map.get(roId);
    if (!g) {
      g = {
        ro_id: roId,
        vehicle: j.vehicle || "",
        customer: j.customer || "",
        minutes: 0,
        items: [],
      };
      map.set(roId, g);
    }
    g.minutes += Math.max(0, Number(j.minutes) || 0);
    g.items.push(j);
    if (!g.vehicle && j.vehicle) g.vehicle = j.vehicle;
    if (!g.customer && j.customer) g.customer = j.customer;
  }
  for (const g of map.values()) {
    g.items.sort((a, b) => (Number(b.minutes) || 0) - (Number(a.minutes) || 0));
  }
  return [...map.values()].sort((a, b) => b.minutes - a.minutes);
}

export function TimeCardsPage() {
  const [people, setPeople] = useState<PersonOption[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [weekStart, setWeekStart] = useState("");
  const [report, setReport] = useState<WeeklyTechReport | null>(null);
  const [shifts, setShifts] = useState<TechShift[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const selected = useMemo(
    () => people.find((p) => p.id === selectedId) || null,
    [people, selectedId],
  );

  const row = useMemo(() => {
    if (!report || !selected) return null;
    return (report.techs || []).find((t) => matchesPerson(t, selected)) || null;
  }, [report, selected]);

  const personShifts = useMemo(() => {
    if (!selected) return [];
    return shifts.filter((s) => matchesShift(s, selected));
  }, [shifts, selected]);

  const jobsByRo = useMemo(() => groupJobsByRo(row?.jobs), [row?.jobs]);

  const loadPeople = useCallback(async () => {
    const [techs, advisors] = await Promise.all([
      api.listTechs().catch(() => ({ technicians: [] as Technician[] })),
      api.listAdvisors().catch(() => ({ advisors: [] as Advisor[] })),
    ]);
    const opts: PersonOption[] = [];
    for (const t of techs.technicians || []) {
      if (!t.id) continue;
      opts.push({ id: t.id, name: t.name || t.id, kind: "tech" });
    }
    for (const a of advisors.advisors || []) {
      if (!a.id || !a.working_privilege) continue;
      opts.push({
        id: a.id,
        name: a.name || a.id,
        kind: "advisor",
      });
    }
    opts.sort((a, b) => a.name.localeCompare(b.name));
    setPeople(opts);
    setSelectedId((prev) => {
      if (prev && opts.some((p) => p.id === prev)) return prev;
      return opts[0]?.id || "";
    });
  }, []);

  const loadWeek = useCallback(async (ws?: string) => {
    setBusy(true);
    setErr("");
    try {
      const r = await api.weeklyReport(ws);
      const live = r.live;
      setReport(live);
      setWeekStart(r.week_start || live.week_start);
      const from = r.week_start || live.week_start;
      const to = live.week_end;
      const sh = await api
        .listShifts({ day_from: from, day_to: to, limit: 500 })
        .catch(() => ({ shifts: [] as TechShift[] }));
      setShifts(sh.shifts || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load time cards");
      setReport(null);
      setShifts([]);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void loadPeople().catch((e: Error) => setErr(e.message));
    void loadWeek();
  }, [loadPeople, loadWeek]);

  // Merge report-only people (e.g. former staff) into the picker
  useEffect(() => {
    if (!report?.techs?.length) return;
    setPeople((prev) => {
      const byId = new Map(prev.map((p) => [p.id, p]));
      let changed = false;
      for (const t of report.techs) {
        const id = (t.tech_id || "").trim();
        if (!id || byId.has(id)) continue;
        byId.set(id, {
          id,
          name: t.tech_name || id,
          kind: "tech",
        });
        changed = true;
      }
      if (!changed) return prev;
      return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));
    });
  }, [report]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold">
          Time cards
        </h1>
        <p className="mt-1 text-sm text-muted">
          Pick a technician or working-privilege advisor to see punches and job-time breakdown for
          the week.
        </p>
      </div>

      {err ? <p className="text-sm text-danger">{err}</p> : null}

      <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-border bg-surface p-4">
        <label className="min-w-[14rem] flex-1 text-xs text-muted">
          Person
          <select
            className="mt-1 flex h-10 w-full rounded-lg border border-border bg-bg px-3 text-sm text-fg"
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
          >
            {!people.length ? <option value="">No staff yet</option> : null}
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.kind === "advisor" ? " (advisor)" : ""}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy || !weekStart}
            onClick={() => void loadWeek(shiftWeek(weekStart, -1))}
          >
            Prev week
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy || !weekStart}
            onClick={() => void loadWeek(shiftWeek(weekStart, 1))}
          >
            Next week
          </Button>
          <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => void loadWeek()}>
            This week
          </Button>
        </div>
        {weekStart && report ? (
          <p className="text-xs text-muted">
            {report.week_start} → {report.week_end}
            {busy ? " · loading…" : ""}
          </p>
        ) : null}
      </div>

      {!selected ? (
        <p className="text-sm text-muted">Select a person to view their time card.</p>
      ) : (
        <div className="space-y-6">
          <section className="rounded-2xl border border-border bg-surface p-4">
            <h2 className="text-sm font-semibold">
              {selected.name}
              <span className="ml-2 text-xs font-normal text-muted">
                {selected.kind === "advisor" ? "Working advisor" : "Technician"}
              </span>
            </h2>
            <div className="mt-2 flex flex-wrap gap-4 text-sm text-muted">
              <span>
                Job time{" "}
                <span className="tabular-nums text-fg">
                  {formatWorkedMinutes(row?.job_minutes || 0)}
                </span>
              </span>
              <span>
                Presence{" "}
                <span className="tabular-nums text-fg">
                  {formatWorkedMinutes(row?.presence_minutes || 0)}
                </span>
                {selected.kind === "advisor" ? (
                  <span className="ml-1 text-xs">(usually none — salary / no day clock)</span>
                ) : null}
              </span>
            </div>

            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[28rem] text-left text-xs">
                <thead>
                  <tr className="text-muted">
                    {DAY_LABELS.map((d) => (
                      <th key={d} className="px-1 py-1 font-medium">
                        {d}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    {DAY_LABELS.map((_, i) => {
                      const day = row?.days?.[String(i)] || {
                        job_minutes: 0,
                        presence_minutes: 0,
                      };
                      return (
                        <td key={i} className="px-1 py-1 tabular-nums">
                          <div>{formatWorkedMinutes(day.job_minutes)}</div>
                          <div className="text-muted">
                            {formatWorkedMinutes(day.presence_minutes)}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                </tbody>
              </table>
              <p className="mt-1 text-[11px] text-muted">
                Top = job · bottom = presence. Job minutes by RO are listed under Worked time by RO
                below.
              </p>
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Punches this week
              {personShifts.length ? ` · ${personShifts.length}` : ""}
            </h2>
            {!personShifts.length ? (
              <p className="text-sm text-muted">
                {selected.kind === "advisor"
                  ? "No day-clock punches (working advisors track job time only)."
                  : "No punches in this week."}
              </p>
            ) : (
              <ul className="space-y-2">
                {personShifts.map((s) => (
                  <li
                    key={s.id}
                    className="rounded-xl border border-border bg-surface px-4 py-3 text-sm"
                  >
                    <span className="font-medium">{s.day}</span>
                    <span className="text-muted">
                      {" "}
                      · {formatShopTime(s.started_at)} →{" "}
                      {s.ended_at ? formatShopTime(s.ended_at) : "on clock"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Worked time by RO
              {jobsByRo.length ? ` · ${jobsByRo.length}` : ""}
            </h2>
            {(row?.job_minutes || 0) > 0 && !jobsByRo.length ? (
              <p className="text-sm text-muted">
                Job time is logged ({formatWorkedMinutes(row?.job_minutes || 0)}) but no RO
                breakdown is available — time entries may be missing tech stamps.
              </p>
            ) : !jobsByRo.length ? (
              <p className="text-sm text-muted">No timed job work for this person this week.</p>
            ) : (
              <ul className="space-y-3">
                {jobsByRo.map((g) => (
                  <li
                    key={g.ro_id}
                    className="rounded-xl border border-border bg-surface px-4 py-3 text-sm"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <Link
                          to={`/ro/${g.ro_id}`}
                          className="font-medium text-accent hover:underline"
                        >
                          {g.ro_id}
                        </Link>
                        <div className="mt-0.5 text-xs text-muted">
                          {[g.vehicle, g.customer].filter(Boolean).join(" · ")}
                        </div>
                      </div>
                      <span className="tabular-nums font-medium">
                        {formatWorkedMinutes(g.minutes)}
                      </span>
                    </div>
                    <ul className="mt-3 space-y-2 border-t border-border/80 pt-3">
                      {g.items.map((j) => (
                        <li
                          key={`${j.ro_id}-${j.item_id}`}
                          className="flex flex-wrap items-start justify-between gap-2 text-sm"
                        >
                          <div className="min-w-0">
                            <span className="font-mono text-xs text-muted">
                              {j.item_id || "—"}
                            </span>
                            {j.concern ? (
                              <div className="mt-0.5">{j.concern}</div>
                            ) : null}
                          </div>
                          <span className="tabular-nums text-muted">
                            {formatWorkedMinutes(j.minutes)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
