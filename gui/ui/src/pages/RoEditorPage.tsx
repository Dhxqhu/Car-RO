import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Cable,
  Camera,
  FileDown,
  History,
  ImagePlus,
  Inbox,
  RefreshCw,
  Smartphone,
  Trash2,
} from "lucide-react";
import { api, photoUrl, type RepairOrder } from "@/lib/api";
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

const PHOTO_TAGS = ["intake", "diag", "other"] as const;

export function RoEditorPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const [order, setOrder] = useState<RepairOrder>(empty);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);
  const [photoTag, setPhotoTag] = useState<(typeof PHOTO_TAGS)[number]>("intake");
  const [photoNotes, setPhotoNotes] = useState("");
  const [phoneSession, setPhoneSession] = useState<{
    url: string;
    help_url: string;
    mode: string;
  } | null>(null);
  const [photoBusy, setPhotoBusy] = useState(false);

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
    if (!confirm(`Delete ${order.id}?`)) {
      return;
    }
    try {
      await api.deleteRo(order.id);
      nav("/");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function onFilesSelected(files: FileList | null) {
    if (!files?.length || !order.id) return;
    setPhotoBusy(true);
    setErr("");
    setMsg("");
    try {
      const updated = await api.uploadPhotos(
        order.id,
        Array.from(files),
        photoTag,
        photoNotes,
      );
      setOrder(updated);
      setPhotoNotes("");
      setMsg(`Attached ${files.length} photo(s)`);
      setPhoneSession(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setPhotoBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function ingestInbox() {
    if (!order.id) return;
    setPhotoBusy(true);
    setErr("");
    setMsg("");
    try {
      const updated = await api.ingestInboxPhotos(order.id, photoTag, photoNotes);
      setOrder(updated);
      setPhotoNotes("");
      setMsg("Ingested inbox photos");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Inbox ingest failed");
    } finally {
      setPhotoBusy(false);
    }
  }

  async function startPhone(mode: "phone" | "shortcut") {
    if (!order.id) return;
    setPhotoBusy(true);
    setErr("");
    setMsg("");
    try {
      const sess = await api.startPhoneUpload(order.id, photoTag, mode);
      setPhoneSession({
        url: sess.url,
        help_url: sess.help_url,
        mode: sess.mode,
      });
      setMsg(
        mode === "phone"
          ? "Phone upload session ready — open the URL on the iPhone (Tailscale on), then Refresh."
          : "Shortcut session ready — open the setup page, then Refresh after sharing photos.",
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Phone upload failed");
    } finally {
      setPhotoBusy(false);
    }
  }

  async function refreshPhotos() {
    if (!order.id) return;
    setPhotoBusy(true);
    setErr("");
    setMsg("");
    try {
      const updated = await api.refreshPhotos(order.id);
      const localFiles = updated._local_files;
      setOrder({
        ...updated,
        photos: updated.photos || [],
      });
      setMsg(
        localFiles != null
          ? `Refreshed — ${updated.photos?.length || 0} photo(s), ${localFiles} local file(s)`
          : "Refreshed photos from server",
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setPhotoBusy(false);
    }
  }

  const historyHref = `/history?${new URLSearchParams({
    ...(order.vin ? { vin: order.vin } : {}),
    ...(order.last_name || order.first_name
      ? {
          name: [order.first_name, order.last_name].filter(Boolean).join(" "),
        }
      : {}),
    ...(order.id ? { exclude: order.id } : {}),
  }).toString()}`;

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
          <Button variant="secondary" onClick={() => nav(historyHref)}>
            <History className="h-4 w-4" />
            History
          </Button>
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

      <section className="space-y-4 rounded-2xl border border-border bg-surface p-5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">Photos</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Tag">
            <select
              className="flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
              value={photoTag}
              onChange={(e) => setPhotoTag(e.target.value as (typeof PHOTO_TAGS)[number])}
            >
              {PHOTO_TAGS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Note (optional)">
            <Input
              value={photoNotes}
              onChange={(e) => setPhotoNotes(e.target.value)}
              placeholder="Applies to next attach"
            />
          </Field>
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            ref={fileRef}
            type="file"
            accept="image/*,.heic"
            multiple
            className="hidden"
            onChange={(e) => void onFilesSelected(e.target.files)}
          />
          <Button
            variant="secondary"
            disabled={photoBusy || !order.id}
            onClick={() => fileRef.current?.click()}
          >
            <ImagePlus className="h-4 w-4" />
            Add files
          </Button>
          <Button
            variant="secondary"
            disabled={photoBusy || !order.id}
            onClick={() => void ingestInbox()}
          >
            <Inbox className="h-4 w-4" />
            Ingest inbox
          </Button>
          <Button
            variant="secondary"
            disabled={photoBusy || !order.id}
            onClick={() => void startPhone("phone")}
          >
            <Camera className="h-4 w-4" />
            Phone QR
          </Button>
          <Button
            variant="secondary"
            disabled={photoBusy || !order.id}
            onClick={() => void startPhone("shortcut")}
          >
            <Smartphone className="h-4 w-4" />
            Shortcut
          </Button>
          <Button
            variant="secondary"
            disabled={photoBusy || !order.id}
            onClick={() => void refreshPhotos()}
          >
            <RefreshCw className="h-4 w-4" />
            Refresh from server
          </Button>
        </div>

        {phoneSession ? (
          <div className="space-y-2 rounded-xl border border-border/80 bg-bg/60 p-4 text-sm">
            <p className="font-medium capitalize">{phoneSession.mode} upload session</p>
            <p className="break-all">
              <a className="text-accent underline" href={phoneSession.url} target="_blank" rel="noreferrer">
                {phoneSession.url}
              </a>
            </p>
            {phoneSession.help_url !== phoneSession.url ? (
              <p className="break-all text-muted">
                Setup:{" "}
                <a
                  className="text-accent underline"
                  href={phoneSession.help_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {phoneSession.help_url}
                </a>
              </p>
            ) : null}
            <Button size="sm" disabled={photoBusy} onClick={() => void refreshPhotos()}>
              Done uploading — refresh
            </Button>
          </div>
        ) : null}

        {(order.photos?.length || 0) === 0 ? (
          <p className="text-sm text-muted">No photos yet — add files, inbox, or phone upload.</p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {order.photos.map((p, i) => {
              const rel = String(p.relpath || p.filename || "");
              const tag = String(p.tag || "other");
              const note = String(p.notes || p.note || "");
              const thumb = rel && order.id ? photoUrl(order.id, rel) : "";
              return (
                <li
                  key={String(p.id || i)}
                  className="overflow-hidden rounded-xl border border-border/80"
                >
                  {thumb ? (
                    <a href={thumb} target="_blank" rel="noreferrer" className="block bg-border/20">
                      <img
                        src={thumb}
                        alt={String(p.filename || "photo")}
                        className="h-36 w-full object-cover"
                        loading="lazy"
                      />
                    </a>
                  ) : null}
                  <div className="space-y-0.5 px-3 py-2 text-sm">
                    <div>
                      <span className="font-medium uppercase text-muted">{tag}</span>
                      {" · "}
                      {String(p.filename || rel || "photo")}
                    </div>
                    {note ? <div className="text-muted">{note}</div> : null}
                  </div>
                </li>
              );
            })}
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
