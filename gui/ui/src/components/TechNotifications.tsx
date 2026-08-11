import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bell, X } from "lucide-react";
import { api, type IdleNudge, type RoEvent, type ShopMessage } from "@/lib/api";
import { eventLabel, filterOthersEvents, filterTechRelevantEvents, formatEventSummary } from "@/lib/notifications";
import type { TechNotifyScope } from "@/lib/notifications";
import {
  eventDismissKey,
  idleDismissKey,
  isDismissed,
  loadDismissed,
  msgDismissKey,
  resolvingClearsType,
  sameWorkTarget,
  saveDismissed,
} from "@/lib/notifyDismiss";
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

function formatIdleThreshold(hours?: number | null, fallback = 24): string {
  const h = hours != null && hours > 0 ? hours : fallback;
  if (h >= 168) return "7d";
  if (h % 24 === 0 && h >= 48) return `${h / 24}d`;
  return `${h}h`;
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
  const dismissed = useRef(loadDismissed());
  const primed = useRef(false);
  const techScope = useRef<TechNotifyScope>({ roIds: new Set(), itemIds: new Set() });
  const self = { name: techName, id: techId };
  const soundOn = prefs.sound;

  // Auto-close the panel after idle. Do not reset on pointermove — poll re-renders
  // under the cursor can keep firing move events and the menu never hides.
  const PANEL_IDLE_MS = 10_000;
  const idleTimer = useRef<number | null>(null);
  const openRef = useRef(open);
  openRef.current = open;

  const clearIdleClose = useCallback(() => {
    if (idleTimer.current != null) {
      window.clearTimeout(idleTimer.current);
      idleTimer.current = null;
    }
  }, []);

  const bumpIdleClose = useCallback(() => {
    clearIdleClose();
    if (!openRef.current) return;
    idleTimer.current = window.setTimeout(() => {
      idleTimer.current = null;
      setOpen(false);
    }, PANEL_IDLE_MS);
  }, [clearIdleClose]);

  useEffect(() => {
    if (!open) {
      clearIdleClose();
      return;
    }
    bumpIdleClose();
    return clearIdleClose;
  }, [open, bumpIdleClose, clearIdleClose]);

  const rememberDismiss = useCallback((key: string | null) => {
    if (!key) return;
    dismissed.current.add(key);
    saveDismissed(dismissed.current);
  }, []);

  const refreshTechScope = useCallback(async () => {
    if (!techId) {
      techScope.current = { roIds: new Set(), itemIds: new Set() };
      return;
    }
    try {
      const board = await api.assignedBoard();
      const roIds = new Set<string>();
      const itemIds = new Set<string>();
      const add = (j?: { ro_id?: string; item_id?: string; id?: string } | null) => {
        if (!j) return;
        const ro = String(j.ro_id || "").trim();
        if (ro) roIds.add(ro);
        const iid = String(j.item_id || j.id || "").trim();
        if (iid) itemIds.add(iid);
      };
      for (const j of board.mine || []) add(j);
      for (const j of board.mine_daily || []) add(j);
      for (const j of board.mine_next_day || []) add(j);
      for (const j of board.mine_long_term || []) add(j);
      add(board.my_current);
      techScope.current = { roIds, itemIds };
    } catch {
      /* keep previous scope */
    }
  }, [techId]);

  const autoClearResolved = useCallback((list: RoEvent[]) => {
    let changed = false;
    for (const e of list) {
      const clears = resolvingClearsType(e.type);
      if (!clears) continue;
      for (const other of list) {
        if (other.type !== clears) continue;
        if (!sameWorkTarget(e, other)) continue;
        const key = eventDismissKey(other.id);
        if (key && !dismissed.current.has(key)) {
          dismissed.current.add(key);
          changed = true;
        }
      }
    }
    if (changed) saveDismissed(dismissed.current);
  }, []);

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
      const batchMax = batch.reduce((m, e) => Math.max(m, Number(e.id) || 0), 0);
      if (batchMax > lastId.current) lastId.current = batchMax;

      const others = filterTechRelevantEvents(
        filterOthersEvents(batch, self),
        self,
        techScope.current,
      ).filter((e) => !isDismissed(dismissed.current, eventDismissKey(e.id)));
      if (!others.length && !replace) return { others, maxId: lastId.current };
      autoClearResolved(others);
      const still = others.filter(
        (e) => !isDismissed(dismissed.current, eventDismissKey(e.id)),
      );
      setEvents((prev) => {
        const merged = replace
          ? still.slice().reverse()
          : [...still.slice().reverse(), ...prev];
        const byId = new Map<string, RoEvent>();
        for (const e of merged) {
          const key = String(e.id ?? `${e.at}-${e.type}-${e.ro_id}`);
          if (isDismissed(dismissed.current, eventDismissKey(e.id))) continue;
          byId.set(key, e);
        }
        autoClearResolved(Array.from(byId.values()));
        for (const [k, e] of [...byId.entries()]) {
          if (isDismissed(dismissed.current, eventDismissKey(e.id))) byId.delete(k);
        }
        return Array.from(byId.values()).slice(0, 40);
      });
      return { others: still, maxId: lastId.current };
    },
    [techName, techId, autoClearResolved],
  );

  const mergeIdle = useCallback((rows: IdleNudge[]) => {
    const panel = rows
      .filter((r) => !isDismissed(dismissed.current, idleDismissKey(r.fingerprint)))
      .slice(0, 40);
    setIdle(panel);
    const active = new Set(panel.map((r) => r.fingerprint).filter(Boolean));
    for (const fp of [...idleBadgeCounted.current]) {
      if (!active.has(fp)) idleBadgeCounted.current.delete(fp);
    }
    let fresh = 0;
    for (const row of panel) {
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

  const wasOffline = useRef(false);
  const reconnecting = useRef(false);

  const ackDelivered = useCallback(async (msgs: ShopMessage[]) => {
    const ids = msgs
      .filter((m) => m.id && !m.delivered_at && !m.read_at)
      .map((m) => Number(m.id))
      .filter((id) => id > 0);
    if (!ids.length) return;
    try {
      await api.markMessagesDelivered(ids);
    } catch {
      /* offline / older server */
    }
  }, []);

  /** Inbox rows addressed to me only — never treat my outbound sends as notifies. */
  const inboxForMe = useCallback(
    (msgs: ShopMessage[]) => {
      const myId = (techId || "").trim().toLowerCase();
      if (!myId) return [];
      return msgs.filter((m) => {
        const to = String(m.to_id || "").trim().toLowerCase();
        const from = String(m.from_id || "").trim().toLowerCase();
        if (from && from === myId) return false;
        return to === myId && !m.read_at;
      });
    },
    [techId],
  );

  const catchUpEvents = useCallback(
    async (opts?: { pageLimit?: number; maxPages?: number }) => {
      await refreshTechScope();
      const pageLimit = opts?.pageLimit ?? 100;
      const maxPages = opts?.maxPages ?? 5;
      let ping: "message" | "update" | null = null;
      let pages = 0;
      while (pages < maxPages) {
        pages += 1;
        const r = await api.listEvents({
          since_id: lastId.current || undefined,
          limit: pageLimit,
          exclude_actor: techName || undefined,
          exclude_actor_id: techId || undefined,
        });
        setNote(r.note ?? null);
        const batch = r.events || [];
        if (!batch.length) break;
        const { others } = mergeEvents(batch, false);
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
        if (batch.length < pageLimit) break;
      }
      return ping;
    },
    [mergeEvents, refreshTechScope, techName, techId, open, prefs],
  );

  const onReconnect = useCallback(async () => {
    if (reconnecting.current) return;
    reconnecting.current = true;
    try {
      try {
        const st = await api.syncStatus();
        const pending = Number(st.pending?.pending_total || 0);
        if (pending > 0) {
          await api.sync().catch(() => undefined);
        }
      } catch {
        /* ignore */
      }
      let ping: "message" | "update" | null = null;
      try {
        ping = await catchUpEvents({ pageLimit: 100, maxPages: 5 });
      } catch {
        /* still offline */
        return;
      }
      try {
        const r = await api.listIdleNotifications(techId ? { assignee_id: techId } : undefined);
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
        /* ignore */
      }
      try {
        if (!prefs.shopMessages) {
          setMsgUnread(0);
          setRecentMsgs([]);
        } else {
          const r = await api.listMessages({ unread: true, limit: 20 });
          const raw = inboxForMe(r.messages || []);
          void ackDelivered(raw);
          const msgs = raw.filter(
            (m) => !isDismissed(dismissed.current, msgDismissKey(m.id)),
          );
          setRecentMsgs(msgs);
          const count = msgs.length;
          setMsgUnread(count);
          const maxMsgId = msgs.reduce((m, x) => Math.max(m, Number(x.id) || 0), 0);
          if (primed.current && maxMsgId > msgSeenId.current && count > 0) {
            ping = "message";
            msgSeenId.current = maxMsgId;
            localStorage.setItem(MSG_SEEN_KEY, String(maxMsgId));
          }
        }
      } catch {
        /* ignore */
      }
      wasOffline.current = false;
      if (ping) chime(ping);
    } finally {
      reconnecting.current = false;
    }
  }, [catchUpEvents, mergeIdle, prefs, open, ackDelivered, inboxForMe, chime]);

  const poll = useCallback(async () => {
    /** Any new notif this tick — sound module coalesces bursts. */
    let ping: "message" | "update" | null = null;
    let eventsOk = false;
    try {
      ping = (await catchUpEvents({ pageLimit: 30, maxPages: 1 })) || null;
      eventsOk = true;
      if (wasOffline.current) {
        void onReconnect();
        return;
      }
    } catch {
      wasOffline.current = true;
    }
    try {
      const r = await api.listIdleNotifications(techId ? { assignee_id: techId } : undefined);
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
        const raw = inboxForMe(r.messages || []);
        void ackDelivered(raw);
        const msgs = raw.filter(
          (m) => !isDismissed(dismissed.current, msgDismissKey(m.id)),
        );
        setRecentMsgs(msgs);
        const count = msgs.length;
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
      if (!eventsOk) wasOffline.current = true;
      setMsgUnread(0);
      setRecentMsgs([]);
    }
    if (ping) chime(ping);
  }, [
    catchUpEvents,
    onReconnect,
    mergeIdle,
    techName,
    techId,
    open,
    chime,
    prefs,
    ackDelivered,
    inboxForMe,
  ]);

  useEffect(() => {
    void (async () => {
      await refreshTechScope();
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
        wasOffline.current = true;
      }
      try {
        const r = await api.listIdleNotifications(techId ? { assignee_id: techId } : undefined);
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
          const raw = inboxForMe(r.messages || []);
          void ackDelivered(raw);
          const msgs = raw.filter(
            (m) => !isDismissed(dismissed.current, msgDismissKey(m.id)),
          );
          setRecentMsgs(msgs);
          setMsgUnread(msgs.length);
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

  useEffect(() => {
    const kick = () => {
      if (wasOffline.current || !navigator.onLine) {
        wasOffline.current = true;
        void onReconnect();
      }
    };
    const onOnline = () => {
      wasOffline.current = true;
      void onReconnect();
    };
    const onVis = () => {
      if (document.visibilityState === "visible") kick();
    };
    window.addEventListener("online", onOnline);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.removeEventListener("online", onOnline);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [onReconnect]);

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

  function dismissEvent(e: RoEvent) {
    const key = eventDismissKey(e.id);
    rememberDismiss(key);
    setEvents((prev) => prev.filter((x) => String(x.id) !== String(e.id)));
    if (Number(e.id) > seenId.current) {
      setUnread((u) => Math.max(0, u - 1));
    }
  }

  function dismissIdle(row: IdleNudge) {
    const key = idleDismissKey(row.fingerprint);
    rememberDismiss(key);
    if (row.fingerprint) {
      idleSeen.current.add(row.fingerprint);
      saveIdleSeen(idleSeen.current);
    }
    setIdle((prev) => prev.filter((r) => r.fingerprint !== row.fingerprint));
    setUnread((u) => Math.max(0, u - 1));
  }

  async function dismissMessage(m: ShopMessage) {
    const key = msgDismissKey(m.id);
    rememberDismiss(key);
    setRecentMsgs((prev) => prev.filter((x) => x.id !== m.id));
    setMsgUnread((n) => Math.max(0, n - 1));
    try {
      if (!m.read_at) await api.markMessageRead(m.id);
    } catch {
      /* offline — stays dismissed locally */
    }
  }

  function dismissAllVisible() {
    for (const e of events) rememberDismiss(eventDismissKey(e.id));
    for (const row of idle) {
      rememberDismiss(idleDismissKey(row.fingerprint));
      if (row.fingerprint) idleSeen.current.add(row.fingerprint);
    }
    saveIdleSeen(idleSeen.current);
    for (const m of recentMsgs) {
      rememberDismiss(msgDismissKey(m.id));
      if (!m.read_at) void api.markMessageRead(m.id).catch(() => undefined);
    }
    setEvents([]);
    setIdle([]);
    setRecentMsgs([]);
    setUnread(0);
    setMsgUnread(0);
    markSeen();
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
            onPointerDown={bumpIdleClose}
            onWheel={bumpIdleClose}
            onScroll={bumpIdleClose}
            onKeyDown={bumpIdleClose}
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
                {!empty ? (
                  <button
                    type="button"
                    className="text-[11px] text-muted hover:text-fg"
                    onClick={() => dismissAllVisible()}
                    title="Dismiss all visible notifications"
                  >
                    Clear all
                  </button>
                ) : null}
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
                      <span className="flex shrink-0 items-center gap-1">
                        {formatShopTime(m.at)}
                        <button
                          type="button"
                          className="rounded p-0.5 text-muted hover:bg-border/50 hover:text-fg"
                          aria-label="Dismiss message"
                          title="Dismiss (marks read)"
                          onClick={() => void dismissMessage(m)}
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </span>
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
                  {idleHours > 0 ? ` · ≥ ${formatIdleThreshold(idleHours)} idle` : ""}
                </div>
                <ul className="max-h-56 overflow-y-auto border-b border-border">
                  {idle.map((row) => (
                    <li
                      key={row.fingerprint}
                      className="border-b border-border/60 px-3 py-2 text-sm last:border-0"
                    >
                      <div className="flex justify-between gap-2 text-xs text-muted">
                        <span>
                          {idleKindLabel(row.kind)}
                          {row.idle_threshold_hours != null &&
                          row.idle_threshold_hours !== idleHours
                            ? ` · ≥ ${formatIdleThreshold(row.idle_threshold_hours)}`
                            : ""}
                        </span>
                        <span className="flex shrink-0 items-center gap-1">
                          {row.idle_hours != null ? `${row.idle_hours}h` : ""}
                          <button
                            type="button"
                            className="rounded p-0.5 text-muted hover:bg-border/50 hover:text-fg"
                            aria-label="Dismiss idle nudge"
                            title="Dismiss"
                            onClick={() => dismissIdle(row)}
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </span>
                      </div>
                      <Link
                        to={`/ro/${row.ro_id}`}
                        className="font-medium text-accent hover:underline"
                        onClick={() => {
                          dismissIdle(row);
                          setOpen(false);
                        }}
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
                      <span className="flex shrink-0 items-center gap-1">
                        {e.at?.slice(11, 19) || ""}
                        <button
                          type="button"
                          className="rounded p-0.5 text-muted hover:bg-border/50 hover:text-fg"
                          aria-label="Dismiss update"
                          title="Dismiss"
                          onClick={() => dismissEvent(e)}
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </span>
                    </div>
                    {e.ro_id && e.ro_id !== "_message" && e.ro_id !== "_shift" ? (
                      <Link
                        to={`/ro/${e.ro_id}`}
                        className="font-medium text-accent hover:underline"
                        onClick={() => {
                          dismissEvent(e);
                          setOpen(false);
                        }}
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
                    ) : e.type === "tech_day_start" || e.type === "tech_day_end" ? (
                      <span className="font-medium">{e.summary || eventLabel(e.type)}</span>
                    ) : null}
                    {e.type === "tech_day_start" || e.type === "tech_day_end"
                      ? null
                      : e.item_id ? (
                          <span className="text-muted"> · {e.item_id}</span>
                        ) : null}
                    {e.actor && e.type !== "tech_day_start" && e.type !== "tech_day_end" ? (
                      <div className="text-xs text-muted">{e.actor}</div>
                    ) : null}
                    {e.summary && e.type !== "tech_day_start" && e.type !== "tech_day_end" ? (
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
