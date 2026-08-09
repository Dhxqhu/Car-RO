import { useEffect, useState } from "react";
import { api, type Technician } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function TechsPage() {
  const [techs, setTechs] = useState<Technician[]>([]);
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [adminPin, setAdminPin] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  async function refresh() {
    const r = await api.listTechs();
    setTechs(r.technicians);
  }

  useEffect(() => {
    refresh().catch((e: Error) => setErr(e.message));
  }, []);

  async function add() {
    setErr("");
    setMsg("");
    try {
      const t = await api.addTech(name, pin, adminPin);
      setMsg(`Added ${t.name} (${t.id})`);
      setName("");
      setPin("");
      setAdminPin("");
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Add failed");
    }
  }

  async function logout() {
    await api.logout();
    window.location.reload();
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold">
          Technicians
        </h1>
        <p className="mt-1 text-sm text-muted">
          Roster is shared via the shop server when configured. Admin PIN required to add.
        </p>
      </div>

      <ul className="divide-y divide-border rounded-2xl border border-border bg-surface">
        {techs.map((t) => (
          <li key={t.id} className="flex justify-between px-5 py-3 text-sm">
            <span className="font-medium">{t.name}</span>
            <span className="text-muted">{t.id}</span>
          </li>
        ))}
      </ul>

      <div className="space-y-3 rounded-2xl border border-border bg-surface p-6">
        <p className="text-sm font-semibold">Add technician</p>
        <div className="space-y-2">
          <Label>Name</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="space-y-2">
          <Label>New login PIN</Label>
          <Input
            type="password"
            inputMode="numeric"
            maxLength={4}
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
          />
        </div>
        <div className="space-y-2">
          <Label>Admin PIN</Label>
          <Input
            type="password"
            inputMode="numeric"
            maxLength={4}
            value={adminPin}
            onChange={(e) => setAdminPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
          />
        </div>
        {msg ? <p className="text-sm text-accent">{msg}</p> : null}
        {err ? <p className="text-sm text-danger">{err}</p> : null}
        <div className="flex gap-2">
          <Button onClick={() => void add()}>Add</Button>
          <Button variant="secondary" onClick={() => void logout()}>
            Log out
          </Button>
        </div>
      </div>
    </div>
  );
}
