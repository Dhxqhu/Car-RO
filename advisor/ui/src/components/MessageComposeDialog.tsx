import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { api, type MessagePerson } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Props = {
  open: boolean;
  onClose: () => void;
  onSent?: () => void;
  /** Prefill when composing from a bay / RO context */
  defaultRoId?: string;
  defaultWorkItemId?: string;
  lockRefs?: boolean;
  /** Optional preselected recipient */
  defaultTo?: MessagePerson | null;
};

function roleLabel(role: string): string {
  return role === "advisor" ? "Advisor" : "Tech";
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ""}${parts[parts.length - 1][0] || ""}`.toUpperCase();
}

export function MessageComposeDialog({
  open,
  onClose,
  onSent,
  defaultRoId = "",
  defaultWorkItemId = "",
  lockRefs = false,
  defaultTo = null,
}: Props) {
  const [people, setPeople] = useState<MessagePerson[]>([]);
  const [toKey, setToKey] = useState("");
  const [filter, setFilter] = useState("");
  const [body, setBody] = useState("");
  const [roId, setRoId] = useState(defaultRoId);
  const [workItemId, setWorkItemId] = useState(defaultWorkItemId);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!open) return;
    setBody("");
    setErr("");
    setFilter("");
    setRoId(defaultRoId);
    setWorkItemId(defaultWorkItemId);
    setToKey(defaultTo ? `${defaultTo.role}:${defaultTo.id}` : "");
    void (async () => {
      try {
        const r = await api.listMessagePeople();
        setPeople(r.people || []);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Could not load people");
        setPeople([]);
      }
    })();
  }, [open, defaultRoId, defaultWorkItemId, defaultTo]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return people;
    return people.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        roleLabel(p.role).toLowerCase().includes(q),
    );
  }, [people, filter]);

  if (!open) return null;

  async function send() {
    const person = people.find((p) => `${p.role}:${p.id}` === toKey);
    if (!person) {
      setErr("Pick a person");
      return;
    }
    if (!body.trim()) {
      setErr("Write a message");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      await api.sendMessage({
        body: body.trim(),
        to_id: person.id,
        to_role: person.role,
        to_name: person.name,
        ro_id: roId.trim() || undefined,
        work_item_id: workItemId.trim() || undefined,
      });
      onSent?.();
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Send failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="Close" onClick={onClose} />
      <div className="relative z-10 flex max-h-[85vh] w-full max-w-md flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-lg">
        <div className="border-b border-border p-4">
          <h2 className="font-[family-name:var(--font-display)] text-lg font-semibold">Send message</h2>
          <p className="mt-1 text-xs text-muted">Any tech or advisor · optional RO / work item tag</p>
        </div>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
          <div>
            <Label htmlFor="msg-filter">To</Label>
            <div className="relative mt-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
              <input
                id="msg-filter"
                className="w-full rounded-lg border border-border bg-bg py-2 pl-8 pr-3 text-sm outline-none focus:border-accent"
                placeholder="Search staff…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
            </div>
            <ul className="mt-2 max-h-40 overflow-y-auto rounded-lg border border-border">
              {!filtered.length ? (
                <li className="px-3 py-2 text-sm text-muted">No matching staff</li>
              ) : (
                filtered.map((p) => {
                  const key = `${p.role}:${p.id}`;
                  const selected = key === toKey;
                  return (
                    <li key={key}>
                      <button
                        type="button"
                        className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm ${
                          selected ? "bg-accent/15 text-accent" : "hover:bg-border/40"
                        }`}
                        onClick={() => setToKey(key)}
                      >
                        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent/15 text-[10px] font-semibold text-accent">
                          {initials(p.name)}
                        </span>
                        <span className="min-w-0 flex-1 truncate font-medium">{p.name}</span>
                        <span className="text-[10px] uppercase tracking-wide text-muted">
                          {roleLabel(p.role)}
                        </span>
                      </button>
                    </li>
                  );
                })
              )}
            </ul>
          </div>
          <div>
            <Label htmlFor="msg-body">Message</Label>
            <textarea
              id="msg-body"
              className="mt-1 min-h-[100px] w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              maxLength={4000}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label htmlFor="msg-ro">RO id</Label>
              <Input
                id="msg-ro"
                value={roId}
                onChange={(e) => setRoId(e.target.value)}
                disabled={lockRefs && !!defaultRoId}
                placeholder="optional"
              />
            </div>
            <div>
              <Label htmlFor="msg-wi">Work item</Label>
              <Input
                id="msg-wi"
                value={workItemId}
                onChange={(e) => setWorkItemId(e.target.value)}
                disabled={lockRefs && !!defaultWorkItemId}
                placeholder="optional"
              />
            </div>
          </div>
          {err ? <p className="text-sm text-danger">{err}</p> : null}
        </div>
        <div className="flex justify-end gap-2 border-t border-border p-3">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="button" onClick={() => void send()} disabled={busy}>
            {busy ? "Sending…" : "Send"}
          </Button>
        </div>
      </div>
    </div>
  );
}
