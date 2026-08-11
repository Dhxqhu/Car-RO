import { useCallback, useEffect, useState } from "react";
import { api, type TechShift } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatShopTime } from "@/lib/utils";

function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function todayIso(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Day start / day end + edit own punches (admin PIN required). */
export function TechShiftControls({ techId }: { techId?: string | null }) {
  const [shift, setShift] = useState<TechShift | null>(null);
  const [todayShifts, setTodayShifts] = useState<TechShift[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editStart, setEditStart] = useState("");
  const [editEnd, setEditEnd] = useState("");
  const [adminPin, setAdminPin] = useState("");

  const refresh = useCallback(async () => {
    if (!techId) {
      setShift(null);
      setTodayShifts([]);
      return;
    }
    try {
      const [mine, listed] = await Promise.all([
        api.shiftMine(),
        api.listShifts({ tech_id: techId, day_from: todayIso(), day_to: todayIso(), limit: 20 }),
      ]);
      setShift(mine.shift || null);
      setTodayShifts(listed.shifts || []);
      setErr("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Shift unavailable");
      setShift(null);
      setTodayShifts([]);
    }
  }, [techId]);

  useEffect(() => {
    void refresh();
    const t = window.setInterval(() => void refresh(), 60_000);
    return () => window.clearInterval(t);
  }, [refresh]);

  if (!techId) return null;

  async function start() {
    setBusy(true);
    setErr("");
    try {
      const r = await api.shiftStart();
      setShift(r.shift);
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Day start failed");
    } finally {
      setBusy(false);
    }
  }

  async function end() {
    setBusy(true);
    setErr("");
    try {
      await api.shiftEnd();
      setShift(null);
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Day end failed");
    } finally {
      setBusy(false);
    }
  }

  function beginEdit(s: TechShift) {
    setEditingId(s.id);
    setEditStart(toLocalInput(s.started_at));
    setEditEnd(s.ended_at ? toLocalInput(s.ended_at) : "");
    setAdminPin("");
    setErr("");
  }

  async function saveEdit(s: TechShift) {
    if (adminPin.length !== 4) {
      setErr("Enter the 4-digit shop admin PIN");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const body: {
        started_at?: string;
        ended_at?: string;
        clear_end?: boolean;
        admin_pin: string;
      } = { admin_pin: adminPin };
      if (editStart) body.started_at = editStart;
      if (!s.ended_at && !editEnd) {
        /* leave open */
      } else if (editEnd) {
        body.ended_at = editEnd;
      }
      await api.updateShift(s.id, body);
      setEditingId(null);
      setAdminPin("");
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save punch");
    } finally {
      setBusy(false);
    }
  }

  const onClock = !!shift && !shift.ended_at;
  const punches = todayShifts.length
    ? todayShifts
    : shift
      ? [shift]
      : [];

  return (
    <div className="flex max-w-md flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {onClock ? (
          <>
            <span className="text-xs text-muted">
              On clock · {formatShopTime(shift.started_at)}
            </span>
            <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={() => void end()}>
              Day end
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => beginEdit(shift)}
            >
              Edit punch
            </Button>
          </>
        ) : (
          <Button type="button" size="sm" variant="default" disabled={busy} onClick={() => void start()}>
            Day start
          </Button>
        )}
      </div>

      {editingId != null ? (
        <div className="space-y-2 rounded-lg border border-border bg-surface px-3 py-2">
          <p className="text-[11px] text-muted">
            Edit your punch — shop admin PIN required
          </p>
          <div className="flex flex-wrap gap-2">
            <Input
              type="datetime-local"
              className="h-10 min-w-[16.5rem] w-[16.5rem] text-sm"
              value={editStart}
              onChange={(e) => setEditStart(e.target.value)}
              aria-label="Start time"
            />
            <Input
              type="datetime-local"
              className="h-10 min-w-[16.5rem] w-[16.5rem] text-sm"
              value={editEnd}
              onChange={(e) => setEditEnd(e.target.value)}
              aria-label="End time"
              placeholder="End (optional if still open)"
            />
            <Input
              type="password"
              inputMode="numeric"
              maxLength={4}
              className="h-9 w-24 text-xs"
              placeholder="Admin PIN"
              value={adminPin}
              onChange={(e) => setAdminPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              disabled={busy || adminPin.length !== 4}
              onClick={() => {
                const s = punches.find((p) => p.id === editingId) || shift;
                if (s) void saveEdit(s);
              }}
            >
              Save
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => {
                setEditingId(null);
                setAdminPin("");
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : null}

      {punches.filter((p) => p.ended_at).length > 0 ? (
        <ul className="space-y-1 text-[11px] text-muted">
          {punches
            .filter((p) => p.ended_at)
            .slice(0, 4)
            .map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-2">
                <span>
                  {formatShopTime(p.started_at)} → {formatShopTime(p.ended_at || "")}
                </span>
                <button
                  type="button"
                  className="text-accent hover:underline"
                  disabled={busy}
                  onClick={() => beginEdit(p)}
                >
                  Edit
                </button>
              </li>
            ))}
        </ul>
      ) : null}

      {err ? (
        <span className="max-w-[20rem] text-[11px] text-danger" title={err}>
          {err}
        </span>
      ) : null}
    </div>
  );
}
