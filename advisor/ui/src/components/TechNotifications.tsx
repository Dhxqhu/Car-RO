import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bell } from "lucide-react";
import { api, type IdleNudge, type RoEvent, type ShopMessage } from "@/lib/api";
import { eventLabel, filterOthersEvents, formatEventSummary } from "@/lib/notifications";
import {
  loadNotifyPrefs,
  NOTIFY_PREFS_CHANGED,
  prefsAllowEvent,
  saveNotifyPrefs,
  type NotifyPrefs,
} from "@/lib/notifyPrefs";
import { playNotifyChime, unlockNotifySound } from "@/lib/notifySound";
import { Button } from "@/components/ui/button";
import { cn, formatShopTime, formatStatus } from "@/lib/utils";

const SEEN_KEY = "carro.notifications.seen_id";
const IDLE_SEEN_KEY = "carro.notifications.idle_seen";
const MSG_SEEN_KEY = "carro.notifications.msg_seen_id";

function loadIdleSeen(): Set<string> {
  try {
    const raw = JSON.parse(localStorage.getItem(IDLE_SEEN_KEY) || "[]");
    return new Set(Array.isArray(raw) ? raw.map(String) : []);
  } catch {
    return new Set();
  }
}

function saveIdleSeen(seen: Set<string>) {
  localStorage.setItem(IDLE_SEEN_KEY, JSON.stringify([...seen].slice(-200)));
}

function idleKindLabel(kind: string): string {
  if (kind === "part") return "Idle part";
  if (kind === "work_item") return "Idle work item";
  if (kind === "ro") return "Idle RO";
  return "Idle";
}

/**
 * Live feed: team RO events, idle nudges, and person-to-person messages (+ sound).
 */
export function TechNotifications({
  techName,
  techId,
}: {
  techName?: string | null;
  techId?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<RoEvent[]>([]);
  const [idle, setIdle] = useState<IdleNudge[]>([]);
  const [idleHours, setIdleHours] = useState(24);
  const [unread, setUnread] = useState(0);
  const [msgUnread, setMsgUnread] = useState(0);
  const [recentMsgs, setRecentMsgs] = useState<ShopMessage[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [prefs, setPrefs] = useState<NotifyPrefs>(() => loadNotifyPrefs());
  const lastId = useRef(0);
  const seenId = useRef(Number(localStorage.getItem(SEEN_KEY) || 0));
  const msgSeenId = useRef(Number(localStorage.getItem(MSG_SEEN_KEY) || 0));
  const idleSeen = useRef(loadIdleSeen());
  const idleBadgeCounted = useRef(new Set<string>());
  const primed = useRef(false);
  const self = { name: techName, id: techId };
  const soundOn = prefs.sound;

  useEffect(() => {
    const sync = () => setPrefs(loadNotifyPrefs());
    window.addEventListener(NOTIFY_PREFS_CHANGED, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(NOTIFY_PREFS_CHANGED, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const mergeEvents = useCallback(
    (batch: RoEvent[], replace: boolean) => {
      const others = filterOthersEvents(batch, self);
      if (!others.length && !replace) return { others, maxId: lastId.current };
      setEvents((prev) => {
        const merged = replace ? others.slice().reverse() : [...others.slice().reverse(), ...prev];
        const byId = new Map<string, RoEvent>();
        for (const e of merged) {
          byId.set(String(e.id ?? `${e.at}-${e.type}-${e.ro_id}`), e);
        }
        return Array.from(byId.values()).slice(0, 40);
      });
      const maxId = others.reduce((m, e) => Math.max(m, Number(e.id) || 0), lastId.current);
      if (maxId > lastId.current) lastId.current = maxId;
      return { others, maxId };
    },
    [techName, techId],
  );

  const mergeIdle = useCallback((rows: IdleNudge[]) => {
    setIdle(rows.slice(0, 40));
    const active = new Set(rows.map((r) => r.fingerprint).filter(Boolean));
    for (const fp of [...idleBadgeCounted.current]) {
      if (!active.has(fp)) idleBadgeCounted.current.delete(fp);
    }
    let fresh = 0;
    for (const row of rows) {
      const fp = row.fingerprint;
      if (!fp || idleSeen.current.has(fp) || idleBadgeCounted.current.has(fp)) continue;
      idleBadgeCounted.current.add(fp);
      fresh += 1;
    }
    return fresh;
  }, []);

  const chime = useCallback(
    (kind: "message" | "update") => {
      if (!soundOn || !primed.current) return;
      playNotifyChime(kind);
    },
    [soundOn],
  );

  const poll = useCallback(async () => {
    /** Any new notif this tick — sound module coalesces bursts. */
    let ping: "message" | "update" | null = null;
    try {
      const r = await api.listEvents({
        since_id: lastId.current || undefined,
        limit: 30,
        exclude_actor: techName || undefined,
        exclude_actor_id: techId || undefined,
      });
      setNote(r.note ?? null);
      if (r.events?.length) {
        const { others } = mergeEvents(r.events, false);
        const fresh = others.filter(
          (e) =>
            Number(e.id) > seenId.current &&
            e.type !== "shop_message" &&
            prefsAllowEvent(prefs, e.type),
        );
        if (fresh.length > 0) {
          if (!open) setUnread((u) => u + fresh.length);
          ping = "update";
        }
      }
    } catch {
      /* offline / no server — quiet */
    }
    try {
      const r = await api.listIdleNotifications();
      setIdleHours(r.idle_nudge_hours ?? 24);
      if (!r.enabled || !prefs.idleNudges) {
        setIdle([]);
      } else {
        const fresh = mergeIdle(r.idle || []);
        if (fresh > 0) {
          if (!open) setUnread((u) => u + fresh);
          if (!ping) ping = "update";
        }
      }
    } catch {
      /* engine older / offline */
    }
    try {
      if (!prefs.shopMessages) {
        setMsgUnread(0);
        setRecentMsgs([]);
      } else {
        const r = await api.listMessages({ unread: true, limit: 8 });
        const msgs = r.messages || [];
        setRecentMsgs(msgs);
        const count = r.unread ?? msgs.length;
        setMsgUnread(count);
        const maxMsgId = msgs.reduce((m, x) => Math.max(m, Number(x.id) || 0), 0);
        if (primed.current && maxMsgId > msgSeenId.current && count > 0) {
          ping = "message";
          msgSeenId.current = maxMsgId;
          localStorage.setItem(MSG_SEEN_KEY, String(maxMsgId));
        } else if (!primed.current && maxMsgId) {
          msgSeenId.current = maxMsgId;
          localStorage.setItem(MSG_SEEN_KEY, String(maxMsgId));
        }
      }
    } catch {
      setMsgUnread(0);
      setRecentMsgs([]);
    }
    if (ping) chime(ping);
  }, [mergeEvents, mergeIdle, techName, techId, open, chime, prefs]);

  useEffect(() => {
    void (async () => {
      try {
        const r = await api.listEvents({
          limit: 25,
          exclude_actor: techName || undefined,
          exclude_actor_id: techId || undefined,
        });
        setNote(r.note ?? null);
        if (r.events?.length) {
          const { others, maxId } = mergeEvents(r.events, true);
          if (maxId) lastId.current = maxId;
          setUnread(
            others.filter(
              (e) =>
                Number(e.id) > seenId.current &&
                e.type !== "shop_message" &&
                prefsAllowEvent(prefs, e.type),
            ).length,
          );
        }
      } catch {
        /* ignore */
      }
      try {
        const r = await api.listIdleNotifications();
        setIdleHours(r.idle_nudge_hours ?? 24);
        if (r.enabled && prefs.idleNudges) {
          const fresh = mergeIdle(r.idle || []);
          if (fresh > 0) setUnread((u) => u + fresh);
        } else {
          setIdle([]);
        }
      } catch {
        /* ignore */
      }
      try {
        if (!prefs.shopMessages) {
          setMsgUnread(0);
          setRecentMsgs([]);
        } else {
          const r = await api.listMessages({ unread: true, limit: 8 });
          const msgs = r.messages || [];
          setRecentMsgs(msgs);
          setMsgUnread(r.unread ?? msgs.length);
          const maxMsgId = msgs.reduce((m, x) => Math.max(m, Number(x.id) || 0), 0);
          if (maxMsgId > msgSeenId.current) {
            msgSeenId.current = maxMsgId;
            localStorage.setItem(MSG_SEEN_KEY, String(maxMsgId));
          }
        }
      } catch {
        setMsgUnread(0);
        setRecentMsgs([]);
      }
      primed.current = true;
    })();
  }, [techName, techId, prefs.idleNudges, prefs.shopMessages]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const t = window.setInterval(() => void poll(), 5000);
    return () => window.clearInterval(t);
  }, [poll]);

  function markSeen() {
    unlockNotifySound();
    if (lastId.current > seenId.current) {
      seenId.current = lastId.current;
      localStorage.setItem(SEEN_KEY, String(seenId.current));
    }
    for (const row of idle) {
      if (row.fingerprint) idleSeen.current.add(row.fingerprint);
    }
    saveIdleSeen(idleSeen.current);
    setUnread(0);
  }

  function toggleSound() {
    unlockNotifySound();
    const next = saveNotifyPrefs({ sound: !prefs.sound });
    setPrefs(next);
    if (next.sound) playNotifyChime("message", { force: true });
  }

  const empty = events.length === 0 && idle.length === 0 && recentMsgs.length === 0;

  return (
    <div className="relative">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label="Notifications"
        className="relative"
        onClick={() => {
          unlockNotifySound();
          setOpen((o) => !o);
          if (!open) markSeen();
        }}
      >
        <Bell className="h-4 w-4" />
        {unread + msgUnread > 0 ? (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold text-accent-fg">
            {unread + msgUnread > 9 ? "9+" : unread + msgUnread}
          </span>
        ) : null}
      </Button>
      {open ? (
        <>
          <button
            type="button"
            className="fixed inset-0 z-30 cursor-default"
            aria-label="Close notifications"
            onClick={() => setOpen(false)}
          />
          <div
            className={cn(
              "absolute right-0 z-40 mt-2 w-80 max-w-[min(20rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-border bg-surface shadow-lg",
            )}
          >
            <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
              <Link
                to="/messages"
                className={cn(
                  "text-sm font-medium hover:underline",
                  msgUnread > 0 ? "text-accent" : "text-muted",
                )}
                onClick={() => setOpen(false)}
              >
                {msgUnread > 0
                  ? `${msgUnread} unread message${msgUnread === 1 ? "" : "s"}`
                  : "Messages"}
              </Link>
              <div className="flex items-center gap-2">
                <Link
                  to="/settings"
                  className="text-[11px] text-muted hover:text-fg"
                  onClick={() => setOpen(false)}
                >
                  Config
                </Link>
                <button
                  type="button"
                  className="text-[11px] text-muted hover:text-fg"
                  onClick={toggleSound}
                  title={soundOn ? "Mute notification sound" : "Enable notification sound"}
                >
                  Sound {soundOn ? "on" : "off"}
                </button>
              </div>
            </div>
            {recentMsgs.length ? (
              <ul className="max-h-40 overflow-y-auto border-b border-border">
                {recentMsgs.slice(0, 5).map((m) => (
                  <li key={m.id} className="border-b border-border/60 px-3 py-2 text-sm last:border-0">
                    <div className="flex justify-between gap-2 text-xs text-muted">
                      <span>From {m.from_name}</span>
                      <span className="shrink-0">{formatShopTime(m.at)}</span>
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-xs">{m.body}</p>
                    {(m.ro_id || m.work_item_id) && (
                      <p className="mt-0.5 text-[11px] text-muted">
                        {m.ro_id ? (
                          <Link
                            to={`/ro/${m.ro_id}`}
                            className="text-accent hover:underline"
                            onClick={() => setOpen(false)}
                          >
                            {m.ro_id}
                          </Link>
                        ) : null}
                        {m.work_item_id ? ` · ${m.work_item_id}` : ""}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            ) : null}
            {idle.length ? (
              <>
                <div className="border-b border-border px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
                  Needs attention
                  {idleHours > 0 ? ` · ≥ ${idleHours}h idle` : ""}
                </div>
                <ul className="max-h-56 overflow-y-auto border-b border-border">
                  {idle.map((row) => (
                    <li
                      key={row.fingerprint}
                      className="border-b border-border/60 px-3 py-2 text-sm last:border-0"
                    >
                      <div className="flex justify-between gap-2 text-xs text-muted">
                        <span>{idleKindLabel(row.kind)}</span>
                        <span className="shrink-0">
                          {row.idle_hours != null ? `${row.idle_hours}h` : ""}
                        </span>
                      </div>
                      <Link
                        to={`/ro/${row.ro_id}`}
                        className="font-medium text-accent hover:underline"
                        onClick={() => setOpen(false)}
                      >
                        {row.ro_id}
                      </Link>
                      {row.work_item_id ? (
                        <span className="text-muted"> · {row.work_item_id}</span>
                      ) : null}
                      {row.part_id ? (
                        <span className="text-muted"> · {row.part_id}</span>
                      ) : null}
                      {row.status ? (
                        <div className="text-xs text-muted">{formatStatus(row.status)}</div>
                      ) : null}
                      {row.summary ? (
                        <p className="mt-0.5 line-clamp-2 text-xs text-muted">{row.summary}</p>
                      ) : null}
                      {row.idle_since ? (
                        <p className="mt-0.5 text-[11px] text-muted">
                          Last activity {formatShopTime(row.idle_since)}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            <div className="border-b border-border px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
              Team updates
            </div>
            {note ? <p className="px-3 py-2 text-xs text-muted">{note}</p> : null}
            {empty ? (
              <p className="px-3 py-4 text-sm text-muted">
                No messages, idle work, or updates from others.
              </p>
            ) : events.length === 0 ? (
              <p className="px-3 py-3 text-sm text-muted">No team updates yet.</p>
            ) : (
              <ul className="max-h-80 overflow-y-auto">
                {events.map((e) => (
                  <li
                    key={String(e.id ?? `${e.at}-${e.type}`)}
                    className="border-b border-border/60 px-3 py-2 text-sm last:border-0"
                  >
                    <div className="flex justify-between gap-2 text-xs text-muted">
                      <span>{eventLabel(e.type)}</span>
                      <span className="shrink-0">{e.at?.slice(11, 19) || ""}</span>
                    </div>
                    {e.ro_id && e.ro_id !== "_message" ? (
                      <Link
                        to={`/ro/${e.ro_id}`}
                        className="font-medium text-accent hover:underline"
                        onClick={() => setOpen(false)}
                      >
                        {e.ro_id}
                      </Link>
                    ) : e.type === "shop_message" ? (
                      <Link
                        to="/messages"
                        className="font-medium text-accent hover:underline"
                        onClick={() => setOpen(false)}
                      >
                        Open message
                      </Link>
                    ) : null}
                    {e.item_id ? <span className="text-muted"> · {e.item_id}</span> : null}
                    {e.actor ? <div className="text-xs text-muted">{e.actor}</div> : null}
                    {e.summary ? (
                      <p className="mt-0.5 line-clamp-2 text-xs text-muted">
                        {formatEventSummary(e.summary)}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}
