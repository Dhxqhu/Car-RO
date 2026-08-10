import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type EfficiencyReport,
  type EfficiencyTechRow,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn, formatWorkedMinutes } from "@/lib/utils";

const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function shiftWeek(weekStart: string, deltaWeeks: number): string {
  const d = new Date(weekStart + "T12:00:00");
  d.setDate(d.getDate() + deltaWeeks * 7);
  return d.toISOString().slice(0, 10);
}

function pct(rate: number): string {
  if (!Number.isFinite(rate)) return "—";
  return `${Math.round(rate * 100)}%`;
}

function StackBar({
  utilized,
  downtime,
  className,
}: {
  utilized: number;
  downtime: number;
  className?: string;
}) {
  const total = Math.max(0, utilized) + Math.max(0, downtime);
  const u = total > 0 ? (utilized / total) * 100 : 0;
  const d = total > 0 ? (downtime / total) * 100 : 0;
  return (
    <div className={cn("flex h-2.5 w-full overflow-hidden rounded-full bg-border/50", className)}>
      {u > 0 ? (
        <div className="bg-accent" style={{ width: `${u}%` }} title="Utilized" />
      ) : null}
      {d > 0 ? (
        <div className="bg-[var(--muted)]/35" style={{ width: `${d}%` }} title="Downtime" />
      ) : null}
    </div>
  );
}

function BaselineBar({
  value,
  baseline,
  label,
}: {
  value: number;
  baseline: number;
  label: string;
}) {
  const max = Math.max(baseline, value, 1);
  const vPct = Math.min(100, (value / max) * 100);
  const bPct = baseline > 0 ? Math.min(100, (baseline / max) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted">
        <span>{label}</span>
        <span className="tabular-nums">
          {formatWorkedMinutes(value)}
          {baseline > 0 ? ` / ${formatWorkedMinutes(baseline)} baseline` : ""}
        </span>
      </div>
      <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-border/50">
        <div className="absolute inset-y-0 left-0 bg-accent/80" style={{ width: `${vPct}%` }} />
        {baseline > 0 ? (
          <div
            className="absolute inset-y-0 w-px bg-fg/70"
            style={{ left: `${bPct}%` }}
            title="40h / 8h baseline"
          />
        ) : null}
      </div>
    </div>
  );
}

function TechCard({ row }: { row: EfficiencyTechRow }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-2xl border border-border bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold tracking-tight">{row.tech_name || row.tech_id}</h3>
          <p className="mt-1 text-sm tabular-nums text-muted">
            <span className="text-fg">{formatWorkedMinutes(row.job_minutes)} worked</span>
            {" · "}
            {formatWorkedMinutes(row.presence_minutes)} clocked
            {" · "}
            {pct(row.worked_vs_clocked_rate)}
          </p>
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={() => setOpen((o) => !o)}>
          {open ? "Hide" : "Details"}
        </Button>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="space-y-2 rounded-xl border border-border/60 p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">
            Worked vs clocked
          </p>
          <p className="text-sm tabular-nums">
            {formatWorkedMinutes(row.job_minutes)} / {formatWorkedMinutes(row.presence_minutes)}
            <span className="ml-2 text-muted">{pct(row.worked_vs_clocked_rate)}</span>
          </p>
        </div>
        <div className="space-y-2 rounded-xl border border-border/60 p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">
            Utilized vs downtime
          </p>
          <p className="text-sm tabular-nums">
            {formatWorkedMinutes(row.utilized_minutes)} util ·{" "}
            {formatWorkedMinutes(row.downtime_minutes)} down
            <span className="ml-2 text-muted">{pct(row.utilized_rate)}</span>
          </p>
          <StackBar utilized={row.utilized_minutes} downtime={row.downtime_minutes} />
        </div>
      </div>

      <div className="mt-3 space-y-2">
        <BaselineBar
          value={row.job_minutes}
          baseline={row.baseline_minutes}
          label="Baseline fill (wrench vs 40h normal week)"
        />
        {row.ot_minutes > 0 ? (
          <p className="text-xs text-muted">
            OT over baseline {formatWorkedMinutes(row.ot_minutes)} clocked
          </p>
        ) : null}
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
                const day = row.days[String(i)] || {
                  job_minutes: 0,
                  presence_minutes: 0,
                  downtime_minutes: 0,
                  ot_minutes: 0,
                  baseline_minutes: 0,
                };
                return (
                  <td key={i} className="px-1 py-1 align-top tabular-nums">
                    <div>{formatWorkedMinutes(day.job_minutes)}</div>
                    <div className="text-muted">{formatWorkedMinutes(day.presence_minutes)}</div>
                    {day.downtime_minutes > 0 ? (
                      <div className="text-[10px] text-muted">
                        ↓{formatWorkedMinutes(day.downtime_minutes)}
                      </div>
                    ) : null}
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
        <p className="mt-1 text-[11px] text-muted">Top = worked · middle = clocked · ↓ = downtime</p>
      </div>

      {open ? (
        <div className="mt-4 space-y-3 border-t border-border/60 pt-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">
              Downtime breakdown
            </p>
            {row.downtime_by_reason?.length ? (
              <ul className="mt-2 space-y-1 text-sm">
                {row.downtime_by_reason.map((r) => (
                  <li key={r.reason} className="flex justify-between gap-2 tabular-nums">
                    <span>{r.label}</span>
                    <span className="text-muted">{formatWorkedMinutes(r.minutes)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-sm text-muted">No downtime this week.</p>
            )}
          </div>
          {row.jobs?.length ? (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                Jobs
              </p>
              <ul className="mt-2 space-y-1 text-sm">
                {row.jobs.map((j) => (
                  <li
                    key={`${j.ro_id}-${j.item_id}`}
                    className="flex flex-wrap justify-between gap-2"
                  >
                    <span>
                      <Link to={`/ro/${j.ro_id}`} className="text-accent hover:underline">
                        {j.item_id}
                      </Link>
                      <span className="text-muted"> · {j.ro_id}</span>
                      {j.concern ? ` — ${j.concern}` : ""}
                    </span>
                    <span className="tabular-nums text-muted">
                      {formatWorkedMinutes(j.minutes)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

export function EfficiencyPage() {
  const [weekStart, setWeekStart] = useState("");
  const [report, setReport] = useState<EfficiencyReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async (ws?: string) => {
    setBusy(true);
    setErr("");
    try {
      const r = await api.efficiencyReport(ws || undefined);
      setWeekStart(r.week_start || r.report?.week_start || "");
      setReport(r.report);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load efficiency");
      setReport(null);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const shop = report?.shop;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight">
            Efficiency
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Shop metric for a normal week: <span className="text-fg">40h baseline</span> (5×8) —
            not a cap. Compare time worked on cars vs time clocked in, and utilized vs downtime
            (parts waits, wrong parts, gaps). OT is hours over the baseline.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            disabled={busy || !weekStart}
            onClick={() => void load(shiftWeek(weekStart, -1))}
          >
            Prev week
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={busy || !weekStart}
            onClick={() => void load(shiftWeek(weekStart, 1))}
          >
            Next week
          </Button>
          <Button type="button" variant="ghost" disabled={busy} onClick={() => void load()}>
            This week
          </Button>
        </div>
      </div>

      {report ? (
        <p className="text-sm text-muted">
          Week of <span className="font-medium text-fg">{report.week_start}</span> →{" "}
          <span className="font-medium text-fg">{report.week_end}</span>
        </p>
      ) : null}

      {err ? <p className="text-sm text-danger">{err}</p> : null}

      {shop ? (
        <section className="space-y-4 rounded-2xl border border-border bg-surface p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">Shop</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-[11px] uppercase tracking-wide text-muted">Worked vs clocked</p>
              <p className="mt-1 text-lg font-semibold tabular-nums">
                {formatWorkedMinutes(shop.job_minutes)}
                <span className="text-sm font-normal text-muted">
                  {" "}
                  / {formatWorkedMinutes(shop.presence_minutes)}
                </span>
              </p>
              <p className="text-xs text-muted">{pct(shop.worked_vs_clocked_rate)} of clocked</p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide text-muted">Utilized vs downtime</p>
              <p className="mt-1 text-lg font-semibold tabular-nums">
                {formatWorkedMinutes(shop.utilized_minutes)}
                <span className="text-sm font-normal text-muted">
                  {" "}
                  · {formatWorkedMinutes(shop.downtime_minutes)} down
                </span>
              </p>
              <StackBar
                className="mt-2"
                utilized={shop.utilized_minutes}
                downtime={shop.downtime_minutes}
              />
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide text-muted">Baseline fill</p>
              <p className="mt-1 text-lg font-semibold tabular-nums">{pct(shop.baseline_fill)}</p>
              <p className="text-xs text-muted">
                vs {formatWorkedMinutes(shop.baseline_minutes)} ({shop.techs_present} tech
                {shop.techs_present === 1 ? "" : "s"} × 40h)
              </p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide text-muted">OT over baseline</p>
              <p className="mt-1 text-lg font-semibold tabular-nums">
                {formatWorkedMinutes(shop.ot_minutes)}
              </p>
              <p className="text-xs text-muted">Clocked past normal week</p>
            </div>
          </div>
          {shop.downtime_by_reason?.length ? (
            <div className="flex flex-wrap gap-2 border-t border-border/60 pt-3">
              {shop.downtime_by_reason.map((r) => (
                <span
                  key={r.reason}
                  className="rounded-lg border border-border/70 px-2.5 py-1 text-xs tabular-nums"
                >
                  {r.label} · {formatWorkedMinutes(r.minutes)}
                </span>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      {!report?.techs?.length ? (
        <p className="text-sm text-muted">
          {busy ? "Loading…" : "No clocked or worked hours for this week yet."}
        </p>
      ) : (
        <ul className="space-y-3">
          {report.techs.map((t) => (
            <TechCard key={t.tech_id || t.tech_name} row={t} />
          ))}
        </ul>
      )}

      <p className="text-xs text-muted">
        Raw timer + punch archive still on{" "}
        <Link to="/reports" className="text-accent hover:underline">
          Reports
        </Link>
        .
      </p>
    </div>
  );
}
