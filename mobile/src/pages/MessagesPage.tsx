import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, MessageSquarePlus, Search, Send } from "lucide-react";
import { api, type Person, type ShopMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn, formatMsgTime, initials } from "@/lib/utils";

type Conversation = {
  key: string;
  person: Person;
  last: ShopMessage;
  unread: number;
  preview: string;
};

function roleLabel(role: string): string {
  return role === "advisor" ? "Advisor" : "Tech";
}

function otherParty(m: ShopMessage, meId: string): Person {
  if (m.from_id === meId) {
    return {
      id: m.to_id,
      name: m.to_name || m.to_id,
      role: m.to_role === "advisor" ? "advisor" : "technician",
    };
  }
  return {
    id: m.from_id,
    name: m.from_name || m.from_id,
    role: m.from_role === "advisor" ? "advisor" : "technician",
  };
}

function buildConversations(inbox: ShopMessage[], sent: ShopMessage[], meId: string): Conversation[] {
  const map = new Map<string, Conversation>();
  for (const m of [...inbox, ...sent]) {
    const person = otherParty(m, meId);
    if (!person.id || person.id === meId) continue;
    const key = `${person.role}:${person.id}`;
    const unreadBump = m.to_id === meId && !m.read_at ? 1 : 0;
    const existing = map.get(key);
    if (!existing) {
      map.set(key, { key, person, last: m, unread: unreadBump, preview: m.body });
      continue;
    }
    existing.unread += unreadBump;
    if (String(m.at || "") >= String(existing.last.at || "")) {
      existing.last = m;
      existing.preview = m.body;
      existing.person = person;
    }
  }
  return [...map.values()].sort((a, b) =>
    String(b.last.at || "").localeCompare(String(a.last.at || "")),
  );
}

function isBetween(m: ShopMessage, meId: string, otherId: string): boolean {
  return (
    (m.from_id === meId && m.to_id === otherId) ||
    (m.from_id === otherId && m.to_id === meId)
  );
}

export function MessagesPage({
  id,
  name,
  role,
}: {
  id: string;
  name: string;
  role: string;
}) {
  const [people, setPeople] = useState<Person[]>([]);
  const [inbox, setInbox] = useState<ShopMessage[]>([]);
  const [sent, setSent] = useState<ShopMessage[]>([]);
  const [error, setError] = useState("");
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [compose, setCompose] = useState("");
  const [sending, setSending] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerFilter, setPickerFilter] = useState("");
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const fromRole = role === "advisor" ? "advisor" : "technician";
  const conversations = useMemo(() => buildConversations(inbox, sent, id), [inbox, sent, id]);

  const activePerson = useMemo(() => {
    if (!activeKey) return null;
    return (
      conversations.find((c) => c.key === activeKey)?.person ||
      people.find((p) => `${p.role === "advisor" ? "advisor" : "technician"}:${p.id}` === activeKey) ||
      null
    );
  }, [activeKey, conversations, people]);

  const thread = useMemo(() => {
    if (!activePerson) return [];
    return [...inbox, ...sent]
      .filter((m) => isBetween(m, id, activePerson.id))
      .sort((a, b) => String(a.at || "").localeCompare(String(b.at || "")));
  }, [activePerson, id, inbox, sent]);

  const pickerPeople = useMemo(() => {
    const q = pickerFilter.trim().toLowerCase();
    const rows = people.filter((p) => p.id !== id);
    if (!q) return rows;
    return rows.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        roleLabel(p.role).toLowerCase().includes(q),
    );
  }, [people, pickerFilter, id]);

  const load = useCallback(async () => {
    try {
      const [p, incoming, outgoing] = await Promise.all([
        api.people(),
        api.messages(id),
        api.sentMessages(id),
      ]);
      setPeople(p.people || []);
      const msgs = incoming.messages || [];
      setInbox(msgs);
      setSent(outgoing.messages || []);
      const undelivered = msgs
        .filter((m) => !m.delivered_at && !m.read_at)
        .map((m) => m.id);
      if (undelivered.length) {
        void api.markDelivered(undelivered, id).catch(() => undefined);
      }
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load messages");
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const t = window.setInterval(() => void load(), 8000);
    return () => window.clearInterval(t);
  }, [load]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [thread.length, activeKey]);

  async function openConversation(person: Person) {
    const key = `${person.role === "advisor" ? "advisor" : "technician"}:${person.id}`;
    setActiveKey(key);
    setPickerOpen(false);
    setPickerFilter("");
    setCompose("");
    setError("");
    const unread = [...inbox, ...sent].filter(
      (m) => m.to_id === id && m.from_id === person.id && !m.read_at,
    );
    for (const m of unread) {
      void api.markRead(m.id, id).catch(() => undefined);
    }
    if (unread.length) {
      setInbox((prev) =>
        prev.map((m) =>
          unread.some((u) => u.id === m.id) ? { ...m, read_at: m.read_at || new Date().toISOString() } : m,
        ),
      );
    }
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function send() {
    if (!activePerson || !compose.trim()) return;
    setSending(true);
    setError("");
    try {
      await api.sendMessage({
        body: compose.trim(),
        from_id: id,
        from_name: name,
        from_role: fromRole,
        to_id: activePerson.id,
        to_role: activePerson.role === "advisor" ? "advisor" : "technician",
        to_name: activePerson.name,
      });
      setCompose("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Send failed");
    } finally {
      setSending(false);
    }
  }

  if (activePerson) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <header className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-2.5">
          <button
            type="button"
            className="flex h-10 w-10 items-center justify-center rounded-full text-fg"
            onClick={() => setActiveKey(null)}
            aria-label="Back to conversations"
          >
            <ArrowLeft size={20} />
          </button>
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent/15 text-xs font-semibold text-accent">
            {initials(activePerson.name)}
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{activePerson.name}</p>
            <p className="text-[10px] font-medium uppercase tracking-wide text-muted">
              {roleLabel(activePerson.role)}
            </p>
          </div>
        </header>

        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-3">
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          {thread.length === 0 ? (
            <p className="pt-8 text-center text-sm text-muted">Say hello — no messages yet.</p>
          ) : (
            thread.map((m) => {
              const mine = m.from_id === id;
              return (
                <div key={m.id} className={cn("flex", mine ? "justify-end" : "justify-start")}>
                  <div
                    className={cn(
                      "max-w-[82%] rounded-2xl px-3.5 py-2 text-sm",
                      mine
                        ? "rounded-br-md bg-accent text-accent-fg"
                        : "rounded-bl-md bg-surface text-fg ring-1 ring-border",
                    )}
                  >
                    <p className="whitespace-pre-wrap break-words">{m.body}</p>
                    <div
                      className={cn(
                        "mt-1 flex flex-wrap items-center gap-x-2 text-[10px]",
                        mine ? "text-accent-fg/75" : "text-muted",
                      )}
                    >
                      <span>{formatMsgTime(m.at)}</span>
                      {mine ? (
                        <span>
                          {m.read_at ? "Read" : m.delivered_at ? "Delivered" : "Sent"}
                        </span>
                      ) : null}
                      {m.ro_id ? (
                        <Link
                          to={`/ro/${m.ro_id}`}
                          className={cn(
                            "underline-offset-2 hover:underline",
                            mine ? "text-accent-fg" : "text-accent",
                          )}
                        >
                          {m.ro_id}
                        </Link>
                      ) : null}
                    </div>
                  </div>
                </div>
              );
            })
          )}
          <div ref={bottomRef} />
        </div>

        <form
          className="shrink-0 border-t border-border bg-bg px-3 py-2"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <div className="flex items-end gap-2 rounded-2xl border border-border bg-surface px-2 py-1.5">
            <textarea
              ref={textareaRef}
              rows={1}
              maxLength={4000}
              className="max-h-28 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-base outline-none"
              placeholder={`Message ${activePerson.name.split(" ")[0]}…`}
              value={compose}
              onChange={(e) => setCompose(e.target.value)}
            />
            <Button
              type="submit"
              size="sm"
              className="mb-0.5 shrink-0 rounded-full"
              disabled={sending || !compose.trim()}
              aria-label="Send"
            >
              <Send size={16} />
            </Button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 items-center justify-between gap-3 px-4 pb-2 pt-3">
        <div>
          <h1 className="font-display text-xl font-semibold tracking-tight">Messages</h1>
          <p className="text-xs text-muted">
            {conversations.reduce((n, c) => n + c.unread, 0) > 0
              ? `${conversations.reduce((n, c) => n + c.unread, 0)} unread`
              : "Techs and advisors"}
          </p>
        </div>
        <Button type="button" size="sm" onClick={() => setPickerOpen(true)}>
          <MessageSquarePlus size={14} />
          New
        </Button>
      </div>
      {error ? <p className="px-4 pb-2 text-sm text-danger">{error}</p> : null}

      <div className="min-h-0 flex-1 overflow-y-auto">
        {conversations.length === 0 ? (
          <div className="space-y-3 px-4 py-10 text-center text-sm text-muted">
            <p>No conversations yet.</p>
            <Button type="button" size="sm" onClick={() => setPickerOpen(true)}>
              Message someone
            </Button>
          </div>
        ) : (
          <ul>
            {conversations.map((c) => (
              <li key={c.key}>
                <button
                  type="button"
                  onClick={() => void openConversation(c.person)}
                  className="flex w-full items-start gap-3 border-b border-border/70 px-4 py-3 text-left active:bg-border/30"
                >
                  <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-accent/15 text-xs font-semibold text-accent">
                    {initials(c.person.name)}
                    {c.unread > 0 ? (
                      <span className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-accent px-1 text-[10px] font-semibold leading-4 text-accent-fg">
                        {c.unread}
                      </span>
                    ) : null}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-sm font-semibold">{c.person.name}</span>
                      <span className="shrink-0 text-[11px] text-muted">{formatMsgTime(c.last.at)}</span>
                    </span>
                    <span className="mt-0.5 block text-[10px] font-medium uppercase tracking-wide text-muted">
                      {roleLabel(c.person.role)}
                    </span>
                    <span
                      className={cn(
                        "mt-0.5 block truncate text-sm",
                        c.unread > 0 ? "font-medium text-fg" : "text-muted",
                      )}
                    >
                      {c.last.from_id === id ? "You: " : ""}
                      {c.preview}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {pickerOpen ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40">
          <button
            type="button"
            className="absolute inset-0"
            aria-label="Close"
            onClick={() => setPickerOpen(false)}
          />
          <div className="relative z-10 flex max-h-[80dvh] w-full max-w-lg flex-col rounded-t-2xl border border-border bg-surface pb-[env(safe-area-inset-bottom)] shadow-lg">
            <div className="border-b border-border px-4 pb-3 pt-4">
              <h2 className="font-display text-lg font-semibold">New message</h2>
              <label className="relative mt-3 block">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
                <input
                  autoFocus
                  className="h-11 w-full rounded-xl border border-border bg-bg py-2 pl-9 pr-3 text-base outline-none focus:border-accent"
                  placeholder="Search staff…"
                  value={pickerFilter}
                  onChange={(e) => setPickerFilter(e.target.value)}
                />
              </label>
            </div>
            <ul className="min-h-0 flex-1 overflow-y-auto">
              {pickerPeople.length === 0 ? (
                <li className="p-4 text-sm text-muted">No matching staff.</li>
              ) : (
                pickerPeople.map((p) => (
                  <li key={`${p.role}:${p.id}`}>
                    <button
                      type="button"
                      className="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-border/40"
                      onClick={() => void openConversation(p)}
                    >
                      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-accent/15 text-xs font-semibold text-accent">
                        {initials(p.name)}
                      </span>
                      <span>
                        <span className="block text-sm font-medium">{p.name}</span>
                        <span className="text-[10px] font-medium uppercase tracking-wide text-muted">
                          {roleLabel(p.role)}
                        </span>
                      </span>
                    </button>
                  </li>
                ))
              )}
            </ul>
            <div className="border-t border-border p-3">
              <Button type="button" variant="secondary" className="w-full" onClick={() => setPickerOpen(false)}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
