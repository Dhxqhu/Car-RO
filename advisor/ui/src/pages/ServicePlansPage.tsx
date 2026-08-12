import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type RepairOrder,
  type ServicePlan,
  type ServicePlanLine,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn, formatStatus } from "@/lib/utils";

const TAGS = [
  { value: "si_im", label: "SI/IM" },
  { value: "si_only", label: "SI only" },
  { value: "service", label: "Service" },
  { value: "diag", label: "Diag" },
  { value: "repair", label: "Repair" },
  { value: "other", label: "Other" },
] as const;
const PA_TAG_VALUES = new Set(["si_im", "si_only"]);

function visiblePlanTags(paEnabled: boolean) {
  return TAGS.filter((t) => paEnabled || !PA_TAG_VALUES.has(t.value));
}

function tagLabel(tag?: string): string {
  const hit = TAGS.find((t) => t.value === tag);
  return hit?.label || formatStatus(tag || "service");
}

function planName(p: ServicePlan): string {
  const n = `${p.last_name || ""}, ${p.first_name || ""}`.replace(/^,\s*|,\s*$/g, "").trim();
  return n || "(no name)";
}

function planVehicle(p: ServicePlan): string {
  return [p.year, p.make, p.model].filter(Boolean).join(" ").trim();
}

function emptyLine(): Partial<ServicePlanLine> {
  return {
    id: "",
    label: "Oil change",
    interval_months: 6,
    tag: "service",
    last_done_at: "",
    next_due: "",
    notes: "",
  };
}

export function ServicePlansPage() {
  const [plans, setPlans] = useState<ServicePlan[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setErr("");
    try {
      const r = await api.listServicePlans();
      setPlans(r.plans || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load plans");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const open = plans.find((p) => p.id === openId) || null;

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">Service plans</h1>
        <p className="text-sm text-muted">
          Yearly SI/IM rolls on from completed inspections. Add oil, trans, etc. for customers who want a schedule.
        </p>
        <Button className="ml-auto" size="sm" onClick={() => setCreating(true)}>
          New plan
        </Button>
      </div>
      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {busy && !plans.length ? <p className="text-sm text-muted">Loading…</p> : null}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,18rem)_1fr]">
        <section className="rounded-xl border border-border bg-surface p-3">
          <h2 className="mb-2 text-sm font-semibold">Vehicles</h2>
          {!plans.length ? (
            <p className="text-sm text-muted">No plans yet. Completing an SI/IM job creates one, or start from a prior record.</p>
          ) : (
            <ul className="space-y-1">
              {plans.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    className={cn(
                      "w-full rounded-lg px-2 py-1.5 text-left text-sm hover:bg-border/40",
                      openId === p.id && "bg-accent/15",
                    )}
                    onClick={() => setOpenId(p.id)}
                  >
                    <div className="font-medium">{planName(p)}</div>
                    <div className="truncate text-xs text-muted">
                      {planVehicle(p) || p.vin || p.phone || p.id}
                      {p.lines?.length ? ` · ${p.lines.length} line${p.lines.length === 1 ? "" : "s"}` : ""}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {open ? (
          <PlanEditor
            plan={open}
            onSaved={async (next) => {
              setPlans((all) => all.map((p) => (p.id === next.id ? next : p)));
              setOpenId(next.id);
            }}
            onDeleted={async (id) => {
              setPlans((all) => all.filter((p) => p.id !== id));
              setOpenId(null);
              await load();
            }}
          />
        ) : (
          <p className="text-sm text-muted">Select a vehicle, or create a plan from history.</p>
        )}
      </div>

      {creating ? (
        <NewPlanDialog
          onClose={() => setCreating(false)}
          onCreated={async (plan) => {
            setCreating(false);
            await load();
            setOpenId(plan.id);
          }}
        />
      ) : null}
    </div>
  );
}

function PlanEditor({
  plan,
  onSaved,
  onDeleted,
}: {
  plan: ServicePlan;
  onSaved: (p: ServicePlan) => Promise<void>;
  onDeleted: (id: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState(plan);
  const [line, setLine] = useState<Partial<ServicePlanLine>>(emptyLine());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [paInspectionTypes, setPaInspectionTypes] = useState(true);

  useEffect(() => {
    setDraft(plan);
    setLine(emptyLine());
    setErr("");
  }, [plan]);

  useEffect(() => {
    void api
      .getConfig()
      .then((c) => setPaInspectionTypes(c.pa_inspection_types !== false))
      .catch(() => undefined);
  }, []);

  async function saveHeader() {
    setBusy(true);
    setErr("");
    try {
      const next = await api.saveServicePlan({
        id: draft.id,
        first_name: draft.first_name,
        last_name: draft.last_name,
        phone: draft.phone,
        year: draft.year,
        make: draft.make,
        model: draft.model,
        vin: draft.vin,
        notes: draft.notes,
      });
      await onSaved(next);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  async function saveLine() {
    setBusy(true);
    setErr("");
    try {
      const next = await api.saveServicePlanLine(draft.id, {
        id: line.id || undefined,
        label: line.label || "Service",
        interval_months: Number(line.interval_months) || 12,
        tag: line.tag || "service",
        last_done_at: line.last_done_at || "",
        next_due: line.next_due || "",
        notes: line.notes || "",
      });
      setLine(emptyLine());
      await onSaved(next);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save line");
    } finally {
      setBusy(false);
    }
  }

  async function removeLine(id: string) {
    setBusy(true);
    setErr("");
    try {
      const next = await api.saveServicePlanLine(draft.id, { id, delete: true });
      await onSaved(next);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not remove line");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-4 rounded-xl border border-border bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">{planName(draft)}</h2>
          <p className="text-xs text-muted">{draft.id}</p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => void saveHeader()}>
            Save customer
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={async () => {
              if (!window.confirm("Delete this service plan?")) return;
              setBusy(true);
              try {
                await api.deleteServicePlan(draft.id);
                await onDeleted(draft.id);
              } catch (e) {
                setErr(e instanceof Error ? e.message : "Could not delete");
                setBusy(false);
              }
            }}
          >
            Delete plan
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="space-y-1">
          <Label>First</Label>
          <Input value={draft.first_name || ""} onChange={(e) => setDraft((d) => ({ ...d, first_name: e.target.value }))} />
        </div>
        <div className="space-y-1">
          <Label>Last</Label>
          <Input value={draft.last_name || ""} onChange={(e) => setDraft((d) => ({ ...d, last_name: e.target.value }))} />
        </div>
        <div className="space-y-1">
          <Label>Phone</Label>
          <Input value={draft.phone || ""} onChange={(e) => setDraft((d) => ({ ...d, phone: e.target.value }))} />
        </div>
        <div className="space-y-1">
          <Label>Year</Label>
          <Input value={draft.year || ""} onChange={(e) => setDraft((d) => ({ ...d, year: e.target.value }))} />
        </div>
        <div className="space-y-1">
          <Label>Make</Label>
          <Input value={draft.make || ""} onChange={(e) => setDraft((d) => ({ ...d, make: e.target.value }))} />
        </div>
        <div className="space-y-1">
          <Label>Model</Label>
          <Input value={draft.model || ""} onChange={(e) => setDraft((d) => ({ ...d, model: e.target.value }))} />
        </div>
        <div className="col-span-2 space-y-1 sm:col-span-3">
          <Label>VIN</Label>
          <Input value={draft.vin || ""} onChange={(e) => setDraft((d) => ({ ...d, vin: e.target.value }))} />
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold">Schedule</h3>
        <ul className="space-y-2">
          {(draft.lines || []).map((ln) => (
            <li key={ln.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-border px-2 py-1.5 text-sm">
              <button
                type="button"
                className="min-w-0 flex-1 text-left"
                onClick={() => setLine({ ...ln })}
              >
                <span className="font-medium">{ln.label}</span>
                <span className="text-muted">
                  {" "}
                  · {tagLabel(ln.tag)} · every {ln.interval_months} mo · next {ln.next_due || "—"}
                  {ln.last_done_at ? ` · last ${ln.last_done_at}` : ""}
                </span>
              </button>
              <Button size="xs" variant="secondary" disabled={busy} onClick={() => void removeLine(ln.id)}>
                Remove
              </Button>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-lg border border-border p-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">
          {line.id ? "Edit line" : "Add line"}
        </p>
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="col-span-2 space-y-1">
            <Label>Name</Label>
            <Input
              value={line.label || ""}
              onChange={(e) => setLine((l) => ({ ...l, label: e.target.value }))}
              placeholder="Oil change"
            />
          </div>
          <div className="space-y-1">
            <Label>Every (months)</Label>
            <Input
              type="number"
              min={1}
              value={line.interval_months ?? 6}
              onChange={(e) => setLine((l) => ({ ...l, interval_months: Number(e.target.value) }))}
            />
          </div>
          <div className="space-y-1">
            <Label>Tag</Label>
            <select
              className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
              value={line.tag || "service"}
              onChange={(e) => setLine((l) => ({ ...l, tag: e.target.value }))}
            >
              {visiblePlanTags(paInspectionTypes).map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label>Last done</Label>
            <Input
              type="date"
              value={line.last_done_at || ""}
              onChange={(e) => setLine((l) => ({ ...l, last_done_at: e.target.value }))}
            />
          </div>
          <div className="space-y-1">
            <Label>Next due</Label>
            <Input
              type="date"
              value={line.next_due || ""}
              onChange={(e) => setLine((l) => ({ ...l, next_due: e.target.value }))}
            />
          </div>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          <Button size="sm" disabled={busy} onClick={() => void saveLine()}>
            {line.id ? "Update line" : "Add to plan"}
          </Button>
          {line.id ? (
            <Button size="sm" variant="ghost" onClick={() => setLine(emptyLine())}>
              Cancel edit
            </Button>
          ) : null}
        </div>
      </div>

      {err ? <p className="text-sm text-danger">{err}</p> : null}
      <p className="text-xs text-muted">
        Due lines show on the <Link to="/calendar" className="text-accent hover:underline">calendar</Link> call list 30 days ahead.
      </p>
    </section>
  );
}

function NewPlanDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (plan: ServicePlan) => Promise<void>;
}) {
  const [vin, setVin] = useState("");
  const [name, setName] = useState("");
  const [hits, setHits] = useState<RepairOrder[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [blank, setBlank] = useState({
    first_name: "",
    last_name: "",
    phone: "",
    year: "",
    make: "",
    model: "",
    vin: "",
  });

  async function lookup() {
    if (!vin.trim() && !name.trim()) {
      setErr("Enter a VIN and/or customer name or phone");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const r = await api.history(vin, name);
      setHits(r.orders || []);
      setNote(r.note || (r.orders?.length ? "" : "No prior jobs found"));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Lookup failed");
      setHits([]);
    } finally {
      setBusy(false);
    }
  }

  async function createFrom(fields: typeof blank) {
    setBusy(true);
    setErr("");
    try {
      const plan = await api.saveServicePlan({ ...fields, lines: [] });
      await onCreated(plan);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not create plan");
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="Close" onClick={onClose} />
      <div className="relative z-10 max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-border bg-surface p-5 shadow-lg">
        <h2 className="text-lg font-semibold">New service plan</h2>
        <p className="mt-1 text-sm text-muted">From a prior job, or enter the customer and vehicle.</p>

        <div className="mt-3 flex flex-wrap gap-2">
          <Input placeholder="VIN" className="h-8 w-28" value={vin} onChange={(e) => setVin(e.target.value)} />
          <Input
            placeholder="Name or phone"
            className="h-8 min-w-[8rem] flex-1"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => void lookup()}>
            Search
          </Button>
        </div>
        {note ? <p className="mt-2 text-xs text-muted">{note}</p> : null}
        {hits.length ? (
          <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto text-sm">
            {hits.map((o) => (
              <li key={o.id}>
                <button
                  type="button"
                  className="w-full rounded-md px-2 py-1 text-left hover:bg-border/40"
                  disabled={busy}
                  onClick={() =>
                    void createFrom({
                      first_name: o.first_name,
                      last_name: o.last_name,
                      phone: o.phone,
                      year: o.year,
                      make: o.make,
                      model: o.model,
                      vin: o.vin,
                    })
                  }
                >
                  <span className="font-medium">
                    {o.last_name}, {o.first_name}
                  </span>
                  <span className="text-muted">
                    {" "}
                    · {[o.year, o.make, o.model].filter(Boolean).join(" ")} · {o.id}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        <div className="mt-4 grid grid-cols-2 gap-2">
          <Input placeholder="First" value={blank.first_name} onChange={(e) => setBlank((b) => ({ ...b, first_name: e.target.value }))} />
          <Input placeholder="Last" value={blank.last_name} onChange={(e) => setBlank((b) => ({ ...b, last_name: e.target.value }))} />
          <Input placeholder="Phone" className="col-span-2" value={blank.phone} onChange={(e) => setBlank((b) => ({ ...b, phone: e.target.value }))} />
          <Input placeholder="Year" value={blank.year} onChange={(e) => setBlank((b) => ({ ...b, year: e.target.value }))} />
          <Input placeholder="Make" value={blank.make} onChange={(e) => setBlank((b) => ({ ...b, make: e.target.value }))} />
          <Input placeholder="Model" className="col-span-2" value={blank.model} onChange={(e) => setBlank((b) => ({ ...b, model: e.target.value }))} />
          <Input placeholder="VIN" className="col-span-2" value={blank.vin} onChange={(e) => setBlank((b) => ({ ...b, vin: e.target.value }))} />
        </div>

        {err ? <p className="mt-3 text-sm text-danger">{err}</p> : null}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          <Button disabled={busy} onClick={() => void createFrom(blank)}>
            Create blank
          </Button>
        </div>
      </div>
    </div>
  );
}
