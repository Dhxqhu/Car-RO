import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, BellOff, X } from "lucide-react";
import { api } from "@/lib/api";
import {
  eventHref,
  eventLabel,
  filterAdvisorEvents,
  filterTechEvents,
  type RoEvent,
} from "@/lib/notifications";
import { isStandalone, pushBlockReason, subscribePush } from "@/lib/push";
import { formatMsgTime } from "@/lib/utils";

const SEEN_KEY = "carro-pwa-notify-seen";
const DISMISS_KEY = "carro-pwa-notify-dismissed";
const MAX_DISMISSED = 400;

function eventKey(e: RoEvent): string {
  return `ev:${e.id ?? `${e.at}-${e.type}-${e.ro_id}`}`;
}

function loadDismissed(): Set<string> {
  try {
    const raw = JSON.parse(localStorage.getItem(DISMISS_KEY) || "[]");
    return new Set(Array.isArray(raw) ? raw.map(String) : []);
  } catch {
    return new Set();
  }
}

function saveDismissed(set: Set<string>) {
  localStorage.setItem(DISMISS_KEY, JSON.stringify([...set].slice(-MAX_DISMISSED)));
}

export function NotifyBell({
  id,
  name,
  role,
}: {
  id: string;
  name: string;
  role: string;
}) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<RoEvent[]>([]);
  const [unread, setUnread] = useState(0);
  const [subscribed, setSubscribed] = useState(false);
  const [pushHint, setPushHint] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const lastId = useRef(0);
  const seenId = useRef(Number(localStorage.getItem(SEEN_KEY) || 0));
  const primed = useRef(false);
  const dismissed = useRef(loadDismissed());
  const self = { id, name };

  const filter = useCallback(
    (batch: RoEvent[]) =>
      role === "advisor" ? filterAdvisorEvents(batch, self) : filterTechEvents(batch, self),
    [id, name, role],
  );

  const load = useCallback(async () => {
    try {
      const r = await api.listEvents({
        since_id: lastId.current || undefined,
        limit: 80,
        exclude_actor_id: id,
      });
      const batch = r.events || [];
      if (!batch.length) return;
      const maxId = Math.max(...batch.map((e) => Number(e.id) || 0), lastId.current);
      lastId.current = maxId;
      const mine = filter(batch).filter((e) => !dismissed.current.has(eventKey(e)));
      if (!mine.length) {
        if (!primed.current) {
          primed.current = true;
          seenId.current = Math.max(seenId.current, maxId);
        }
        return;
      }
      setEvents((prev) => {
        const byId = new Map<string, RoEvent>();
        for (const e of [...mine.slice().reverse(), ...prev]) {
          if (dismissed.current.has(eventKey(e))) continue;
          byId.set(eventKey(e), e);
        }
        return Array.from(byId.values()).slice(0, 40);
      });
      if (!primed.current) {
        primed.current = true;
        seenId.current = Math.max(seenId.current, maxId);
        localStorage.setItem(SEEN_KEY, String(seenId.current));
        return;
      }
      const fresh = mine.filter((e) => Number(e.id) > seenId.current);
      if (fresh.length && !open) setUnread((u) => u + fresh.length);
    } catch {
      /* ignore poll errors */
    }
  }, [filter, id, open]);

  useEffect(() => {
    setPushHint(pushBlockReason());
    api
      .pushVapid()
      .then((r) => setSubscribed(!!r.subscribed))
      .catch(() => undefined);
    void load();
    const t = window.setInterval(() => void load(), 8000);
    return () => window.clearInterval(t);
  }, [load]);

  function dismissOne(e: RoEvent) {
    dismissed.current.add(eventKey(e));
    saveDismissed(dismissed.current);
    setEvents((prev) => prev.filter((x) => eventKey(x) !== eventKey(e)));
  }

  function dismissAll() {
    for (const e of events) dismissed.current.add(eventKey(e));
    saveDismissed(dismissed.current);
    setEvents([]);
    setUnread(0);
  }

  function markSeen() {
    const top = events[0]?.id;
    if (top) {
      seenId.current = Math.max(seenId.current, Number(top) || 0);
      localStorage.setItem(SEEN_KEY, String(seenId.current));
    }
    setUnread(0);
  }

  async function enablePush() {
    setBusy(true);
    try {
      const blocked = pushBlockReason();
      if (blocked) {
        setPushHint(blocked);
        return;
      }
      const cfg = await api.pushVapid();
      const sub = await subscribePush(cfg.public_key);
      await api.pushSubscribe(sub);
      setSubscribed(true);
      setPushHint(null);
    } catch (e) {
      setPushHint(e instanceof Error ? e.message : "Could not enable");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        className="relative flex h-10 w-10 items-center justify-center rounded-full text-fg"
        aria-label="Notifications"
        onClick={() => {
          setOpen((v) => {
            const next = !v;
            if (next) markSeen();
            return next;
          });
        }}
      >
        <Bell size={20} />
        {unread > 0 ? (
          <span className="absolute right-1 top-1 min-w-4 rounded-full bg-accent px-1 text-[10px] font-semibold leading-4 text-accent-fg">
            {unread > 9 ? "9+" : unread}
          </span>
        ) : null}
      </button>

      {open ? (
        <>
          <button
            type="button"
            className="fixed inset-0 z-40 cursor-default bg-black/30"
            aria-label="Close notifications"
            onClick={() => setOpen(false)}
          />
          <div className="fixed inset-x-3 z-50 flex max-h-[min(28rem,70dvh)] flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-lg top-[calc(env(safe-area-inset-top)+3.75rem)]">
            <div className="flex items-start justify-between gap-3 border-b border-border px-3 py-2">
              <div>
                <p className="text-sm font-semibold">Notifications</p>
                <p className="text-[11px] text-muted">
                  {role === "advisor" ? "Desk updates and messages" : "Your jobs and messages"}
                </p>
              </div>
              {events.length > 0 ? (
                <button
                  type="button"
                  className="shrink-0 pt-0.5 text-[11px] font-medium text-muted"
                  onClick={() => dismissAll()}
                >
                  Clear all
                </button>
              ) : null}
            </div>
            <ul className="min-h-0 flex-1 overflow-y-auto">
              {events.length === 0 ? (
                <li className="px-3 py-6 text-center text-sm text-muted">Nothing yet.</li>
              ) : (
                events.map((e) => (
                  <li key={eventKey(e)} className="flex items-stretch border-b border-border/60">
                    <button
                      type="button"
                      className="min-w-0 flex-1 px-3 py-2.5 text-left active:bg-border/30"
                      onClick={() => {
                        setOpen(false);
                        navigate(eventHref(e));
                      }}
                    >
                      <span className="flex items-baseline justify-between gap-2">
                        <span className="text-xs font-semibold text-accent">{eventLabel(e.type)}</span>
                        <span className="text-[10px] text-muted">{formatMsgTime(e.at)}</span>
                      </span>
                      <span className="mt-0.5 block truncate text-sm">
                        {e.ro_id && e.ro_id !== "_message" ? `${e.ro_id} · ` : ""}
                        {e.summary || e.actor || "Update"}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="flex w-11 shrink-0 items-center justify-center text-muted active:text-fg"
                      aria-label="Clear notification"
                      onClick={(ev) => {
                        ev.stopPropagation();
                        dismissOne(e);
                      }}
                    >
                      <X size={16} />
                    </button>
                  </li>
                ))
              )}
            </ul>
            <div className="border-t border-border px-3 py-2">
              {subscribed ? (
                <p className="flex items-center gap-1.5 text-[11px] text-muted">
                  <Bell size={12} />
                  Phone alerts on
                </p>
              ) : (
                <button
                  type="button"
                  disabled={busy}
                  className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-xs font-medium text-accent-fg disabled:opacity-50"
                  onClick={() => void enablePush()}
                >
                  <BellOff size={12} />
                  {isStandalone() ? "Enable phone alerts" : "Add to Home Screen for alerts"}
                </button>
              )}
              {pushHint && !subscribed ? (
                <p className="mt-1.5 text-[11px] text-muted">{pushHint}</p>
              ) : null}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
