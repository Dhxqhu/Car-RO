import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type RepairOrder, type Technician, type WorkItem } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatShopTime, formatStatus, formatWorkedMinutes } from "@/lib/utils";

export function AdminPage() {
  const [active, setActive] = useState(false);
  const [hasPin, setHasPin] = useState(true);
  const [pin, setPin] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const [techs, setTechs] = useState<Technician[]>([]);
  const [newName, setNewName] = useState("");
  const [newTechPin, setNewTechPin] = useState("");
  const [resetTechId, setResetTechId] = useState("");
  const [resetPin, setResetPin] = useState("");
  const [renameTechId, setRenameTechId] = useState("");
  const [renameName, setRenameName] = useState("");
  const [oldAdminPin, setOldAdminPin] = useState("");
  const [newAdminPin, setNewAdminPin] = useState("");

  const [roId, setRoId] = useState("");
  const [order, setOrder] = useState<RepairOrder | null>(null);
  const [editItemId, setEditItemId] = useState("");
  const [setMinutes, setSetMinutes] = useState("60");
  const [addMinutes, setAddMinutes] = useState("15");
  const [timeNote, setTimeNote] = useState("");

  const refreshSession = useCallback(async () => {
    const s = await api.adminSession();
    setActive(s.active);
    setHasPin(s.has_admin_pin);
  }, []);

  const refreshTechs = useCallback(async () => {
    const r = await api.listTechs();
    const list = r.technicians || [];
    setTechs(list);
    setResetTechId((cur) => cur || list[0]?.id || "");
    setRenameTechId((cur) => cur || list[0]?.id || "");
  }, []);

  useEffect(() => {
    void refreshSession().catch((e: Error) => setErr(e.message));
    void refreshTechs().catch(() => undefined);
  }, [refreshSession, refreshTechs]);

  async function unlock() {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      await api.adminUnlock(pin);
      setPin("");
      setMsg("Admin unlocked — corrections available for 2 hours");
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

  async function loadRo() {
    setBusy(true);
    setErr("");
    try {
      const o = await api.getRo(roId.trim());
      setOrder(o);
      const first = (o.work_items || [])[0];
      setEditItemId(first?.id || "");
      setMsg(`Loaded ${o.id}`);
    } catch (e) {
      setOrder(null);
      setErr(e instanceof Error ? e.message : "Load failed");
    } finally {
      setBusy(false);
    }
  }

  async function correctTime(action: "set" | "add" | "clear") {
    if (!order?.id || !editItemId) return;
    setBusy(true);
    setErr("");
    try {
      const next = await api.adminWorkItemTime(order.id, editItemId, {
        action,
        minutes:
          action === "set"
            ? Math.floor(Number(setMinutes))
            : action === "add"
              ? Math.floor(Number(addMinutes))
              : undefined,
        note: timeNote || undefined,
      });
      setOrder(next);
      setMsg(
        action === "clear"
          ? `Cleared time on ${editItemId}`
          : `Updated time on ${editItemId}`,
      );
      setTimeNote("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Time correction failed");
    } finally {
      setBusy(false);
    }
  }

  const selectedItem: WorkItem | undefined = (order?.work_items || []).find(
    (w) => w.id === editItemId,
  );

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight">
          Admin
        </h1>
        <p className="mt-1 text-sm text-muted">
          Unlock with the shop admin PIN to correct clocks, manage techs, and other shop controls.
          Separate from technician login.
        </p>
      </div>

      <section className="space-y-3 rounded-2xl border border-border bg-surface p-5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
          Admin session
        </h2>
        {!hasPin ? (
          <p className="text-sm text-danger">
            No admin PIN set. Finish technician setup in the CLI first (`carro` → techs).
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
              <Label htmlFor="admin-pin">Admin PIN</Label>
              <Input
                id="admin-pin"
                type="password"
                inputMode="numeric"
                maxLength={4}
                className="w-28"
                value={pin}
                onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
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
        <p className="text-sm text-muted">Unlock to use admin tools below.</p>
      ) : (
        <>
          <section className="space-y-4 rounded-2xl border border-border bg-surface p-5">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Correct worked time
            </h2>
            <p className="text-xs text-muted">
              Fix forgotten clocks or mistaken entries. Edits are logged as admin corrections
              (shop-only — not on customer PDF).
            </p>
            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="ro-id">RO id</Label>
                <Input
                  id="ro-id"
                  className="w-44"
                  value={roId}
                  onChange={(e) => setRoId(e.target.value)}
                  placeholder="RO-…"
                />
              </div>
              <Button variant="secondary" disabled={busy || !roId.trim()} onClick={() => void loadRo()}>
                Load
              </Button>
              {order ? (
                <Link to={`/ro/${order.id}`} className="text-sm text-accent hover:underline">
                  Open RO
                </Link>
              ) : null}
            </div>
            {order ? (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label>Work item</Label>
                  <select
                    className="flex h-10 w-full rounded-lg border border-border bg-bg px-3 text-sm"
                    value={editItemId}
                    onChange={(e) => setEditItemId(e.target.value)}
                  >
                    {(order.work_items || []).map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.id} · {formatStatus(w.status)} ·{" "}
                        {(w.concern || "").slice(0, 40) || "—"}
                      </option>
                    ))}
                  </select>
                </div>
                {selectedItem ? (
                  <p className="text-xs text-muted">
                    Current total {formatWorkedMinutes(selectedItem.worked_minutes || 0)}
                    {selectedItem.worked_first_at
                      ? ` · first ${formatShopTime(selectedItem.worked_first_at)}`
                      : ""}
                    {selectedItem.worked_last_at
                      ? ` · last ${formatShopTime(selectedItem.worked_last_at)}`
                      : ""}
                    {selectedItem.timer_started_at ? " · timer running (will stop on set)" : ""}
                  </p>
                ) : null}
                <div className="space-y-1.5">
                  <Label>Note (optional)</Label>
                  <Input
                    value={timeNote}
                    onChange={(e) => setTimeNote(e.target.value)}
                    placeholder="e.g. forgot to start timer before lunch"
                  />
                </div>
                <div className="flex flex-wrap items-end gap-2">
                  <div className="space-y-1.5">
                    <Label>Set total minutes</Label>
                    <Input
                      className="w-24"
                      inputMode="numeric"
                      value={setMinutes}
                      onChange={(e) => setSetMinutes(e.target.value)}
                    />
                  </div>
                  <Button
                    disabled={busy || !editItemId}
                    onClick={() => void correctTime("set")}
                  >
                    Set total
                  </Button>
                  <div className="space-y-1.5">
                    <Label>Add / subtract</Label>
                    <Input
                      className="w-24"
                      inputMode="numeric"
                      value={addMinutes}
                      onChange={(e) => setAddMinutes(e.target.value)}
                    />
                  </div>
                  <Button
                    variant="secondary"
                    disabled={busy || !editItemId}
                    onClick={() => void correctTime("add")}
                  >
                    Apply delta
                  </Button>
                  <Button
                    variant="danger"
                    disabled={busy || !editItemId}
                    onClick={() => {
                      if (confirm(`Clear all time on ${editItemId}?`)) void correctTime("clear");
                    }}
                  >
                    Clear time
                  </Button>
                </div>
              </div>
            ) : null}
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
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
                <Input
                  type="password"
                  inputMode="numeric"
                  maxLength={4}
                  placeholder="Login PIN"
                  value={newTechPin}
                  onChange={(e) =>
                    setNewTechPin(e.target.value.replace(/\D/g, "").slice(0, 4))
                  }
                />
                <Button
                  disabled={busy || !newName.trim() || newTechPin.length !== 4}
                  onClick={() =>
                    void (async () => {
                      setBusy(true);
                      setErr("");
                      try {
                        await api.addTech(newName.trim(), newTechPin);
                        setNewName("");
                        setNewTechPin("");
                        setMsg("Technician added");
                        await refreshTechs();
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
                <p className="text-sm font-medium">Reset tech PIN</p>
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
                  value={resetPin}
                  onChange={(e) => setResetPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
                />
                <Button
                  variant="secondary"
                  disabled={busy || !resetTechId || resetPin.length !== 4}
                  onClick={() =>
                    void (async () => {
                      setBusy(true);
                      setErr("");
                      try {
                        await api.adminResetTechPin(resetTechId, resetPin);
                        setResetPin("");
                        setMsg("PIN reset");
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
                  value={renameName}
                  onChange={(e) => setRenameName(e.target.value)}
                />
                <Button
                  variant="secondary"
                  disabled={busy || !renameTechId || !renameName.trim()}
                  onClick={() =>
                    void (async () => {
                      setBusy(true);
                      setErr("");
                      try {
                        await api.adminRenameTech(renameTechId, renameName.trim());
                        setRenameName("");
                        setMsg("Renamed");
                        await refreshTechs();
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
                        await refreshTechs();
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
              Also see <Link to="/techs" className="text-accent hover:underline">Technicians</Link>{" "}
              for the simple add form.
            </p>
          </section>

          <section className="space-y-3 rounded-2xl border border-border bg-surface p-5">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Change admin PIN
            </h2>
            <div className="flex flex-wrap gap-2">
              <Input
                type="password"
                inputMode="numeric"
                maxLength={4}
                className="w-28"
                placeholder="Current"
                value={oldAdminPin}
                onChange={(e) =>
                  setOldAdminPin(e.target.value.replace(/\D/g, "").slice(0, 4))
                }
              />
              <Input
                type="password"
                inputMode="numeric"
                maxLength={4}
                className="w-28"
                placeholder="New"
                value={newAdminPin}
                onChange={(e) =>
                  setNewAdminPin(e.target.value.replace(/\D/g, "").slice(0, 4))
                }
              />
              <Button
                variant="secondary"
                disabled={busy || oldAdminPin.length !== 4 || newAdminPin.length !== 4}
                onClick={() =>
                  void (async () => {
                    setBusy(true);
                    setErr("");
                    try {
                      await api.adminChangePin(oldAdminPin, newAdminPin);
                      setOldAdminPin("");
                      setNewAdminPin("");
                      setMsg("Admin PIN updated");
                      await refreshSession();
                    } catch (e) {
                      setErr(e instanceof Error ? e.message : "Change failed");
                    } finally {
                      setBusy(false);
                    }
                  })()
                }
              >
                Update PIN
              </Button>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
