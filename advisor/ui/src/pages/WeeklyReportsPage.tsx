import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type WeeklyReportMeta,
  type WeeklyTechReport,
  type WeeklyTechRow,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { formatShopTime, formatWorkedMinutes } from "@/lib/utils";

const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function shiftWeek(weekStart: string, deltaWeeks: number): string {
  const d = new Date(weekStart + "T12:00:00");
  d.setDate(d.getDate() + deltaWeeks * 7);
  return d.toISOString().slice(0, 10);
}

function TechBlock({ row }: { row: WeeklyTechRow }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-xl border border-border bg-surface px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-medium">{row.tech_name || row.tech_id}</div>
          <div className="mt-0.5 text-sm text-muted">
            Job {formatWorkedMinutes(row.job_minutes)} · Presence{" "}
            {formatWorkedMinutes(row.presence_minutes)}
          </div>
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={() => setOpen((o) => !o)}>
          {open ? "Hide jobs" : `Jobs · ${row.jobs.length}`}
        </Button>
      </div>
      <div className="mt-3 overflow-x-auto">
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
                const day = row.days[String(i)] || { job_minutes: 0, presence_minutes: 0 };
                return (
                  <td key={i} className="px-1 py-1 tabular-nums">
                    <div>{formatWorkedMinutes(day.job_minutes)}</div>
                    <div className="text-muted">{formatWorkedMinutes(day.presence_minutes)}</div>
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
        <p className="mt-1 text-[11px] text-muted">Top = job · bottom = presence</p>
      </div>
      {open && row.jobs.length ? (
        <ul className="mt-3 space-y-1 border-t border-border/60 pt-2 text-sm">
          {row.jobs.map((j) => (
            <li key={`${j.ro_id}-${j.item_id}`} className="flex flex-wrap justify-between gap-2">
              <span>
                <Link to={`/ro/${j.ro_id}`} className="text-accent hover:underline">
                  {j.item_id}
                </Link>
                <span className="text-muted"> · {j.ro_id}</span>
                {j.concern ? ` — ${j.concern}` : ""}
              </span>
              <span className="tabular-nums text-muted">{formatWorkedMinutes(j.minutes)}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function WeeklyReportsPage() {
  const [weekStart, setWeekStart] = useState("");
  const [live, setLive] = useState<WeeklyTechReport | null>(null);
  const [snapshot, setSnapshot] = useState<WeeklyTechReport | null>(null);
  const [snapMeta, setSnapMeta] = useState<{
    created_at?: string;
    created_by?: string;
  } | null>(null);
  const [archive, setArchive] = useState<WeeklyReportMeta[]>([]);
  const [useSnap, setUseSnap] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async (ws?: string) => {
    setBusy(true);
    setErr("");
    try {
      const r = await api.weeklyReport(ws || undefined);
      setWeekStart(r.week_start || r.live?.week_start || "");
      setLive(r.live);
      const snap = r.snapshot?.payload || null;
      setSnapshot(snap);
      setSnapMeta(
        r.snapshot
          ? { created_at: r.snapshot.created_at, created_by: r.snapshot.created_by }
          : null,
      );
      setUseSnap(!!snap);
      const a = await api.weeklyReportArchive().catch(() => ({ weeks: [] }));
      setArchive(a.weeks || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load report");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const report = useSnap && snapshot ? snapshot : live;
  const closed =
    report && report.week_end
      ? report.week_end < new Date().toISOString().slice(0, 10)
      : false;

  async function save() {
    if (!weekStart) return;
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const r = await api.saveWeeklyReport(weekStart);
      setSnapshot(r.snapshot?.payload || null);
      setSnapMeta({
        created_at: r.snapshot?.created_at,
        created_by: r.snapshot?.created_by,
      });
      setUseSnap(true);
      setMsg("Week saved to shop server");
      await load(weekStart);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight">
            Weekly tech reports
          </h1>
          <p className="mt-1 max-w-xl text-sm text-muted">
            Sunday–Saturday job hours (timers) and presence (day start → day end). Save a week to the
            shop server for later reference.
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
          {" · "}
          {useSnap && snapshot ? (
            <span className="text-accent">
              Saved
              {snapMeta?.created_by ? ` by ${snapMeta.created_by}` : ""}
              {snapMeta?.created_at ? ` · ${formatShopTime(snapMeta.created_at)}` : ""}
            </span>
          ) : (
            <span>Live</span>
          )}
          {snapshot && live ? (
            <>
              {" · "}
              <button
                type="button"
                className="text-accent hover:underline"
                onClick={() => setUseSnap((v) => !v)}
              >
                Show {useSnap ? "live" : "saved"}
              </button>
            </>
          ) : null}
        </p>
      ) : null}

      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {msg ? <p className="text-sm text-muted">{msg}</p> : null}

      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={busy || !weekStart} onClick={() => void save()}>
          Save week to server
        </Button>
        {closed && !snapshot ? (
          <span className="self-center text-xs text-muted">
            This week is closed and not archived yet — save to keep a fixed copy.
          </span>
        ) : null}
      </div>

      {report ? (
        <div className="space-y-2 text-sm text-muted">
          Shop job total {formatWorkedMinutes(report.shop_job_minutes)} · presence{" "}
          {formatWorkedMinutes(report.shop_presence_minutes)}
        </div>
      ) : null}

      {!report?.techs?.length ? (
        <p className="text-sm text-muted">
          {busy ? "Loading…" : "No tech hours for this week yet."}
        </p>
      ) : (
        <ul className="space-y-3">
          {report.techs.map((t) => (
            <TechBlock key={t.tech_id || t.tech_name} row={t} />
          ))}
        </ul>
      )}

      {archive.length ? (
        <section className="space-y-2 border-t border-border pt-6">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
            Saved weeks
          </h2>
          <ul className="flex flex-wrap gap-2">
            {archive.map((w) => (
              <li key={w.week_start}>
                <Button
                  type="button"
                  size="sm"
                  variant={w.week_start === weekStart ? "default" : "secondary"}
                  onClick={() => void load(w.week_start)}
                >
                  {w.week_start}
                </Button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
