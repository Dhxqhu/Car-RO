import { useEffect, useState } from "react";
import { api, type Person, type ShopMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { formatShopTime } from "@/lib/utils";

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
  const [toId, setToId] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const fromRole = role === "advisor" ? "advisor" : "technician";

  async function load() {
    try {
      const [p, m] = await Promise.all([api.people(), api.messages(id)]);
      setPeople((p.people || []).filter((x) => x.id !== id));
      setInbox(m.messages || []);
      if (!toId && p.people?.find((x) => x.id !== id)) {
        setToId(p.people.find((x) => x.id !== id)?.id || "");
      }
      for (const msg of m.messages || []) {
        if (!msg.read_at) {
          void api.markRead(msg.id, id).catch(() => undefined);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load messages");
    }
  }

  useEffect(() => {
    void load();
  }, [id]);

  async function send() {
    const to = people.find((p) => p.id === toId);
    if (!to || !body.trim()) return;
    setBusy(true);
    setError("");
    try {
      await api.sendMessage({
        body: body.trim(),
        from_id: id,
        from_name: name,
        from_role: fromRole,
        to_id: to.id,
        to_role: to.role === "advisor" ? "advisor" : "technician",
        to_name: to.name,
      });
      setBody("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Send failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2 rounded-xl border border-border bg-surface p-3">
        <select
          className="h-11 w-full rounded-xl border border-border bg-bg px-3 text-base"
          value={toId}
          onChange={(e) => setToId(e.target.value)}
        >
          {people.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.role === "advisor" ? "advisor" : "tech"})
            </option>
          ))}
        </select>
        <Textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Shop note…"
          rows={3}
        />
        <Button disabled={busy || !body.trim() || !toId} onClick={() => void send()}>
          Send
        </Button>
      </div>
      {error ? <p className="text-sm text-danger">{error}</p> : null}
      <ul className="space-y-2">
        {inbox.map((m) => (
          <li key={m.id} className="rounded-xl border border-border bg-surface px-4 py-3">
            <p className="text-xs text-muted">
              {m.from_name} → {m.to_name}
              {m.at ? ` · ${formatShopTime(m.at)}` : ""}
            </p>
            <p className="mt-1 text-sm">{m.body}</p>
          </li>
        ))}
      </ul>
      {inbox.length === 0 ? <p className="text-sm text-muted">No messages.</p> : null}
    </div>
  );
}
