import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ShopMessage } from "@/lib/api";
import { MessageComposeDialog } from "@/components/MessageComposeDialog";
import { Button } from "@/components/ui/button";
import { formatShopTime } from "@/lib/utils";

const RENOTIFY_GAP_MS = 15 * 60 * 1000;

function canRenotify(m: ShopMessage): boolean {
  if (m.read_at) return false;
  const last = m.last_notified_at || m.at;
  const t = Date.parse(last);
  if (!Number.isFinite(t)) return true;
  return Date.now() - t >= RENOTIFY_GAP_MS;
}

export function MessagesPage() {
  const [tab, setTab] = useState<"inbox" | "sent">("inbox");
  const [messages, setMessages] = useState<ShopMessage[]>([]);
  const [unread, setUnread] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [compose, setCompose] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setErr("");
    try {
      if (tab === "inbox") {
        const r = await api.listMessages({ limit: 100 });
        setMessages(r.messages || []);
        setUnread(r.unread ?? 0);
      } else {
        const r = await api.listSentMessages({ limit: 100 });
        setMessages(r.messages || []);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load messages");
      setMessages([]);
    } finally {
      setBusy(false);
    }
  }, [tab]);

  useEffect(() => {
    void load();
  }, [load]);

  async function markRead(id: number) {
    try {
      await api.markMessageRead(id);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not mark read");
    }
  }

  async function renotify(id: number) {
    try {
      await api.renotifyMessage(id);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not renotify");
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 px-5 py-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold tracking-tight">
            Messages
          </h1>
          <p className="mt-1 text-sm text-muted">
            Person-to-person notes · optional work item tag
            {unread > 0 ? ` · ${unread} unread` : ""}
          </p>
        </div>
        <Button type="button" onClick={() => setCompose(true)}>
          New message
        </Button>
      </div>

      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          variant={tab === "inbox" ? "default" : "secondary"}
          onClick={() => setTab("inbox")}
        >
          Inbox
        </Button>
        <Button
          type="button"
          size="sm"
          variant={tab === "sent" ? "default" : "secondary"}
          onClick={() => setTab("sent")}
        >
          Sent
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => void load()} disabled={busy}>
          Refresh
        </Button>
      </div>

      {err ? <p className="text-sm text-red-600 dark:text-red-400">{err}</p> : null}

      {busy && !messages.length ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : !messages.length ? (
        <p className="text-sm text-muted">No messages yet.</p>
      ) : (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
          {messages.map((m) => {
            const unreadRow = tab === "inbox" && !m.read_at;
            const sentUnread = tab === "sent" && !m.read_at;
            return (
              <li key={m.id} className="px-4 py-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                      <span>{formatShopTime(m.at)}</span>
                      {unreadRow ? (
                        <span className="rounded bg-accent/15 px-1.5 py-0.5 font-medium text-accent">
                          unread
                        </span>
                      ) : null}
                      {tab === "sent" ? (
                        m.read_at ? (
                          <span className="rounded bg-border/80 px-1.5 py-0.5 font-medium">
                            Read {formatShopTime(m.read_at)}
                          </span>
                        ) : (
                          <span className="rounded bg-accent/15 px-1.5 py-0.5 font-medium text-accent">
                            Unread
                          </span>
                        )
                      ) : null}
                      {(m.renotify_count || 0) > 0 ? (
                        <span className="text-muted">
                          Renotified {m.renotify_count}×
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-0.5 text-sm font-medium">
                      {tab === "inbox" ? (
                        <>
                          From {m.from_name}{" "}
                          <span className="font-normal text-muted">({m.from_role})</span>
                        </>
                      ) : (
                        <>
                          To {m.to_name}{" "}
                          <span className="font-normal text-muted">({m.to_role})</span>
                        </>
                      )}
                    </p>
                    <p className="mt-1 whitespace-pre-wrap text-sm">{m.body}</p>
                    {(m.ro_id || m.work_item_id) && (
                      <p className="mt-1 text-xs text-muted">
                        {m.ro_id ? (
                          <Link to={`/ro/${m.ro_id}`} className="text-accent hover:underline">
                            {m.ro_id}
                          </Link>
                        ) : null}
                        {m.work_item_id ? ` · ${m.work_item_id}` : ""}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-col gap-2">
                    {unreadRow ? (
                      <Button type="button" size="sm" variant="secondary" onClick={() => void markRead(m.id)}>
                        Mark read
                      </Button>
                    ) : null}
                    {sentUnread ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        disabled={!canRenotify(m)}
                        title={
                          canRenotify(m)
                            ? "Ping the recipient again"
                            : "Wait 15 minutes between renotifies"
                        }
                        onClick={() => void renotify(m.id)}
                      >
                        Renotify
                      </Button>
                    ) : null}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <MessageComposeDialog
        open={compose}
        onClose={() => setCompose(false)}
        onSent={() => void load()}
      />
    </div>
  );
}
