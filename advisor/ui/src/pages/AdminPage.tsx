import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Advisor, type Technician } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function digits4(value: string): string {
  return value.replace(/\D/g, "").slice(0, 4);
}

export function AdminPage() {
  const [active, setActive] = useState(false);
  const [hasPin, setHasPin] = useState(true);
  const [pin, setPin] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const [techs, setTechs] = useState<Technician[]>([]);
  const [advisors, setAdvisors] = useState<Advisor[]>([]);

  const [newTechName, setNewTechName] = useState("");
  const [newTechPin, setNewTechPin] = useState("");
  const [resetTechId, setResetTechId] = useState("");
  const [resetTechPin, setResetTechPin] = useState("");
  const [renameTechId, setRenameTechId] = useState("");
  const [renameTechName, setRenameTechName] = useState("");

  const [newAdvName, setNewAdvName] = useState("");
  const [newAdvPin, setNewAdvPin] = useState("");
  const [resetAdvId, setResetAdvId] = useState("");
  const [resetAdvPin, setResetAdvPin] = useState("");
  const [renameAdvId, setRenameAdvId] = useState("");
  const [renameAdvName, setRenameAdvName] = useState("");
  const [removeAdvId, setRemoveAdvId] = useState("");

  const [oldAdminPin, setOldAdminPin] = useState("");
  const [newAdminPin, setNewAdminPin] = useState("");
  const [confirmAdminPin, setConfirmAdminPin] = useState("");

  const refreshSession = useCallback(async () => {
    const s = await api.adminSession();
    setActive(s.active);
    setHasPin(s.has_admin_pin);
  }, []);

  const refreshStaff = useCallback(async () => {
    const [r, a] = await Promise.all([api.listTechs(), api.listAdvisors()]);
    const list = r.technicians || [];
    setTechs(list);
    setResetTechId((cur) => cur || list[0]?.id || "");
    setRenameTechId((cur) => cur || list[0]?.id || "");
    const adv = a.advisors || [];
    setAdvisors(adv);
    setResetAdvId((cur) => cur || adv[0]?.id || "");
    setRenameAdvId((cur) => cur || adv[0]?.id || "");
    setRemoveAdvId((cur) => cur || adv[0]?.id || "");
  }, []);

  useEffect(() => {
    void refreshSession().catch((e: Error) => setErr(e.message));
    void refreshStaff().catch(() => undefined);
  }, [refreshSession, refreshStaff]);

  async function unlock() {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      await api.adminUnlock(pin);
      setPin("");
      setMsg("Admin unlocked — staff tools available for 2 hours");
      await refreshSession();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Unlock failed");
    } finally {
      setBusy(false);
    }
  }

  async function lock() {
    setBusy(true);
    try {
      await api.adminLock();
      setMsg("Admin locked");
      await refreshSession();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Lock failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight">
          Admin
        </h1>
        <p className="mt-1 text-sm text-muted">
          Unlock with the <span className="text-fg">shop admin PIN</span> to manage technicians,
          advisors (including login PINs), and the admin PIN itself. Separate from advisor desk
          login. Worked-time edits stay on each RO (Edit time).
        </p>
      </div>

      <section className="space-y-3 rounded-2xl border border-border bg-surface p-5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
          Admin session
        </h2>
        {!hasPin ? (
          <p className="text-sm text-danger">
            No shop admin PIN set yet. Create the first technician or advisor with an admin PIN
            (People / setup), or use the CLI.
          </p>
        ) : active ? (
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-sm text-accent">Unlocked</p>
            <Button variant="secondary" disabled={busy} onClick={() => void lock()}>
              Lock admin
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="admin-pin">Shop admin PIN</Label>
              <Input
                id="admin-pin"
                type="password"
                inputMode="numeric"
                maxLength={4}
                className="w-28"
                value={pin}
                onChange={(e) => setPin(digits4(e.target.value))}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void unlock();
                }}
              />
            </div>
            <Button disabled={busy || pin.length !== 4} onClick={() => void unlock()}>
              Unlock
            </Button>
          </div>
        )}
      </section>

      {msg ? <p className="text-sm text-accent">{msg}</p> : null}
      {err ? <p className="text-sm text-danger">{err}</p> : null}

      {!active ? (
        <p className="text-sm text-muted">
          Unlock to manage staff and change the shop admin PIN below.
        </p>
      ) : (
        <>
          <section className="space-y-4 rounded-2xl border border-border bg-surface p-5">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Shop admin PIN
            </h2>
            <p className="text-xs text-muted">
              This unlocks Admin on both the advisor desk and tech app. It is not an advisor or
              technician login PIN.
            </p>
            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1.5">
                <Label>Current</Label>
                <Input
                  type="password"
                  inputMode="numeric"
                  maxLength={4}
                  className="w-28"
                  value={oldAdminPin}
                  onChange={(e) => setOldAdminPin(digits4(e.target.value))}
                />
              </div>
              <div className="space-y-1.5">
                <Label>New</Label>
                <Input
                  type="password"
                  inputMode="numeric"
                  maxLength={4}
                  className="w-28"
                  value={newAdminPin}
                  onChange={(e) => setNewAdminPin(digits4(e.target.value))}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Confirm new</Label>
                <Input
                  type="password"
                  inputMode="numeric"
                  maxLength={4}
                  className="w-28"
                  value={confirmAdminPin}
                  onChange={(e) => setConfirmAdminPin(digits4(e.target.value))}
                />
              </div>
              <Button
                variant="secondary"
                disabled={
                  busy ||
                  oldAdminPin.length !== 4 ||
                  newAdminPin.length !== 4 ||
                  confirmAdminPin.length !== 4
                }
                onClick={() =>
                  void (async () => {
                    setBusy(true);
                    setErr("");
                    setMsg("");
                    try {
                      if (newAdminPin !== confirmAdminPin) {
                        throw new Error("New PIN and confirm do not match");
                      }
                      await api.adminChangePin(oldAdminPin, newAdminPin);
                      setOldAdminPin("");
                      setNewAdminPin("");
                      setConfirmAdminPin("");
                      setMsg("Shop admin PIN updated");
                      await refreshSession();
                    } catch (e) {
                      setErr(e instanceof Error ? e.message : "Change failed");
                    } finally {
                      setBusy(false);
                    }
                  })()
                }
              >
                Update admin PIN
              </Button>
            </div>
          </section>

          <section className="space-y-4 rounded-2xl border border-border bg-surface p-5">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Advisors
            </h2>
            <p className="text-xs text-muted">
              Advisor login PINs open the desk app. Keep them unique across advisors and techs.
            </p>
            <ul className="divide-y divide-border rounded-xl border border-border">
              {advisors.map((a) => (
                <li key={a.id} className="flex justify-between px-4 py-2 text-sm">
                  <span className="font-medium">{a.name}</span>
                  <span className="text-muted">{a.id}</span>
                </li>
              ))}
              {!advisors.length ? (
                <li className="px-4 py-2 text-sm text-muted">No advisors.</li>
              ) : null}
            </ul>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <p className="text-sm font-medium">Add advisor</p>
                <Input
                  placeholder="Name"
                  value={newAdvName}
                  onChange={(e) => setNewAdvName(e.target.value)}
                />
                <Input
                  type="password"
                  inputMode="numeric"
                  maxLength={4}
                  placeholder="Login PIN"
                  value={newAdvPin}
                  onChange={(e) => setNewAdvPin(digits4(e.target.value))}
                />
                <Button
                  disabled={busy || !newAdvName.trim() || newAdvPin.length !== 4}
                  onClick={() =>
                    void (async () => {
                      setBusy(true);
                      setErr("");
                      try {
                        await api.addAdvisor(newAdvName.trim(), newAdvPin);
                        setNewAdvName("");
                        setNewAdvPin("");
                        setMsg("Advisor added");
                        await refreshStaff();
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Add failed");
                      } finally {
                        setBusy(false);
                      }
                    })()
                  }
                >
                  Add
                </Button>
              </div>
              <div className="space-y-2">
                <p className="text-sm font-medium">Reset advisor login PIN</p>
                <select
                  className="flex h-10 w-full rounded-lg border border-border bg-bg px-3 text-sm"
                  value={resetAdvId}
                  onChange={(e) => setResetAdvId(e.target.value)}
                >
                  {advisors.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
                <Input
                  type="password"
                  inputMode="numeric"
                  maxLength={4}
                  placeholder="New login PIN"
                  value={resetAdvPin}
                  onChange={(e) => setResetAdvPin(digits4(e.target.value))}
                />
                <Button
                  variant="secondary"
                  disabled={busy || !resetAdvId || resetAdvPin.length !== 4}
                  onClick={() =>
                    void (async () => {
                      setBusy(true);
                      setErr("");
                      try {
                        await api.adminResetAdvisorPin(resetAdvId, resetAdvPin);
                        setResetAdvPin("");
                        setMsg("Advisor login PIN reset");
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Reset failed");
                      } finally {
                        setBusy(false);
                      }
                    })()
                  }
                >
                  Reset PIN
                </Button>
              </div>
              <div className="space-y-2">
                <p className="text-sm font-medium">Rename advisor</p>
                <select
                  className="flex h-10 w-full rounded-lg border border-border bg-bg px-3 text-sm"
                  value={renameAdvId}
                  onChange={(e) => setRenameAdvId(e.target.value)}
                >
                  {advisors.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
                <Input
                  placeholder="New name"
                  value={renameAdvName}
                  onChange={(e) => setRenameAdvName(e.target.value)}
                />
                <Button
                  variant="secondary"
                  disabled={busy || !renameAdvId || !renameAdvName.trim()}
                  onClick={() =>
                    void (async () => {
                      setBusy(true);
                      setErr("");
                      try {
                        await api.adminRenameAdvisor(renameAdvId, renameAdvName.trim());
                        setRenameAdvName("");
                        setMsg("Advisor renamed");
                        await refreshStaff();
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Rename failed");
                      } finally {
                        setBusy(false);
                      }
                    })()
                  }
                >
                  Rename
                </Button>
              </div>
              <div className="space-y-2">
                <p className="text-sm font-medium">Remove advisor</p>
                <select
                  className="flex h-10 w-full rounded-lg border border-border bg-bg px-3 text-sm"
                  value={removeAdvId}
                  onChange={(e) => setRemoveAdvId(e.target.value)}
                >
                  {advisors.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
                <Button
                  variant="danger"
                  disabled={busy || !removeAdvId || advisors.length < 2}
                  onClick={() => {
                    if (!confirm(`Remove advisor ${removeAdvId}?`)) return;
                    void (async () => {
                      setBusy(true);
                      setErr("");
                      try {
                        await api.adminRemoveAdvisor(removeAdvId);
                        setMsg("Advisor removed");
                        await refreshStaff();
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Remove failed");
                      } finally {
                        setBusy(false);
                      }
                    })();
                  }}
                >
                  Remove
                </Button>
                <p className="text-xs text-muted">Cannot remove the last advisor.</p>
              </div>
            </div>
          </section>

          <section className="space-y-4 rounded-2xl border border-border bg-surface p-5">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Technicians
            </h2>
            <ul className="divide-y divide-border rounded-xl border border-border">
              {techs.map((t) => (
                <li key={t.id} className="flex justify-between px-4 py-2 text-sm">
                  <span className="font-medium">{t.name}</span>
                  <span className="text-muted">{t.id}</span>
                </li>
              ))}
            </ul>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <p className="text-sm font-medium">Add technician</p>
                <Input
                  placeholder="Name"
                  value={newTechName}
                  onChange={(e) => setNewTechName(e.target.value)}
                />
                <Input
                  type="password"
                  inputMode="numeric"
                  maxLength={4}
                  placeholder="Login PIN"
                  value={newTechPin}
                  onChange={(e) => setNewTechPin(digits4(e.target.value))}
                />
                <Button
                  disabled={busy || !newTechName.trim() || newTechPin.length !== 4}
                  onClick={() =>
                    void (async () => {
                      setBusy(true);
                      setErr("");
                      try {
                        await api.addTech(newTechName.trim(), newTechPin);
                        setNewTechName("");
                        setNewTechPin("");
                        setMsg("Technician added");
                        await refreshStaff();
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Add failed");
                      } finally {
                        setBusy(false);
                      }
                    })()
                  }
                >
                  Add
                </Button>
              </div>
              <div className="space-y-2">
                <p className="text-sm font-medium">Reset tech login PIN</p>
                <select
                  className="flex h-10 w-full rounded-lg border border-border bg-bg px-3 text-sm"
                  value={resetTechId}
                  onChange={(e) => setResetTechId(e.target.value)}
                >
                  {techs.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
                <Input
                  type="password"
                  inputMode="numeric"
                  maxLength={4}
                  placeholder="New login PIN"
                  value={resetTechPin}
                  onChange={(e) => setResetTechPin(digits4(e.target.value))}
                />
                <Button
                  variant="secondary"
                  disabled={busy || !resetTechId || resetTechPin.length !== 4}
                  onClick={() =>
                    void (async () => {
                      setBusy(true);
                      setErr("");
                      try {
                        await api.adminResetTechPin(resetTechId, resetTechPin);
                        setResetTechPin("");
                        setMsg("Tech login PIN reset");
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Reset failed");
                      } finally {
                        setBusy(false);
                      }
                    })()
                  }
                >
                  Reset PIN
                </Button>
              </div>
              <div className="space-y-2">
                <p className="text-sm font-medium">Rename technician</p>
                <select
                  className="flex h-10 w-full rounded-lg border border-border bg-bg px-3 text-sm"
                  value={renameTechId}
                  onChange={(e) => setRenameTechId(e.target.value)}
                >
                  {techs.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
                <Input
                  placeholder="New name"
                  value={renameTechName}
                  onChange={(e) => setRenameTechName(e.target.value)}
                />
                <Button
                  variant="secondary"
                  disabled={busy || !renameTechId || !renameTechName.trim()}
                  onClick={() =>
                    void (async () => {
                      setBusy(true);
                      setErr("");
                      try {
                        await api.adminRenameTech(renameTechId, renameTechName.trim());
                        setRenameTechName("");
                        setMsg("Renamed");
                        await refreshStaff();
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Rename failed");
                      } finally {
                        setBusy(false);
                      }
                    })()
                  }
                >
                  Rename
                </Button>
              </div>
              <div className="space-y-2">
                <p className="text-sm font-medium">Remove technician</p>
                <select
                  className="flex h-10 w-full rounded-lg border border-border bg-bg px-3 text-sm"
                  value={resetTechId}
                  onChange={(e) => setResetTechId(e.target.value)}
                >
                  {techs.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
                <Button
                  variant="danger"
                  disabled={busy || !resetTechId || techs.length < 2}
                  onClick={() => {
                    if (!confirm(`Remove ${resetTechId}?`)) return;
                    void (async () => {
                      setBusy(true);
                      setErr("");
                      try {
                        await api.adminRemoveTech(resetTechId);
                        setMsg("Removed");
                        await refreshStaff();
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Remove failed");
                      } finally {
                        setBusy(false);
                      }
                    })();
                  }}
                >
                  Remove
                </Button>
              </div>
            </div>
            <p className="text-xs text-muted">
              Quick adds also on{" "}
              <Link to="/people" className="text-accent hover:underline">
                People
              </Link>
              .
            </p>
          </section>
        </>
      )}
    </div>
  );
}
