import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

const POLL_MS = 12_000;

type SyncStatus = {
  ok?: boolean;
  offline?: boolean;
  server_configured?: boolean;
  server_reachable?: boolean;
  pending?: {
    pending_total?: number;
    pending_ros?: number;
    pending_shifts?: number;
    pending_messages?: number;
  };
};

/** Sticky strip when shop server is configured but unreachable. */
export function OfflineBanner() {
  const [offline, setOffline] = useState(false);
  const [pending, setPending] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const st = (await api.syncStatus()) as SyncStatus;
      setOffline(Boolean(st.offline));
      setPending(Number(st.pending?.pending_total || 0));
    } catch {
      /* engine down — separate problem; do not claim shop offline */
    }
  }, []);

  useEffect(() => {
    void refresh();
    const t = window.setInterval(() => void refresh(), POLL_MS);
    const onFocus = () => void refresh();
    const onOnline = () => {
      void (async () => {
        try {
          await api.sync();
        } catch {
          /* best-effort drain */
        }
        await refresh();
      })();
    };
    window.addEventListener("focus", onFocus);
    window.addEventListener("online", onOnline);
    return () => {
      window.clearInterval(t);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("online", onOnline);
    };
  }, [refresh]);

  if (!offline) return null;

  return (
    <div
      role="status"
      className="border-b border-amber-600/40 bg-amber-500/15 px-5 py-2 text-sm text-amber-950 dark:text-amber-50"
    >
      <div className="mx-auto max-w-6xl">
        <p className="font-medium">
          You&apos;re offline (shop server unreachable).
        </p>
        <p className="mt-0.5 text-xs opacity-90">
          Updates, notifications, and messages will send/receive when this machine
          reconnects.
          {pending > 0 ? (
            <span className="ml-1 font-medium">
              {pending} change{pending === 1 ? "" : "s"} waiting to sync.
            </span>
          ) : null}
        </p>
      </div>
    </div>
  );
}
