import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Cable, FileDown, Trash2 } from "lucide-react";
import { api, type RepairOrder } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const empty: RepairOrder = {
  id: "",
  first_name: "",
  last_name: "",
  phone: "",
  year: "",
  make: "",
  model: "",
  vin: "",
  mileage: "",
  plate: "",
  complaint: "",
  tech_notes: "",
  technician_name: "",
  technician_id: "",
  status: "open",
  obd_snapshot: "",
  photos: [],
  created: "",
  updated: "",
};

export function RoEditorPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [order, setOrder] = useState<RepairOrder>(empty);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!id) return;
    api
      .getRo(id)
      .then(setOrder)
      .catch((e: Error) => setErr(e.message));
  }, [id]);

  function set<K extends keyof RepairOrder>(key: K, value: RepairOrder[K]) {
    setOrder((o) => ({ ...o, [key]: value }));
  }

  async function save() {
    setSaving(true);
    setErr("");
    setMsg("");
    try {
      const saved = await api.saveRo(order);
      setOrder(saved);
      setMsg("Saved");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function pdf() {
    setErr("");
    try {
      const r = await api.exportPdf(order.id);
      setMsg(`PDF → ${r.path}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "PDF failed");
    }
  }

  async function pullObd() {
    if (!order.id) return;
    setErr("");
    setMsg("");
    try {
      const updated = await api.pullObd(order.id);
      setOrder(updated);
      setMsg("Pulled OBD / Saved Codes");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "OBD pull failed");
    }
  }

  async function remove() {
    if (!confirm(`Delete ${order.id}? Type-confirm in CLI is stricter; this GUI asks once.`)) {
      return;
    }
    try {
      await api.deleteRo(order.id);
      nav("/");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Delete failed");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => nav("/")} aria-label="Back">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold">
              {order.id || "Repair order"}
            </h1>
            <p className="text-sm text-muted">
              Tech: {order.technician_name || "—"} · Updated {order.updated || "—"}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => void pullObd()}>
            <Cable className="h-4 w-4" />
            Pull OBD
          </Button>
          <Button variant="secondary" onClick={() => void pdf()}>
            <FileDown className="h-4 w-4" />
            PDF
          </Button>
          <Button variant="danger" onClick={() => void remove()}>
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
          <Button onClick={() => void save()} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>

      {msg ? <p className="text-sm text-accent">{msg}</p> : null}
      {err ? <p className="text-sm text-danger">{err}</p> : null}

      <section className="grid gap-6 md:grid-cols-2">
        <fieldset className="space-y-3 rounded-2xl border border-border bg-surface p-5">
          <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-accent">
            Customer
          </legend>
          <Field label="First name">
            <Input value={order.first_name} onChange={(e) => set("first_name", e.target.value)} />
          </Field>
          <Field label="Last name">
            <Input value={order.last_name} onChange={(e) => set("last_name", e.target.value)} />
          </Field>
          <Field label="Phone">
            <Input value={order.phone} onChange={(e) => set("phone", e.target.value)} />
          </Field>
        </fieldset>

        <fieldset className="space-y-3 rounded-2xl border border-border bg-surface p-5">
          <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-accent">
            Vehicle
          </legend>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Year">
              <Input value={order.year} onChange={(e) => set("year", e.target.value)} />
            </Field>
            <Field label="Make">
              <Input value={order.make} onChange={(e) => set("make", e.target.value)} />
            </Field>
            <Field label="Model">
              <Input value={order.model} onChange={(e) => set("model", e.target.value)} />
            </Field>
          </div>
          <Field label="VIN">
            <Input value={order.vin} onChange={(e) => set("vin", e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Plate">
              <Input value={order.plate} onChange={(e) => set("plate", e.target.value)} />
            </Field>
            <Field label="Mileage">
              <Input value={order.mileage} onChange={(e) => set("mileage", e.target.value)} />
            </Field>
          </div>
          <Field label="Status">
            <select
              className="flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
              value={order.status}
              onChange={(e) => set("status", e.target.value)}
            >
              <option value="open">open</option>
              <option value="in_progress">in_progress</option>
              <option value="done">done</option>
            </select>
          </Field>
        </fieldset>
      </section>

      <Field label="Customer concern / request">
        <Textarea value={order.complaint} onChange={(e) => set("complaint", e.target.value)} />
      </Field>
      <Field label="Diagnosis & technician notes">
        <Textarea value={order.tech_notes} onChange={(e) => set("tech_notes", e.target.value)} />
      </Field>
      <Field label="OBD snapshot">
        <Textarea
          className="font-mono text-xs"
          value={order.obd_snapshot}
          onChange={(e) => set("obd_snapshot", e.target.value)}
        />
      </Field>

      <section className="rounded-2xl border border-border bg-surface p-5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">Photos</h2>
        {(order.photos?.length || 0) === 0 ? (
          <p className="mt-2 text-sm text-muted">
            No photos yet. Attach with CLI: <code className="text-fg">carro photo …</code>
          </p>
        ) : (
          <ul className="mt-3 space-y-2 text-sm">
            {order.photos.map((p, i) => (
              <li key={String(p.id || i)} className="flex justify-between gap-3 border-b border-border/60 py-2 last:border-0">
                <span>
                  <span className="font-medium uppercase text-muted">{String(p.tag || "other")}</span>
                  {" · "}
                  {String(p.filename || p.relpath || "photo")}
                </span>
                <span className="text-muted">{String(p.notes || p.note || "")}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="text-sm text-muted">
        <Link className="text-accent underline" to="/">
          Back to list
        </Link>
      </p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
