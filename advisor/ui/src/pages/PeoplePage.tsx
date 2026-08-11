import { useCallback, useEffect, useState } from "react";
import { api, type Advisor, type Technician } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function PeoplePage() {
  const [advisors, setAdvisors] = useState<Advisor[]>([]);
  const [techs, setTechs] = useState<Technician[]>([]);
  const [advName, setAdvName] = useState("");
  const [advPin, setAdvPin] = useState("");
  const [techName, setTechName] = useState("");
  const [techPin, setTechPin] = useState("");
  const [adminPin, setAdminPin] = useState("");
  const [removeAdminPin, setRemoveAdminPin] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [a, t] = await Promise.all([api.listAdvisors(), api.listTechs()]);
    setAdvisors(a.advisors || []);
    setTechs(t.technicians || []);
  }, []);

  useEffect(() => {
    refresh().catch((e: Error) => setErr(e.message));
  }, [refresh]);

  async function addAdvisor() {
    setErr("");
    setMsg("");
    try {
      const r = await api.addAdvisor(advName, advPin);
      setMsg(`Added advisor ${r.name}`);
      setAdvName("");
      setAdvPin("");
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Add advisor failed");
    }
  }

  async function addTech() {
    setErr("");
    setMsg("");
    try {
      const r = await api.addTech(techName, techPin, adminPin || undefined);
      setMsg(`Added technician ${r.name}`);
      setTechName("");
      setTechPin("");
      setAdminPin("");
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Add tech failed");
    }
  }

  async function toggleWorkingPrivilege(a: Advisor, enabled: boolean) {
    if (removeAdminPin.length !== 4) {
      setErr("Enter the shop admin PIN to change working privilege");
      return;
    }
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const r = await api.setAdvisorWorkingPrivilege(a.id, enabled, removeAdminPin);
      setMsg(
        enabled
          ? `${r.name}: working privilege on (bay work + job timers; no tech day clock)`
          : `${r.name}: working privilege off`,
      );
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not update working privilege");
    } finally {
      setBusy(false);
    }
  }

  async function removeAdvisor(a: Advisor) {
    if (advisors.length < 2) {
      setErr("Cannot remove the last advisor");
      return;
    }
    if (removeAdminPin.length !== 4) {
      setErr("Enter the shop admin PIN to remove staff");
      return;
    }
    if (!window.confirm(`Remove advisor ${a.name}?`)) return;
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      await api.adminRemoveAdvisor(a.id, removeAdminPin);
      setMsg(`Removed advisor ${a.name}`);
      setRemoveAdminPin("");
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Remove advisor failed");
    } finally {
      setBusy(false);
    }
  }

  async function removeTech(t: Technician) {
    if (techs.length < 2) {
      setErr("Cannot remove the last technician");
      return;
    }
    if (removeAdminPin.length !== 4) {
      setErr("Enter the shop admin PIN to remove staff");
      return;
    }
    if (!window.confirm(`Remove technician ${t.name}?`)) return;
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      await api.adminRemoveTech(t.id, removeAdminPin);
      setMsg(`Removed technician ${t.name}`);
      setRemoveAdminPin("");
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Remove tech failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold">Staff</h1>
        <p className="mt-1 text-sm text-muted">
          Add advisors here only. You can also add technicians from the desk. Rosters sync through the
          shop server. Removals require the shop admin PIN.
        </p>
      </div>

      {msg ? <p className="text-sm text-accent">{msg}</p> : null}
      {err ? <p className="text-sm text-danger">{err}</p> : null}

      <section className="space-y-3 rounded-2xl border border-border bg-surface p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">
          Staff changes
        </h2>
        <p className="text-xs text-muted">
          Enter the admin PIN once, then use Remove or Working privilege on a person below. Cannot
          remove the last advisor or last technician.
        </p>
        <div className="max-w-xs">
          <Label>Admin PIN (for remove / privilege)</Label>
          <Input
            className="mt-1"
            type="password"
            inputMode="numeric"
            maxLength={4}
            value={removeAdminPin}
            onChange={(e) => setRemoveAdminPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
            placeholder="••••"
          />
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Advisors</h2>
        <p className="text-xs text-muted">
          Working privilege: may assign and perform bay work; job time is tracked; not a tech day
          clock.
        </p>
        <ul className="divide-y divide-border rounded-2xl border border-border bg-surface">
          {advisors.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 text-sm">
              <div>
                <span className="font-medium">{a.name}</span>
                <span className="ml-2 text-muted">{a.id}</span>
                {a.working_privilege ? (
                  <span className="ml-2 rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">
                    Working privilege
                  </span>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-2 text-xs text-muted">
                  <input
                    type="checkbox"
                    checked={!!a.working_privilege}
                    disabled={busy}
                    onChange={(e) => void toggleWorkingPrivilege(a, e.target.checked)}
                  />
                  Working privilege
                </label>
                <Button
                  type="button"
                  size="sm"
                  variant="danger"
                  disabled={busy || advisors.length < 2}
                  onClick={() => void removeAdvisor(a)}
                >
                  Remove
                </Button>
              </div>
            </li>
          ))}
          {!advisors.length ? (
            <li className="px-5 py-3 text-sm text-muted">No advisors yet.</li>
          ) : null}
        </ul>
        <div className="grid gap-3 rounded-2xl border border-border bg-surface p-4 sm:grid-cols-3">
          <div>
            <Label>Name</Label>
            <Input className="mt-1" value={advName} onChange={(e) => setAdvName(e.target.value)} />
          </div>
          <div>
            <Label>PIN</Label>
            <Input
              className="mt-1"
              type="password"
              inputMode="numeric"
              maxLength={4}
              value={advPin}
              onChange={(e) => setAdvPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
            />
          </div>
          <div className="flex items-end">
            <Button type="button" onClick={() => void addAdvisor()}>
              Add advisor
            </Button>
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Technicians</h2>
        <ul className="divide-y divide-border rounded-2xl border border-border bg-surface">
          {techs.map((t) => (
            <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 text-sm">
              <div>
                <span className="font-medium">{t.name}</span>
                <span className="ml-2 text-muted">{t.id}</span>
              </div>
              <Button
                type="button"
                size="sm"
                variant="danger"
                disabled={busy || techs.length < 2}
                onClick={() => void removeTech(t)}
              >
                Remove
              </Button>
            </li>
          ))}
          {!techs.length ? (
            <li className="px-5 py-3 text-sm text-muted">No technicians yet.</li>
          ) : null}
        </ul>
        <div className="grid gap-3 rounded-2xl border border-border bg-surface p-4 sm:grid-cols-4">
          <div>
            <Label>Name</Label>
            <Input className="mt-1" value={techName} onChange={(e) => setTechName(e.target.value)} />
          </div>
          <div>
            <Label>PIN</Label>
            <Input
              className="mt-1"
              type="password"
              inputMode="numeric"
              maxLength={4}
              value={techPin}
              onChange={(e) => setTechPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
            />
          </div>
          <div>
            <Label>Admin PIN</Label>
            <Input
              className="mt-1"
              type="password"
              inputMode="numeric"
              maxLength={4}
              value={adminPin}
              onChange={(e) => setAdminPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
            />
          </div>
          <div className="flex items-end">
            <Button type="button" onClick={() => void addTech()}>
              Add technician
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
