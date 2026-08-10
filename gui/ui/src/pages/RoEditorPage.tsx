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
import {
  api,
  photoUrl,
  type RepairOrder,
  type Technician,
  type WorkItem,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { formatPhotoTag, formatStatus, formatUploadMode } from "@/lib/utils";

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
  assigned_to_id: "",
  assigned_to_name: "",
  assigned_at: "",
  current_tech_id: "",
  current_tech_name: "",
  current_since: "",
  status: "open",
  obd_snapshot: "",
  photos: [],
  work_items: [],
  created: "",
  updated: "",
};

const PHOTO_TAGS = ["intake", "diag", "other"] as const;
const ITEM_STATUSES = ["open", "in_progress", "waiting_parts", "done", "declined"] as const;
const RO_STATUSES = ["open", "assigned", "in_progress", "done"] as const;

const emptyItem = (): WorkItem => ({
  id: "",
  concern: "",
  notes: "",
  status: "open",
  assigned_to_id: "",
  assigned_to_name: "",
});

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
  const [draftItem, setDraftItem] = useState<WorkItem>(emptyItem());
  const [itemBusy, setItemBusy] = useState(false);
  const [lastPdf, setLastPdf] = useState<{
    path: string;
    include_photos: boolean;
  } | null>(null);
  const [techs, setTechs] = useState<Technician[]>([]);
  const [me, setMe] = useState<Technician | null>(null);
  const [currentBusy, setCurrentBusy] = useState(false);

  useEffect(() => {
    void api
      .listTechs()
      .then((r) => setTechs(r.technicians || []))
      .catch(() => undefined);
    void api
      .whoami()
      .then((r) => setMe(r.technician))
      .catch(() => undefined);
  }, []);

  const isMyCurrent =
    !!me &&
    ((!!me.id && order.current_tech_id === me.id) ||
      (!!me.name && order.current_tech_name === me.name));

  async function toggleCurrentTask() {
    if (!order.id || !me) return;
    setCurrentBusy(true);
    setErr("");
    try {
      const next = await api.setCurrentTask(order.id, !isMyCurrent);
      setOrder(next);
      setMsg(
        !isMyCurrent
          ? "Set as your current task — others see this on Assigned"
          : "Cleared current task",
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not update current task");
    } finally {
      setCurrentBusy(false);
    }
  }

  useEffect(() => {
    if (!id) return;
    api
      .getRo(id)
      .then((o) => {
        setOrder(o);
        if (!o.work_items?.length && (o.complaint || o.tech_notes)) {
          /* legacy blob — engine/from_dict synthesizes on next save */
        }
      })
      .catch((e: Error) => setErr(e.message));
  }, [id]);

  function setRoAssignee(techId: string) {
    if (!techId) {
      setOrder((o) => ({
        ...o,
        assigned_to_id: "",
        assigned_to_name: "",
        assigned_at: "",
        status: o.status === "assigned" ? "open" : o.status,
      }));
      return;
    }
    const t = techs.find((x) => x.id === techId);
    setOrder((o) => ({
      ...o,
      assigned_to_id: techId,
      assigned_to_name: t?.name || "",
      assigned_at: o.assigned_at || new Date().toISOString().slice(0, 19),
      status: o.status === "open" ? "assigned" : o.status,
    }));
  }

  function setItemAssignee(techId: string) {
    if (!techId) {
      setDraftItem((d) => ({ ...d, assigned_to_id: "", assigned_to_name: "" }));
      return;
    }
    const t = techs.find((x) => x.id === techId);
    setDraftItem((d) => ({
      ...d,
      assigned_to_id: techId,
      assigned_to_name: t?.name || "",
    }));
  }

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

  async function pdf(includePhotos: boolean) {
    setErr("");
    setMsg("");
    try {
      const r = await api.exportPdf(order.id, { include_photos: includePhotos });
      const mode = includePhotos ? "with photos" : "no photos";
      setLastPdf({ path: r.path, include_photos: includePhotos });
      setMsg(`PDF (${mode}) → ${r.path}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "PDF failed");
    }
  }

  async function viewPdf() {
    if (!order.id || !lastPdf) return;
    setErr("");
    try {
      const r = await api.openPdf(order.id, { include_photos: lastPdf.include_photos });
      if (r.opened) {
        setMsg(`Opened PDF with ${r.viewer || "system viewer"}`);
      } else {
        window.open(api.pdfViewUrl(order.id, lastPdf.include_photos), "_blank", "noopener");
        setMsg("Opened PDF in browser");
      }
    } catch (e) {
      // Fallback: stream in a new tab
      try {
        window.open(api.pdfViewUrl(order.id, lastPdf.include_photos), "_blank", "noopener");
        setMsg("Opened PDF in browser");
      } catch {
        setErr(e instanceof Error ? e.message : "Could not open PDF");
      }
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
              {order.current_tech_name
                ? ` · Working now: ${order.current_tech_name}`
                : ""}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {me ? (
            <Button
              variant={isMyCurrent ? "default" : "secondary"}
              disabled={currentBusy || !order.id}
              onClick={() => void toggleCurrentTask()}
            >
              {currentBusy
                ? "Updating…"
                : isMyCurrent
                  ? "Clear current task"
                  : "Set as my current task"}
            </Button>
          ) : null}
          <Button variant="secondary" onClick={() => nav(historyHref)}>
            <History className="h-4 w-4" />
            History
          </Button>
          <Button variant="secondary" onClick={() => void pullObd()}>
            <Cable className="h-4 w-4" />
            Pull OBD
          </Button>
          <Button variant="secondary" onClick={() => void pdf(true)}>
            <FileDown className="h-4 w-4" />
            PDF + photos
          </Button>
          <Button variant="secondary" onClick={() => void pdf(false)}>
            <FileDown className="h-4 w-4" />
            PDF (no photos)
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

      {msg || lastPdf ? (
        <div className="flex flex-wrap items-center gap-3">
          {msg ? <p className="text-sm text-accent">{msg}</p> : null}
          {lastPdf ? (
            <Button type="button" size="sm" variant="secondary" onClick={() => void viewPdf()}>
              View PDF
            </Button>
          ) : null}
        </div>
      ) : null}
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
              {RO_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {formatStatus(s)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Assigned tech (whole RO)">
            <select
              className="flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
              value={order.assigned_to_id || ""}
              onChange={(e) => setRoAssignee(e.target.value)}
            >
              <option value="">Unassigned</option>
              {techs.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-muted">
              For one tech on the car. Split work below by assigning individual items.
            </p>
          </Field>
        </fieldset>
      </section>

      <section className="space-y-4 rounded-2xl border border-border bg-surface p-5">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Work items
            </h2>
            <p className="mt-1 text-xs text-muted">
              Itemize concerns and assign each to a tech when more than one person works the car.
            </p>
          </div>
          <Button
            type="button"
            variant="secondary"
            disabled={itemBusy || !order.id}
            onClick={() => {
              setDraftItem(emptyItem());
            }}
          >
            New item
          </Button>
        </div>

        {(order.work_items || []).length === 0 ? (
          <p className="text-sm text-muted">
            No work items yet
            {order.complaint || order.tech_notes
              ? " — legacy notes will become item WI-001 on next item save."
              : "."}
          </p>
        ) : (
          <ul className="space-y-3">
            {(order.work_items || []).map((item) => (
              <li
                key={item.id}
                className="rounded-xl border border-border bg-bg/40 px-4 py-3 text-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-mono text-xs text-muted">
                    {item.id} · {formatStatus(item.status)}
                    {item.assigned_to_name
                      ? ` · ${item.assigned_to_name}`
                      : item.assigned_to_id
                        ? ` · ${item.assigned_to_id}`
                        : ""}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => setDraftItem({ ...item })}
                    >
                      Edit
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="danger"
                      disabled={itemBusy}
                      onClick={() =>
                        void (async () => {
                          setItemBusy(true);
                          setErr("");
                          try {
                            const next = await api.deleteWorkItem(order.id, item.id);
                            setOrder(next);
                            setMsg(`Removed ${item.id}`);
                            if (draftItem.id === item.id) setDraftItem(emptyItem());
                          } catch (e) {
                            setErr(e instanceof Error ? e.message : "Delete failed");
                          } finally {
                            setItemBusy(false);
                          }
                        })()
                      }
                    >
                      Delete
                    </Button>
                  </div>
                </div>
                <p className="mt-2 whitespace-pre-wrap">{item.concern || "—"}</p>
                {item.notes ? (
                  <p className="mt-2 whitespace-pre-wrap text-muted">
                    <span className="text-xs uppercase tracking-wide">Notes · </span>
                    {item.notes}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        )}

        <div className="space-y-3 border-t border-border pt-4">
          <div className="text-xs font-medium uppercase tracking-wide text-muted">
            {draftItem.id ? `Edit ${draftItem.id}` : "Add work item"}
          </div>
          <Field label="Customer concern / request">
            <Textarea
              value={draftItem.concern}
              onChange={(e) => setDraftItem((d) => ({ ...d, concern: e.target.value }))}
              placeholder="e.g. Brake noise when cold"
            />
          </Field>
          <Field label="Diagnosis / technician notes">
            <Textarea
              value={draftItem.notes}
              onChange={(e) => setDraftItem((d) => ({ ...d, notes: e.target.value }))}
              placeholder="Findings for this item"
            />
          </Field>
          <Field label="Status">
            <select
              className="flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
              value={draftItem.status || "open"}
              onChange={(e) => setDraftItem((d) => ({ ...d, status: e.target.value }))}
            >
              {ITEM_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {formatStatus(s)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Assigned tech (this item)">
            <select
              className="flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
              value={draftItem.assigned_to_id || ""}
              onChange={(e) => setItemAssignee(e.target.value)}
            >
              <option value="">Unassigned</option>
              {techs.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </Field>
          <Button
            type="button"
            disabled={itemBusy || !order.id || !draftItem.concern.trim()}
            onClick={() =>
              void (async () => {
                setItemBusy(true);
                setErr("");
                try {
                  // Seed from legacy blobs once if empty
                  if (
                    !(order.work_items || []).length &&
                    (order.complaint || order.tech_notes)
                  ) {
                    await api.saveRo(order);
                  }
                  const next = await api.upsertWorkItem(order.id, {
                    id: draftItem.id || undefined,
                    concern: draftItem.concern,
                    notes: draftItem.notes,
                    status: draftItem.status,
                    assigned_to_id: draftItem.assigned_to_id || "",
                    assigned_to_name: draftItem.assigned_to_name || "",
                  });
                  setOrder(next);
                  setDraftItem(emptyItem());
                  setMsg(draftItem.id ? `Updated ${draftItem.id}` : "Work item added");
                } catch (e) {
                  setErr(e instanceof Error ? e.message : "Work item save failed");
                } finally {
                  setItemBusy(false);
                }
              })()
            }
          >
            {itemBusy ? "Saving…" : draftItem.id ? "Update item" : "Add item"}
          </Button>
        </div>
      </section>

      <Field label="OBD snapshot">
        <Textarea
          className="min-h-[16rem] max-h-[28rem] overflow-y-auto font-mono text-sm leading-relaxed"
          value={order.obd_snapshot}
          onChange={(e) => set("obd_snapshot", e.target.value)}
          onWheel={(e) => {
            // Textareas often trap wheel/touchpad even when they can't scroll —
            // pass through to the page at the edges (or when content fits).
            const el = e.currentTarget;
            const canScroll = el.scrollHeight > el.clientHeight + 1;
            const atTop = el.scrollTop <= 0;
            const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 1;
            if (!canScroll || (e.deltaY < 0 && atTop) || (e.deltaY > 0 && atBottom)) {
              e.preventDefault();
              window.scrollBy({ top: e.deltaY, left: 0, behavior: "auto" });
            }
          }}
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
                  {formatPhotoTag(t)}
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
            <p className="font-medium">
              {formatUploadMode(phoneSession.mode)} upload session
            </p>
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
                      <span className="font-medium text-muted">{formatPhotoTag(tag)}</span>
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
