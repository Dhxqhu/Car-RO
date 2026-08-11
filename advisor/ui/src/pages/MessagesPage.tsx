import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, MessageSquarePlus, RefreshCw, Search, Send } from "lucide-react";
import { api, type MessagePerson, type ShopMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn, formatShopTime } from "@/lib/utils";

type Conversation = {
  key: string;
  person: MessagePerson;
  last: ShopMessage;
  unread: number;
  preview: string;
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ""}${parts[parts.length - 1][0] || ""}`.toUpperCase();
}

function roleLabel(role: string): string {
  return role === "advisor" ? "Advisor" : "Tech";
}

function otherParty(m: ShopMessage, meId: string): MessagePerson {
  if (m.from_id === meId) {
    return {
      id: m.to_id,
      name: m.to_name || m.to_id,
      role: (m.to_role === "advisor" ? "advisor" : "technician") as MessagePerson["role"],
    };
  }
  return {
    id: m.from_id,
    name: m.from_name || m.from_id,
    role: (m.from_role === "advisor" ? "advisor" : "technician") as MessagePerson["role"],
  };
}

function buildConversations(
  inbox: ShopMessage[],
  sent: ShopMessage[],
  meId: string,
): Conversation[] {
  const map = new Map<string, Conversation>();
  const all = [...inbox, ...sent];
  for (const m of all) {
    const person = otherParty(m, meId);
    if (!person.id || person.id === meId) continue;
    const key = `${person.role}:${person.id}`;
    const unreadBump = m.to_id === meId && !m.read_at ? 1 : 0;
    const existing = map.get(key);
    if (!existing) {
      map.set(key, {
        key,
        person,
        last: m,
        unread: unreadBump,
        preview: m.body,
      });
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

export function MessagesPage() {
  const [people, setPeople] = useState<MessagePerson[]>([]);
  const [meId, setMeId] = useState("");
  const [inbox, setInbox] = useState<ShopMessage[]>([]);
  const [sent, setSent] = useState<ShopMessage[]>([]);
  const [unreadTotal, setUnreadTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [listFilter, setListFilter] = useState("");
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [thread, setThread] = useState<ShopMessage[]>([]);
  const [composeBody, setComposeBody] = useState("");
  const [sending, setSending] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerFilter, setPickerFilter] = useState("");
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const conversations = useMemo(
    () => (meId ? buildConversations(inbox, sent, meId) : []),
    [inbox, sent, meId],
  );

  const filteredConversations = useMemo(() => {
    const q = listFilter.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter(
      (c) =>
        c.person.name.toLowerCase().includes(q) ||
        roleLabel(c.person.role).toLowerCase().includes(q) ||
        c.preview.toLowerCase().includes(q),
    );
  }, [conversations, listFilter]);

  const activePerson = useMemo(() => {
    if (!activeKey) return null;
    const fromConv = conversations.find((c) => c.key === activeKey)?.person;
    if (fromConv) return fromConv;
    return people.find((p) => `${p.role}:${p.id}` === activeKey) || null;
  }, [activeKey, conversations, people]);

  const filteredPeople = useMemo(() => {
    const q = pickerFilter.trim().toLowerCase();
    const rows = people;
    if (!q) return rows;
    return rows.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        roleLabel(p.role).toLowerCase().includes(q),
    );
  }, [people, pickerFilter]);

  const loadRoster = useCallback(async () => {
    const r = await api.listMessagePeople();
    setPeople(r.people || []);
    if (r.me?.id) setMeId(r.me.id);
  }, []);

  const loadLists = useCallback(async () => {
    const [inb, out] = await Promise.all([
      api.listMessages({ limit: 200 }),
      api.listSentMessages({ limit: 200 }),
    ]);
    const msgs = inb.messages || [];
    setInbox(msgs);
    setSent(out.messages || []);
    setUnreadTotal(inb.unread ?? 0);
    const undelivered = msgs
      .filter((m) => !m.delivered_at && !m.read_at)
      .map((m) => m.id);
    if (undelivered.length) {
      void api.markMessagesDelivered(undelivered).catch(() => undefined);
    }
    if (!meId && msgs[0]) {
      // Fallback me id from first inbound
      setMeId(msgs[0].to_id);
    }
  }, [meId]);

  const loadThread = useCallback(
    async (person: MessagePerson, opts?: { quiet?: boolean }) => {
      if (!opts?.quiet) setBusy(true);
      try {
        const r = await api.listMessageThread(person.id, { limit: 300 });
        if (r.me?.id) setMeId(r.me.id);
        setThread(r.messages || []);
        const unreadIds = (r.messages || [])
          .filter((m) => m.to_id === (r.me?.id || meId) && !m.read_at)
          .map((m) => m.id);
        for (const id of unreadIds) {
          await api.markMessageRead(id).catch(() => undefined);
        }
        if (unreadIds.length) await loadLists();
      } finally {
        if (!opts?.quiet) setBusy(false);
      }
    },
    [loadLists, meId],
  );

  const refreshAll = useCallback(async () => {
    setBusy(true);
    setErr("");
    try {
      await loadRoster();
      await loadLists();
      if (activePerson) await loadThread(activePerson, { quiet: true });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load messages");
    } finally {
      setBusy(false);
    }
  }, [activePerson, loadLists, loadRoster, loadThread]);

  useEffect(() => {
    void refreshAll();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const id = window.setInterval(() => {
      void (async () => {
        try {
          await loadLists();
          if (activePerson) await loadThread(activePerson, { quiet: true });
        } catch {
          /* ignore poll errors */
        }
      })();
    }, 8000);
    return () => window.clearInterval(id);
  }, [activePerson, loadLists, loadThread]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [thread, activeKey]);

  async function openConversation(person: MessagePerson) {
    const key = `${person.role}:${person.id}`;
    setActiveKey(key);
    setPickerOpen(false);
    setPickerFilter("");
    setComposeBody("");
    setErr("");
    await loadThread(person);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function send() {
    if (!activePerson || !composeBody.trim()) return;
    setSending(true);
    setErr("");
    try {
      await api.sendMessage({
        body: composeBody.trim(),
        to_id: activePerson.id,
        to_role: activePerson.role,
        to_name: activePerson.name,
      });
      setComposeBody("");
      await loadLists();
      await loadThread(activePerson, { quiet: true });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Send failed");
    } finally {
      setSending(false);
    }
  }

  const showThread = Boolean(activeKey && activePerson);

  return (
    <div className="mx-auto flex h-[calc(100vh-5.5rem)] max-w-5xl flex-col px-4 py-4 sm:px-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold tracking-tight">
            Messages
          </h1>
          <p className="text-sm text-muted">
            Techs and advisors · {unreadTotal > 0 ? `${unreadTotal} unread` : "All caught up"}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy}
            onClick={() => void refreshAll()}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", busy && "animate-spin")} />
            Refresh
          </Button>
          <Button type="button" size="sm" onClick={() => setPickerOpen(true)}>
            <MessageSquarePlus className="h-3.5 w-3.5" />
            New
          </Button>
        </div>
      </div>

      {err ? <p className="mb-2 text-sm text-danger">{err}</p> : null}

      <div className="flex min-h-0 flex-1 overflow-hidden rounded-2xl border border-border bg-surface shadow-sm">
        {/* Conversation list */}
        <aside
          className={cn(
            "flex w-full flex-col border-border md:w-[18.5rem] md:border-r lg:w-80",
            showThread && "hidden md:flex",
          )}
        >
          <div className="border-b border-border p-3">
            <label className="relative block">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
              <input
                className="w-full rounded-lg border border-border bg-bg py-2 pl-8 pr-3 text-sm outline-none focus:border-accent"
                placeholder="Search conversations"
                value={listFilter}
                onChange={(e) => setListFilter(e.target.value)}
              />
            </label>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {busy && !conversations.length ? (
              <p className="p-4 text-sm text-muted">Loading…</p>
            ) : !filteredConversations.length ? (
              <div className="space-y-2 p-4 text-sm text-muted">
                <p>No conversations yet.</p>
                <Button type="button" size="sm" onClick={() => setPickerOpen(true)}>
                  Message someone
                </Button>
              </div>
            ) : (
              <ul>
                {filteredConversations.map((c) => {
                  const active = c.key === activeKey;
                  return (
                    <li key={c.key}>
                      <button
                        type="button"
                        onClick={() => void openConversation(c.person)}
                        className={cn(
                          "flex w-full items-start gap-3 border-b border-border/70 px-3 py-3 text-left transition-colors",
                          active ? "bg-accent/10" : "hover:bg-border/30",
                        )}
                      >
                        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent/15 text-xs font-semibold text-accent">
                          {initials(c.person.name)}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex items-baseline justify-between gap-2">
                            <span className="truncate text-sm font-semibold">{c.person.name}</span>
                            <span className="shrink-0 text-[10px] text-muted">
                              {formatShopTime(c.last.at)}
                            </span>
                          </span>
                          <span className="mt-0.5 block text-[10px] font-medium uppercase tracking-wide text-muted">
                            {roleLabel(c.person.role)}
                          </span>
                          <span className="mt-0.5 flex items-center gap-2">
                            <span className="truncate text-xs text-muted">{c.preview}</span>
                            {c.unread > 0 ? (
                              <span className="ml-auto shrink-0 rounded-full bg-accent px-1.5 py-0.5 text-[10px] font-semibold text-accent-fg">
                                {c.unread}
                              </span>
                            ) : null}
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </aside>

        {/* Thread */}
        <section
          className={cn(
            "flex min-w-0 flex-1 flex-col",
            !showThread && "hidden md:flex",
          )}
        >
          {!showThread || !activePerson ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center text-muted">
              <MessageSquarePlus className="h-10 w-10 opacity-40" />
              <p className="text-sm">Pick a conversation or start a new one.</p>
              <Button type="button" onClick={() => setPickerOpen(true)}>
                New message
              </Button>
            </div>
          ) : (
            <>
              <header className="flex items-center gap-3 border-b border-border px-3 py-3">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="md:hidden"
                  onClick={() => setActiveKey(null)}
                >
                  <ArrowLeft className="h-4 w-4" />
                </Button>
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-accent/15 text-xs font-semibold text-accent">
                  {initials(activePerson.name)}
                </span>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold">{activePerson.name}</div>
                  <div className="text-[10px] font-medium uppercase tracking-wide text-muted">
                    {roleLabel(activePerson.role)}
                  </div>
                </div>
              </header>

              <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-4 sm:px-5">
                {thread.length === 0 ? (
                  <p className="text-center text-sm text-muted">Say hello — no messages yet.</p>
                ) : (
                  thread.map((m) => {
                    const mine = Boolean(meId && m.from_id === meId);
                    return (
                      <div
                        key={m.id}
                        className={cn("flex", mine ? "justify-end" : "justify-start")}
                      >
                        <div
                          className={cn(
                            "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm shadow-sm sm:max-w-[70%]",
                            mine
                              ? "rounded-br-md bg-accent text-accent-fg"
                              : "rounded-bl-md bg-bg text-fg ring-1 ring-border",
                          )}
                        >
                          <p className="whitespace-pre-wrap break-words">{m.body}</p>
                          <div
                            className={cn(
                              "mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px]",
                              mine ? "text-accent-fg/75" : "text-muted",
                            )}
                          >
                            <span>{formatShopTime(m.at)}</span>
                            {mine ? (
                              <span>
                                {m.read_at
                                  ? `Read ${formatShopTime(m.read_at)}`
                                  : m.delivered_at
                                    ? "Delivered"
                                    : "Sent"}
                              </span>
                            ) : null}
                            {(m.ro_id || m.work_item_id) && (
                              <span>
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
                                {m.work_item_id ? ` · ${m.work_item_id}` : ""}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
                <div ref={bottomRef} />
              </div>

              <form
                className="border-t border-border p-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  void send();
                }}
              >
                <div className="flex items-end gap-2 rounded-xl border border-border bg-bg p-2">
                  <textarea
                    ref={textareaRef}
                    rows={1}
                    className="max-h-32 min-h-[2.5rem] flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none"
                    placeholder={`Message ${activePerson.name}…`}
                    value={composeBody}
                    maxLength={4000}
                    onChange={(e) => setComposeBody(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        void send();
                      }
                    }}
                  />
                  <Button
                    type="submit"
                    size="sm"
                    disabled={sending || !composeBody.trim()}
                    className="shrink-0"
                  >
                    <Send className="h-3.5 w-3.5" />
                    Send
                  </Button>
                </div>
                <p className="mt-1.5 text-[10px] text-muted">Enter to send · Shift+Enter for new line</p>
              </form>
            </>
          )}
        </section>
      </div>

      {/* New conversation picker */}
      {pickerOpen ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
          <button
            type="button"
            className="absolute inset-0 cursor-default"
            aria-label="Close"
            onClick={() => setPickerOpen(false)}
          />
          <div className="relative z-10 flex max-h-[80vh] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-lg">
            <div className="border-b border-border p-4">
              <h2 className="font-[family-name:var(--font-display)] text-lg font-semibold">
                New message
              </h2>
              <p className="mt-0.5 text-xs text-muted">Any technician or advisor on the roster</p>
              <label className="relative mt-3 block">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
                <input
                  autoFocus
                  className="w-full rounded-lg border border-border bg-bg py-2 pl-8 pr-3 text-sm outline-none focus:border-accent"
                  placeholder="Search staff…"
                  value={pickerFilter}
                  onChange={(e) => setPickerFilter(e.target.value)}
                />
              </label>
            </div>
            <ul className="min-h-0 flex-1 overflow-y-auto">
              {!filteredPeople.length ? (
                <li className="p-4 text-sm text-muted">No matching staff.</li>
              ) : (
                filteredPeople.map((p) => (
                  <li key={`${p.role}:${p.id}`}>
                    <button
                      type="button"
                      className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-border/40"
                      onClick={() => void openConversation(p)}
                    >
                      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-accent/15 text-xs font-semibold text-accent">
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
              <Button
                type="button"
                variant="secondary"
                className="w-full"
                onClick={() => setPickerOpen(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
