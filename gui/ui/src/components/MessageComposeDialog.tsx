import { useEffect, useState } from "react";
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
};

export function MessageComposeDialog({
  open,
  onClose,
  onSent,
  defaultRoId = "",
  defaultWorkItemId = "",
  lockRefs = false,
}: Props) {
  const [people, setPeople] = useState<MessagePerson[]>([]);
  const [toKey, setToKey] = useState("");
  const [body, setBody] = useState("");
  const [roId, setRoId] = useState(defaultRoId);
  const [workItemId, setWorkItemId] = useState(defaultWorkItemId);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!open) return;
    setBody("");
    setErr("");
    setRoId(defaultRoId);
    setWorkItemId(defaultWorkItemId);
    setToKey("");
    void (async () => {
      try {
        const r = await api.listMessagePeople();
        setPeople(r.people || []);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Could not load people");
        setPeople([]);
      }
    })();
  }, [open, defaultRoId, defaultWorkItemId]);

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
      <div className="relative z-10 w-full max-w-md rounded-xl border border-border bg-surface p-4 shadow-lg">
        <h2 className="font-[family-name:var(--font-display)] text-lg font-semibold">Send message</h2>
        <p className="mt-1 text-xs text-muted">Specific person only · optional RO / work item tag</p>
        <div className="mt-4 space-y-3">
          <div>
            <Label htmlFor="msg-to">To</Label>
            <select
              id="msg-to"
              className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm"
              value={toKey}
              onChange={(e) => setToKey(e.target.value)}
            >
              <option value="">Select person…</option>
              {people.map((p) => (
                <option key={`${p.role}:${p.id}`} value={`${p.role}:${p.id}`}>
                  {p.name} ({p.role === "advisor" ? "advisor" : "tech"})
                </option>
              ))}
            </select>
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
          {err ? <p className="text-sm text-red-600 dark:text-red-400">{err}</p> : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button type="button" onClick={() => void send()} disabled={busy}>
              {busy ? "Sending…" : "Send"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
