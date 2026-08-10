import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bell } from "lucide-react";
import { api, type RoEvent } from "@/lib/api";
import { eventLabel, filterOthersEvents, formatEventSummary } from "@/lib/notifications";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SEEN_KEY = "carro.notifications.seen_id";

/**
 * Tech↔tech live feed (assignment / item updates from others).
 * Engine/server already drop the maker's own events; we also filter client-side.
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
  const [unread, setUnread] = useState(0);
  const [note, setNote] = useState<string | null>(null);
  const lastId = useRef(0);
  const seenId = useRef(Number(localStorage.getItem(SEEN_KEY) || 0));
  const self = { name: techName, id: techId };

  const mergeEvents = useCallback((batch: RoEvent[], replace: boolean) => {
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
  }, [techName, techId]);

  const poll = useCallback(async () => {
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
        const fresh = others.filter((e) => Number(e.id) > seenId.current).length;
        if (fresh > 0 && !open) setUnread((u) => u + fresh);
      }
    } catch {
      /* offline / no server — quiet */
    }
  }, [mergeEvents, techName, techId, open]);

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
          setUnread(others.filter((e) => Number(e.id) > seenId.current).length);
        }
      } catch {
        /* ignore */
      }
    })();
  }, [techName, techId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const t = window.setInterval(() => void poll(), 8000);
    return () => window.clearInterval(t);
  }, [poll]);

  function markSeen() {
    if (lastId.current > seenId.current) {
      seenId.current = lastId.current;
      localStorage.setItem(SEEN_KEY, String(seenId.current));
    }
    setUnread(0);
  }

  return (
    <div className="relative">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label="Notifications"
        className="relative"
        onClick={() => {
          setOpen((o) => !o);
          if (!open) markSeen();
        }}
      >
        <Bell className="h-4 w-4" />
        {unread > 0 ? (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold text-accent-fg">
            {unread > 9 ? "9+" : unread}
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
            <div className="border-b border-border px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
              Team updates
            </div>
            {note ? <p className="px-3 py-2 text-xs text-muted">{note}</p> : null}
            {events.length === 0 ? (
              <p className="px-3 py-4 text-sm text-muted">
                No updates from other techs yet. Your own edits stay silent.
              </p>
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
                    <Link
                      to={`/ro/${e.ro_id}`}
                      className="font-medium text-accent hover:underline"
                      onClick={() => setOpen(false)}
                    >
                      {e.ro_id}
                    </Link>
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
