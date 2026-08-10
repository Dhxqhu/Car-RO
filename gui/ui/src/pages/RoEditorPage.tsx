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
  type FoundIssue,
  type RepairOrder,
  type Technician,
  type WorkItem,
  type WorkItemPart,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { formatDurationMinutes, formatPhotoTag, formatShopTime, formatStatus, formatUploadMode, formatWorkedHours, formatWorkedMinutes } from "@/lib/utils";

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
  current_item_id: "",
  started_at: "",
  done_at: "",
  billed_out_at: "",
  waiting_since: "",
  parts_requested_at: "",
  parts_requested_by: "",
  approval_requested_at: "",
  approval_requested_by: "",
  status: "open",
  obd_snapshot: "",
  photos: [],
  work_items: [],
  found_issues: [],
  created: "",
  updated: "",
};

const PHOTO_TAGS = ["intake", "diag", "other"] as const;
const ITEM_TYPES = [
  { value: "diag", label: "Diag" },
  { value: "service", label: "Service" },
  { value: "repair", label: "Repair" },
  { value: "other", label: "Other" },
] as const;
const ITEM_STATUSES = [
  "open",
  "in_progress",
  "waiting_parts",
  "waiting_customer",
  "done",
  "declined",
] as const;
const PART_STATUSES = [
  { value: "new_request", label: "New request" },
  { value: "ordered", label: "Ordered" },
  { value: "received", label: "Received" },
  { value: "received_wrong", label: "Received wrong" },
] as const;
const RO_STATUSES = [
  "open",
  "assigned",
  "in_progress",
  "waiting_parts",
  "waiting_customer",
  "done",
  "billed_out",
] as const;

const emptyItem = (): WorkItem => ({
  id: "",
  concern: "",
  notes: "",
  private_notes: "",
  item_type: "",
  status: "open",
  worked_minutes: 0,
  time_log: [],
  timer_started_at: "",
  parts: [],
});

const emptyPartDraft = (make = ""): WorkItemPart => ({
  id: "",
  description: "",
  part_number: "",
  manufacturer: make,
  status: "new_request",
});

function itemTypeLabel(t?: string): string {
  const hit = ITEM_TYPES.find((x) => x.value === t);
  return hit?.label || (t ? formatStatus(t) : "—");
}

function partStatusLabel(s?: string): string {
  const hit = PART_STATUSES.find((x) => x.value === s);
  return hit?.label || formatStatus(s);
}

function roleLabel(role?: string): string {
  if (role === "advisor") return "advisor";
  if (role === "tech") return "tech";
  return "";
}

function formatRoleWho(name?: string, role?: string): string {
  const n = (name || "").trim();
  if (!n) return "";
  const r = roleLabel(role);
  return r ? `${n} (${r})` : n;
}

function orderWorkedMinutes(o: RepairOrder): number {
  return (o.work_items || []).reduce(
    (sum, it) => sum + Math.max(0, Number(it.worked_minutes) || 0),
    0,
  );
}

function itemDowntimeMinutes(it: WorkItem): number {
  const totals = it.stage_totals || {};
  let parts = Math.max(0, Number(totals.waiting_parts_minutes) || 0);
  let customer = Math.max(0, Number(totals.waiting_customer_minutes) || 0);
  const st = (it.status || "").toLowerCase();
  if ((st === "waiting_parts" || st === "waiting_customer") && it.stage_entered_at) {
    const started = Date.parse(it.stage_entered_at);
    if (!Number.isNaN(started)) {
      const live = Math.max(0, Math.round((Date.now() - started) / 60000));
      if (st === "waiting_parts") parts += live;
      else customer += live;
    }
  }
  let interrupt = Math.max(0, Number(it.downtime_minutes) || 0);
  if (it.downtime_started_at) {
    const started = Date.parse(it.downtime_started_at);
    if (!Number.isNaN(started)) {
      interrupt += Math.max(0, Math.round((Date.now() - started) / 60000));
    }
  }
  return parts + customer + interrupt;
}

function orderDowntimeMinutes(o: RepairOrder): number {
  return (o.work_items || []).reduce((sum, it) => sum + itemDowntimeMinutes(it), 0);
}

function orderStageTotals(o: RepairOrder): {
  parts: number;
  customer: number;
  ageMinutes: number;
} {
  let parts = 0;
  let customer = 0;
  for (const it of o.work_items || []) {
    const t = it.stage_totals || {};
    parts += Math.max(0, Number(t.waiting_parts_minutes) || 0);
    customer += Math.max(0, Number(t.waiting_customer_minutes) || 0);
    const st = (it.status || "").toLowerCase();
    if (
      (st === "waiting_parts" || st === "waiting_customer") &&
      it.stage_entered_at
    ) {
      const started = Date.parse(it.stage_entered_at);
      if (!Number.isNaN(started)) {
        const live = Math.max(0, Math.round((Date.now() - started) / 60000));
        if (st === "waiting_parts") parts += live;
        else customer += live;
      }
    }
  }
  let ageMinutes = 0;
  const created = (o.created || "").trim();
  if (created) {
    const t0 = Date.parse(created);
    if (!Number.isNaN(t0)) {
      const endRaw = (o.done_at || o.billed_out_at || "").trim();
      const t1 = endRaw ? Date.parse(endRaw) : Date.now();
      if (!Number.isNaN(t1)) ageMinutes = Math.max(0, Math.round((t1 - t0) / 60000));
    }
  }
  return { parts, customer, ageMinutes };
}

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
  const [itemEditorOpen, setItemEditorOpen] = useState(false);
  const [draftPart, setDraftPart] = useState<WorkItemPart>(emptyPartDraft());
  const [fiEditorOpen, setFiEditorOpen] = useState(false);
  const [draftFi, setDraftFi] = useState({ description: "", notes: "" });
  const [fiBusy, setFiBusy] = useState(false);
  const [itemBusy, setItemBusy] = useState(false);
  const [roDetailsEditing, setRoDetailsEditing] = useState(false);
  const [bayItemId, setBayItemId] = useState("");
  const [bayFocus, setBayFocus] = useState<"notes" | "parts">("notes");
  const [bayNotes, setBayNotes] = useState("");
  const [bayPrivateNotes, setBayPrivateNotes] = useState("");
  const [bayPart, setBayPart] = useState<WorkItemPart>(emptyPartDraft());
  const [addMinutes, setAddMinutes] = useState("30");
  const [lastPdf, setLastPdf] = useState<{
    path: string;
    include_photos: boolean;
  } | null>(null);
  const [techs, setTechs] = useState<Technician[]>([]);
  const [me, setMe] = useState<Technician | null>(null);
  const [currentBusy, setCurrentBusy] = useState(false);
  const [adminActive, setAdminActive] = useState(false);
  const [adminSetMinutes, setAdminSetMinutes] = useState("");
  const [adminNote, setAdminNote] = useState("");

  useEffect(() => {
    void api
      .listTechs()
      .then((r) => setTechs(r.technicians || []))
      .catch(() => undefined);
    void api
      .whoami()
      .then((r) => setMe(r.technician))
      .catch(() => undefined);
    void api
      .adminSession()
      .then((s) => setAdminActive(s.active))
      .catch(() => undefined);
  }, []);

  const isMyCurrent =
    !!me &&
    ((!!me.id && order.current_tech_id === me.id) ||
      (!!me.name && order.current_tech_name === me.name));
  const currentItemId = order.current_item_id || "";

  function itemOnMyQueue(item: WorkItem): boolean {
    if (!me) return false;
    return (
      (!!me.id && item.assigned_to_id === me.id) ||
      (!!me.name && item.assigned_to_name === me.name)
    );
  }

  function itemTechBreakdown(item: WorkItem): Array<{ name: string; minutes: number }> {
    const buckets = new Map<string, { name: string; minutes: number }>();
    for (const e of item.time_log || []) {
      const mins = Math.max(0, Number(e.minutes) || 0);
      if (!mins) continue;
      const name = (e.tech_name || e.tech_id || "Unknown").trim() || "Unknown";
      const key = (e.tech_id || name).toLowerCase();
      const cur = buckets.get(key) || { name, minutes: 0 };
      cur.minutes += mins;
      buckets.set(key, cur);
    }
    return [...buckets.values()].sort((a, b) => b.minutes - a.minutes);
  }

  function overallTechBreakdown(): Array<{ name: string; minutes: number }> {
    const buckets = new Map<string, { name: string; minutes: number }>();
    for (const item of order.work_items || []) {
      for (const row of itemTechBreakdown(item)) {
        const key = row.name.toLowerCase();
        const cur = buckets.get(key) || { name: row.name, minutes: 0 };
        cur.minutes += row.minutes;
        buckets.set(key, cur);
      }
    }
    return [...buckets.values()].sort((a, b) => b.minutes - a.minutes);
  }

  function openBay(itemId: string, focus: "notes" | "parts" = "notes") {
    const item = (order.work_items || []).find((w) => w.id === itemId);
    setBayItemId(itemId);
    setBayFocus(focus);
    setBayNotes(item?.notes || "");
    setBayPrivateNotes(item?.private_notes || "");
    setBayPart(emptyPartDraft(order.make));
  }

  function closeBay() {
    setBayItemId("");
    setBayFocus("notes");
    setBayNotes("");
    setBayPrivateNotes("");
    setBayPart(emptyPartDraft(order.make));
  }

  async function setItemCurrent(itemId: string, active: boolean) {
    if (!order.id || !me) return;
    setCurrentBusy(true);
    setErr("");
    try {
      const next = await api.setCurrentTask(order.id, active, active ? itemId : undefined);
      setOrder(next);
      if (active) {
        const item = (next.work_items || []).find((w) => w.id === itemId);
        setBayItemId(itemId);
        setBayFocus("notes");
        setBayNotes(item?.notes || "");
        setBayPrivateNotes(item?.private_notes || "");
        setBayPart(emptyPartDraft(next.make));
        setMsg(`Started work on ${itemId} — notes open`);
      } else {
        closeBay();
        setMsg("Stopped current work item");
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not update current work");
    } finally {
      setCurrentBusy(false);
    }
  }

  // Crash-safe timer: bank + restart every 15 minutes while bay panel has a live timer
  const bayTimerOn = !!(order.work_items || []).find(
    (w) => w.id === bayItemId && w.timer_started_at,
  );
  useEffect(() => {
    if (!order.id || !bayItemId || !me || !bayTimerOn) return;
    const id = window.setInterval(() => {
      void (async () => {
        try {
          const next = await api.workItemTime(order.id, bayItemId, {
            action: "checkpoint",
          });
          setOrder(next);
        } catch {
          /* ignore transient heartbeat errors */
        }
      })();
    }, 15 * 60 * 1000);
    return () => window.clearInterval(id);
  }, [order.id, bayItemId, me, bayTimerOn]);

  async function queueAction(
    action:
      | "add"
      | "remove"
      | "complete"
      | "complete_item"
      | "billed_out"
      | "reopen"
      | "waiting_parts"
      | "request_parts"
      | "item_waiting_parts"
      | "waiting_customer"
      | "request_approval"
      | "item_waiting_customer",
    itemId?: string,
  ) {
    if (!order.id || !me) return;
    setCurrentBusy(true);
    setErr("");
    try {
      const next = await api.queueAction(order.id, action, itemId);
      setOrder(next);
      const labels: Record<string, string> = {
        add: itemId ? `Queued ${itemId}` : "Added to your planned queue",
        remove: itemId ? `Removed ${itemId} from queue` : "Removed from your queue",
        complete: "Marked done — in advisor ready-to-bill queue",
        complete_item: itemId ? `Completed ${itemId}` : "Item completed",
        billed_out: "Marked billed out (closed)",
        reopen: "Reopened",
        waiting_parts: "Pushed for parts order (advisor)",
        request_parts: "Pushed for parts order (advisor)",
        item_waiting_parts: itemId
          ? `${itemId} waiting on parts`
          : "Waiting on parts",
        waiting_customer: "Pushed for customer approval",
        request_approval: "Pushed for customer approval",
        item_waiting_customer: itemId
          ? `${itemId} waiting on customer`
          : "Waiting on customer",
      };
      setMsg(labels[action] || "Updated");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Queue update failed");
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

  async function workItemTime(
    itemId: string,
    action: "add" | "start" | "stop",
    minutes?: number,
  ) {
    if (!order.id || !me) return;
    setItemBusy(true);
    setErr("");
    try {
      const next = await api.workItemTime(order.id, itemId, {
        action,
        minutes,
      });
      setOrder(next);
      const labels = {
        add: `Logged ${formatWorkedMinutes(minutes || 0)} on ${itemId}`,
        start: `Timer started on ${itemId}`,
        stop: `Timer stopped on ${itemId}`,
      };
      setMsg(labels[action]);
      const updated = (next.work_items || []).find((w) => w.id === itemId);
      if (updated && draftItem.id === itemId) setDraftItem({ ...updated });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Time update failed");
    } finally {
      setItemBusy(false);
    }
  }

  async function adminCorrectTime(action: "set" | "add" | "clear", minutes?: number) {
    if (!order.id || !draftItem.id || !adminActive) return;
    setItemBusy(true);
    setErr("");
    try {
      const next = await api.adminWorkItemTime(order.id, draftItem.id, {
        action,
        minutes,
        note: adminNote || undefined,
      });
      setOrder(next);
      const updated = (next.work_items || []).find((w) => w.id === draftItem.id);
      if (updated) setDraftItem({ ...updated });
      setMsg(
        action === "clear"
          ? `Admin cleared time on ${draftItem.id}`
          : `Admin corrected time on ${draftItem.id}`,
      );
      setAdminNote("");
      setAdminSetMinutes("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Admin time correction failed");
    } finally {
      setItemBusy(false);
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
      <div className="space-y-3">
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
                ? ` · Working now: ${order.current_tech_name}${
                    order.current_item_id ? ` on ${order.current_item_id}` : ""
                  }`
                : ""}
            </p>
            {order.id ? (
              <p className="mt-0.5 text-sm font-medium text-fg">
                Total worked{" "}
                <span className="tabular-nums">{formatWorkedHours(orderWorkedMinutes(order))}</span>
                <span className="ml-1 text-xs font-normal text-muted">
                  ({formatWorkedMinutes(orderWorkedMinutes(order))} · shop only)
                </span>
              </p>
            ) : null}
            {order.id ? (
              <p className="mt-0.5 text-sm font-medium text-fg">
                Downtime{" "}
                <span className="tabular-nums">
                  {formatDurationMinutes(orderDowntimeMinutes(order))}
                </span>
                <span className="ml-1 text-xs font-normal text-muted">
                  (waits + gaps · shop only)
                </span>
              </p>
            ) : null}
            {order.id ? (
              <p className="mt-0.5 text-xs text-muted">
                Job metrics
                {(() => {
                  const m = orderStageTotals(order);
                  const bits: string[] = [];
                  if (m.ageMinutes > 0) bits.push(`age ${formatDurationMinutes(m.ageMinutes)}`);
                  if (m.parts > 0) bits.push(`parts wait ${formatDurationMinutes(m.parts)}`);
                  if (m.customer > 0)
                    bits.push(`customer wait ${formatDurationMinutes(m.customer)}`);
                  return bits.length ? ` · ${bits.join(" · ")}` : " · —";
                })()}
                <span className="text-muted/80"> (shop only — not on customer PDF)</span>
              </p>
            ) : null}
            {(order.started_at ||
              order.waiting_since ||
              order.done_at ||
              order.billed_out_at ||
              orderWorkedMinutes(order) > 0) && (
              <p className="mt-0.5 text-xs text-muted">
                Shop timing
                {order.started_at ? ` · started ${formatShopTime(order.started_at)}` : ""}
                {order.waiting_since
                  ? ` · waiting since ${formatShopTime(order.waiting_since)}`
                  : ""}
                {order.done_at ? ` · done ${formatShopTime(order.done_at)}` : ""}
                {order.billed_out_at
                  ? ` · billed out ${formatShopTime(order.billed_out_at)}`
                  : ""}
                {order.parts_requested_at
                  ? ` · parts asked ${formatShopTime(order.parts_requested_at)}${
                      order.parts_requested_by ? ` by ${order.parts_requested_by}` : ""
                    }`
                  : ""}
                {order.approval_requested_at
                  ? ` · approval asked ${formatShopTime(order.approval_requested_at)}${
                      order.approval_requested_by ? ` by ${order.approval_requested_by}` : ""
                    }`
                  : ""}
                {overallTechBreakdown().length
                  ? ` · ${overallTechBreakdown()
                      .map((t) => `${t.name} ${formatWorkedHours(t.minutes)}`)
                      .join(", ")}`
                  : ""}
                <span className="text-muted/80"> (not on customer PDF)</span>
              </p>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {me ? (
            <>
              {order.status === "done" ? (
                <>
                  <Button
                    variant="secondary"
                    disabled={currentBusy || !order.id}
                    onClick={() => void queueAction("reopen")}
                  >
                    Reopen
                  </Button>
                  <Button
                    disabled={currentBusy || !order.id}
                    onClick={() => void queueAction("billed_out")}
                  >
                    Mark billed out
                  </Button>
                </>
              ) : null}
              {order.status === "billed_out" ? (
                <Button
                  variant="secondary"
                  disabled={currentBusy || !order.id}
                  onClick={() => void queueAction("reopen")}
                >
                  Reopen
                </Button>
              ) : null}
            </>
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
        </div>
        <div className="flex flex-wrap gap-2">
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
          <div className="flex flex-wrap items-center justify-between gap-2">
            <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-accent">
              Customer
            </legend>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={!order.id}
              onClick={() => {
                if (roDetailsEditing) {
                  void (async () => {
                    try {
                      const saved = await api.saveRo(order);
                      setOrder(saved);
                      setRoDetailsEditing(false);
                      setMsg("Customer / vehicle saved");
                    } catch (e) {
                      setErr(e instanceof Error ? e.message : "Save failed");
                    }
                  })();
                } else {
                  setRoDetailsEditing(true);
                }
              }}
            >
              {roDetailsEditing ? "Done" : "Edit details"}
            </Button>
          </div>
          <Field label="First name">
            <Input
              value={order.first_name}
              readOnly={!roDetailsEditing}
              onChange={(e) => set("first_name", e.target.value)}
              className={!roDetailsEditing ? "bg-bg/40" : undefined}
            />
          </Field>
          <Field label="Last name">
            <Input
              value={order.last_name}
              readOnly={!roDetailsEditing}
              onChange={(e) => set("last_name", e.target.value)}
              className={!roDetailsEditing ? "bg-bg/40" : undefined}
            />
          </Field>
          <Field label="Phone">
            <Input
              value={order.phone}
              readOnly={!roDetailsEditing}
              onChange={(e) => set("phone", e.target.value)}
              className={!roDetailsEditing ? "bg-bg/40" : undefined}
            />
          </Field>
        </fieldset>

        <fieldset className="space-y-3 rounded-2xl border border-border bg-surface p-5">
          <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-accent">
            Vehicle
          </legend>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Year">
              <Input
                value={order.year}
                readOnly={!roDetailsEditing}
                onChange={(e) => set("year", e.target.value)}
                className={!roDetailsEditing ? "bg-bg/40" : undefined}
              />
            </Field>
            <Field label="Make">
              <Input
                value={order.make}
                readOnly={!roDetailsEditing}
                onChange={(e) => set("make", e.target.value)}
                className={!roDetailsEditing ? "bg-bg/40" : undefined}
              />
            </Field>
            <Field label="Model">
              <Input
                value={order.model}
                readOnly={!roDetailsEditing}
                onChange={(e) => set("model", e.target.value)}
                className={!roDetailsEditing ? "bg-bg/40" : undefined}
              />
            </Field>
          </div>
          <Field label="VIN">
            <Input
              value={order.vin}
              readOnly={!roDetailsEditing}
              onChange={(e) => set("vin", e.target.value)}
              className={!roDetailsEditing ? "bg-bg/40" : undefined}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Plate">
              <Input
                value={order.plate}
                readOnly={!roDetailsEditing}
                onChange={(e) => set("plate", e.target.value)}
                className={!roDetailsEditing ? "bg-bg/40" : undefined}
              />
            </Field>
            <Field label="Mileage">
              <Input
                value={order.mileage}
                readOnly={!roDetailsEditing}
                onChange={(e) => set("mileage", e.target.value)}
                className={!roDetailsEditing ? "bg-bg/40" : undefined}
              />
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
              Each concern is its own billed job. Queue and current work attach to the work item —
              the RO is only the car. Time stamps and tech totals stay shop-side (not on customer PDF).
            </p>
          </div>
          <Button
            type="button"
            variant="secondary"
            disabled={itemBusy || !order.id}
            onClick={() => {
              setDraftItem(emptyItem());
              setDraftPart(emptyPartDraft(order.make));
              setItemEditorOpen(true);
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
            {(order.work_items || []).map((item) => {
              const onQueue = itemOnMyQueue(item);
              const isCurrent =
                isMyCurrent && (currentItemId === item.id || !!item.timer_started_at);
              const breakdown = itemTechBreakdown(item);
              return (
                <li
                  key={item.id}
                  className="rounded-xl border border-border bg-bg/40 px-4 py-3 text-sm"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="font-mono text-xs text-muted">
                      {item.id} · {itemTypeLabel(item.item_type)} · {formatStatus(item.status)}
                      {item.assigned_to_name ? ` · queue ${item.assigned_to_name}` : ""}
                      {isCurrent ? " · your current work" : ""}
                      {(item.parts || []).length
                        ? ` · ${(item.parts || []).length} part(s)`
                        : ""}
                      {(item.private_notes || "").trim() ? " · private notes" : ""}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {me && order.status !== "billed_out" && order.status !== "done" ? (
                        <>
                          {!onQueue ? (
                            <Button
                              type="button"
                              size="sm"
                              variant="secondary"
                              disabled={currentBusy || itemBusy}
                              onClick={() => void queueAction("add", item.id)}
                            >
                              Add to my queue
                            </Button>
                          ) : (
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              disabled={currentBusy || itemBusy}
                              onClick={() => void queueAction("remove", item.id)}
                            >
                              Remove from queue
                            </Button>
                          )}
                          {isCurrent ? (
                            <>
                              <Button
                                type="button"
                                size="sm"
                                variant="secondary"
                                disabled={currentBusy || itemBusy}
                                onClick={() =>
                                  void queueAction("complete_item", item.id)
                                }
                              >
                                Completed
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="secondary"
                                disabled={currentBusy || itemBusy}
                                onClick={() =>
                                  void queueAction("item_waiting_parts", item.id)
                                }
                              >
                                Wait for parts
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="secondary"
                                disabled={currentBusy || itemBusy}
                                onClick={() =>
                                  void queueAction("item_waiting_customer", item.id)
                                }
                              >
                                Waiting on customer
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                disabled={currentBusy || itemBusy}
                                onClick={() => void setItemCurrent(item.id, false)}
                              >
                                Stop working
                              </Button>
                            </>
                          ) : (
                            <Button
                              type="button"
                              size="sm"
                              variant="secondary"
                              disabled={currentBusy || itemBusy}
                              onClick={() => void setItemCurrent(item.id, true)}
                            >
                              Start work
                            </Button>
                          )}
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            disabled={currentBusy || itemBusy || !me}
                            onClick={() =>
                              void (async () => {
                                if (!isCurrent) {
                                  await setItemCurrent(item.id, true);
                                }
                                openBay(item.id, "parts");
                                setMsg(`Parts open for ${item.id}`);
                              })()
                            }
                          >
                            Add parts
                          </Button>
                        </>
                      ) : null}
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setDraftItem({ ...item });
                          setDraftPart(emptyPartDraft(order.make));
                          setItemEditorOpen(true);
                        }}
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
                              if (draftItem.id === item.id) {
                                setDraftItem(emptyItem());
                                setDraftPart(emptyPartDraft(order.make));
                                setItemEditorOpen(false);
                              }
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
                  <p className="mt-1 text-xs text-muted">
                    Worked
                    {item.worked_minutes
                      ? ` · ${formatWorkedMinutes(item.worked_minutes)}`
                      : " · 0m"}
                    {item.worked_first_at
                      ? ` · first ${formatShopTime(item.worked_first_at)}`
                      : ""}
                    {item.worked_last_at
                      ? ` · last ${formatShopTime(item.worked_last_at)}`
                      : ""}
                    {item.timer_started_at ? " · timer running" : ""}
                    {breakdown.length
                      ? ` · ${breakdown
                          .map((t) => `${t.name} ${formatWorkedMinutes(t.minutes)}`)
                          .join(", ")}`
                      : ""}
                  </p>
                  {(() => {
                    const st = (item.status || "").toLowerCase();
                    const totals = item.stage_totals || {};
                    const bits: string[] = [];
                    if (st === "waiting_parts" || st === "waiting_customer") {
                      if (item.stage_entered_at) {
                        const started = Date.parse(item.stage_entered_at);
                        if (!Number.isNaN(started)) {
                          const live = Math.max(
                            0,
                            Math.round((Date.now() - started) / 60000),
                          );
                          if (live > 0) bits.push(`waiting ${formatDurationMinutes(live)}`);
                        }
                      }
                    }
                    const parts = Number(totals.waiting_parts_minutes) || 0;
                    const cust = Number(totals.waiting_customer_minutes) || 0;
                    if (parts > 0) bits.push(`parts wait ${formatDurationMinutes(parts)}`);
                    if (cust > 0) bits.push(`customer wait ${formatDurationMinutes(cust)}`);
                    return bits.length ? (
                      <p className="mt-0.5 text-xs text-muted">{bits.join(" · ")}</p>
                    ) : null;
                  })()}
                  {formatRoleWho(item.created_by, item.created_by_role) ? (
                    <p className="mt-1 text-xs text-muted">
                      Concern entered by {formatRoleWho(item.created_by, item.created_by_role)}
                    </p>
                  ) : null}
                  {item.notes ? (
                    <p className="mt-2 whitespace-pre-wrap text-muted">
                      <span className="text-xs uppercase tracking-wide">
                        Notes
                        {item.notes_by || item.assigned_to_name
                          ? ` · ${item.notes_by || item.assigned_to_name}`
                          : ""}{" "}
                        ·{" "}
                      </span>
                      {item.notes}
                    </p>
                  ) : null}
                  {(item.private_notes || "").trim() ? (
                    <p className="mt-2 whitespace-pre-wrap text-xs text-amber-800 dark:text-amber-200">
                      <span className="uppercase tracking-wide">Private · </span>
                      {item.private_notes}
                    </p>
                  ) : null}
                  {(item.parts || []).length ? (
                    <ul className="mt-2 space-y-1 text-xs text-muted">
                      {(item.parts || []).map((p) => (
                        <li key={p.id}>
                          {p.description || "—"} · {partStatusLabel(p.status)}
                          {p.part_number ? ` · PN ${p.part_number}` : ""}
                          {p.manufacturer ? ` · ${p.manufacturer}` : ""}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}

        {bayItemId ? (
          <div className="space-y-3 rounded-xl border border-accent/40 bg-bg/50 p-4">
            {(() => {
              const bayItem = (order.work_items || []).find((w) => w.id === bayItemId);
              if (!bayItem) {
                return <p className="text-sm text-muted">Work item {bayItemId} not found.</p>;
              }
              return (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-xs font-medium uppercase tracking-wide text-accent">
                        Working on {bayItem.id}
                      </div>
                      <p className="mt-0.5 text-sm">{bayItem.concern || "—"}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant={bayFocus === "notes" ? "default" : "secondary"}
                        onClick={() => setBayFocus("notes")}
                      >
                        Notes
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant={bayFocus === "parts" ? "default" : "secondary"}
                        onClick={() => setBayFocus("parts")}
                      >
                        Parts
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => closeBay()}
                      >
                        Close panel
                      </Button>
                    </div>
                  </div>

                  {bayFocus === "notes" ? (
                    <div className="space-y-3">
                      <Field label="Diagnosis / technician notes (customer PDF)">
                        <Textarea
                          value={bayNotes}
                          onChange={(e) => setBayNotes(e.target.value)}
                          placeholder="Findings while working…"
                        />
                      </Field>
                      <Field label="Private shop notes (techs only — never on customer PDF)">
                        <Textarea
                          value={bayPrivateNotes}
                          onChange={(e) => setBayPrivateNotes(e.target.value)}
                          placeholder="Internal tips, gotchas…"
                        />
                      </Field>
                      <Button
                        type="button"
                        disabled={itemBusy || !order.id}
                        onClick={() =>
                          void (async () => {
                            setItemBusy(true);
                            setErr("");
                            try {
                              const next = await api.upsertWorkItem(order.id, {
                                id: bayItem.id,
                                concern: bayItem.concern,
                                notes: bayNotes,
                                private_notes: bayPrivateNotes,
                                item_type: bayItem.item_type,
                                status: bayItem.status,
                              });
                              setOrder(next);
                              setMsg(`Notes saved on ${bayItem.id}`);
                            } catch (e) {
                              setErr(e instanceof Error ? e.message : "Save notes failed");
                            } finally {
                              setItemBusy(false);
                            }
                          })()
                        }
                      >
                        Save notes
                      </Button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {(bayItem.parts || []).length ? (
                        <ul className="space-y-1 text-xs text-muted">
                          {(bayItem.parts || []).map((p) => (
                            <li key={p.id}>
                              {p.description || "—"} · {partStatusLabel(p.status)}
                              {p.part_number ? ` · PN ${p.part_number}` : ""}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-xs text-muted">No parts yet.</p>
                      )}
                      <Field label="Add part">
                        <Input
                          value={bayPart.description}
                          onChange={(e) =>
                            setBayPart((d) => ({ ...d, description: e.target.value }))
                          }
                          placeholder="Description"
                        />
                      </Field>
                      <div className="grid grid-cols-2 gap-3">
                        <Field label="Part number">
                          <Input
                            value={bayPart.part_number || ""}
                            onChange={(e) =>
                              setBayPart((d) => ({ ...d, part_number: e.target.value }))
                            }
                          />
                        </Field>
                        <Field label="Manufacturer">
                          <Input
                            value={bayPart.manufacturer || ""}
                            onChange={(e) =>
                              setBayPart((d) => ({ ...d, manufacturer: e.target.value }))
                            }
                            placeholder={order.make || ""}
                          />
                        </Field>
                      </div>
                      <Button
                        type="button"
                        disabled={itemBusy || !bayPart.description.trim()}
                        onClick={() =>
                          void (async () => {
                            setItemBusy(true);
                            setErr("");
                            try {
                              const next = await api.addPart(order.id, bayItem.id, {
                                description: bayPart.description,
                                part_number: bayPart.part_number || "",
                                manufacturer: bayPart.manufacturer || order.make || "",
                              });
                              setOrder(next);
                              setBayPart(emptyPartDraft(order.make));
                              setMsg(`Part added to ${bayItem.id}`);
                            } catch (e) {
                              setErr(e instanceof Error ? e.message : "Add part failed");
                            } finally {
                              setItemBusy(false);
                            }
                          })()
                        }
                      >
                        Add part
                      </Button>
                    </div>
                  )}
                </>
              );
            })()}
          </div>
        ) : null}

        {itemEditorOpen ? (
        <div className="space-y-3 border-t border-border pt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs font-medium uppercase tracking-wide text-muted">
              {draftItem.id ? `Edit ${draftItem.id}` : "Add work item"}
            </div>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={itemBusy}
              onClick={() => {
                setDraftItem(emptyItem());
                setDraftPart(emptyPartDraft(order.make));
                setItemEditorOpen(false);
              }}
            >
              Cancel
            </Button>
          </div>
          <Field label="Type (required for new items)">
            <select
              className="flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
              value={draftItem.item_type || ""}
              onChange={(e) => setDraftItem((d) => ({ ...d, item_type: e.target.value }))}
            >
              <option value="">Choose type…</option>
              {ITEM_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Customer concern / request">
            <Textarea
              value={draftItem.concern}
              onChange={(e) => setDraftItem((d) => ({ ...d, concern: e.target.value }))}
              placeholder="e.g. Brake noise when cold"
            />
          </Field>
          <Field label="Diagnosis / technician notes (customer PDF)">
            <Textarea
              value={draftItem.notes}
              onChange={(e) => setDraftItem((d) => ({ ...d, notes: e.target.value }))}
              placeholder="Findings for this item"
            />
          </Field>
          <Field label="Private shop notes (techs only — never on customer PDF)">
            <Textarea
              value={draftItem.private_notes || ""}
              onChange={(e) => setDraftItem((d) => ({ ...d, private_notes: e.target.value }))}
              placeholder="Internal notes, tips, gotchas…"
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
          {draftItem.id && me ? (
            <div className="space-y-2 rounded-xl border border-border/80 bg-bg/30 p-3">
              <div className="text-xs font-medium uppercase tracking-wide text-muted">
                Worked time (shop only — not billed hours)
              </div>
              <p className="text-sm text-muted">
                Logged {formatWorkedMinutes(draftItem.worked_minutes || 0)}
                {draftItem.timer_started_at ? " · timer running" : ""}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                {draftItem.timer_started_at ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={itemBusy}
                    onClick={() => void workItemTime(draftItem.id, "stop")}
                  >
                    Stop timer
                  </Button>
                ) : (
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={itemBusy}
                    onClick={() => void workItemTime(draftItem.id, "start")}
                  >
                    Start timer
                  </Button>
                )}
                {[15, 30, 60].map((m) => (
                  <Button
                    key={m}
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={itemBusy}
                    onClick={() => void workItemTime(draftItem.id, "add", m)}
                  >
                    +{m}m
                  </Button>
                ))}
                <Input
                  className="h-8 w-20"
                  inputMode="numeric"
                  value={addMinutes}
                  onChange={(e) => setAddMinutes(e.target.value)}
                  aria-label="Minutes to add"
                />
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={itemBusy || !(Number(addMinutes) > 0)}
                  onClick={() =>
                    void workItemTime(draftItem.id, "add", Math.floor(Number(addMinutes)))
                  }
                >
                  Add minutes
                </Button>
              </div>
              {adminActive ? (
                <div className="mt-3 space-y-2 border-t border-border/60 pt-3">
                  <div className="text-xs font-medium uppercase tracking-wide text-accent">
                    Admin correction
                  </div>
                  <p className="text-xs text-muted">
                    Unlocked admin session — set total, clear, or open{" "}
                    <Link to="/admin" className="text-accent hover:underline">
                      Admin
                    </Link>
                    .
                  </p>
                  <Input
                    className="h-8"
                    value={adminNote}
                    onChange={(e) => setAdminNote(e.target.value)}
                    placeholder="Correction note (optional)"
                  />
                  <div className="flex flex-wrap items-center gap-2">
                    <Input
                      className="h-8 w-24"
                      inputMode="numeric"
                      value={adminSetMinutes}
                      onChange={(e) => setAdminSetMinutes(e.target.value)}
                      placeholder="Total min"
                      aria-label="Set total minutes"
                    />
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={itemBusy || !(Number(adminSetMinutes) >= 0) || adminSetMinutes === ""}
                      onClick={() =>
                        void adminCorrectTime("set", Math.floor(Number(adminSetMinutes)))
                      }
                    >
                      Set total
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="danger"
                      disabled={itemBusy}
                      onClick={() => {
                        if (confirm(`Clear all worked time on ${draftItem.id}?`)) {
                          void adminCorrectTime("clear");
                        }
                      }}
                    >
                      Clear time
                    </Button>
                  </div>
                </div>
              ) : (
                <p className="mt-2 text-xs text-muted">
                  Mistaken clocks? Unlock{" "}
                  <Link to="/admin" className="text-accent hover:underline">
                    Admin
                  </Link>{" "}
                  with the shop admin PIN.
                </p>
              )}
            </div>
          ) : null}
          {draftItem.id && (draftItem.created_by || draftItem.notes_by) ? (
            <p className="text-xs text-muted">
              {draftItem.created_by
                ? `Concern: ${formatRoleWho(draftItem.created_by, draftItem.created_by_role)}. `
                : ""}
              {draftItem.notes_by
                ? `Notes last saved by ${draftItem.notes_by}.`
                : "Notes will stamp you when you save them."}
            </p>
          ) : (
            <p className="text-xs text-muted">
              Saving notes stamps you as the tech who did the repair work on this item.
            </p>
          )}
          {draftItem.id ? (
            <div className="space-y-3 rounded-xl border border-border/80 bg-bg/30 p-3">
              <div className="text-xs font-medium uppercase tracking-wide text-muted">
                Parts for this item
              </div>
              {(draftItem.parts || []).length ? (
                <ul className="space-y-2 text-sm">
                  {(draftItem.parts || []).map((p) => (
                    <li
                      key={p.id}
                      className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-2"
                    >
                      <div>
                        <span className="font-medium">{p.description || "—"}</span>
                        <span className="ml-2 font-mono text-xs text-muted">
                          {p.id} · {partStatusLabel(p.status)}
                        </span>
                        <div className="text-xs text-muted">
                          {p.manufacturer || order.make || "—"}
                          {p.part_number ? ` · PN ${p.part_number}` : ""}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          disabled={itemBusy}
                          onClick={() => setDraftPart({ ...p })}
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
                                const next = await api.deletePart(
                                  order.id,
                                  draftItem.id,
                                  p.id,
                                );
                                setOrder(next);
                                const wi = (next.work_items || []).find(
                                  (w) => w.id === draftItem.id,
                                );
                                if (wi) setDraftItem({ ...wi });
                                setDraftPart(emptyPartDraft(order.make));
                                setMsg(`Removed ${p.id}`);
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
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-muted">No parts yet.</p>
              )}
              <Field label={draftPart.id ? `Edit ${draftPart.id}` : "Add part"}>
                <Input
                  value={draftPart.description}
                  onChange={(e) =>
                    setDraftPart((d) => ({ ...d, description: e.target.value }))
                  }
                  placeholder="Description"
                />
              </Field>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Part number">
                  <Input
                    value={draftPart.part_number || ""}
                    onChange={(e) =>
                      setDraftPart((d) => ({ ...d, part_number: e.target.value }))
                    }
                  />
                </Field>
                <Field label="Manufacturer">
                  <Input
                    value={draftPart.manufacturer || ""}
                    onChange={(e) =>
                      setDraftPart((d) => ({ ...d, manufacturer: e.target.value }))
                    }
                    placeholder={order.make || "Vehicle make"}
                  />
                </Field>
              </div>
              <Field label="Status">
                <select
                  className="flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
                  value={draftPart.status || "new_request"}
                  onChange={(e) =>
                    setDraftPart((d) => ({ ...d, status: e.target.value }))
                  }
                >
                  {PART_STATUSES.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={itemBusy || !draftPart.description.trim()}
                  onClick={() =>
                    void (async () => {
                      setItemBusy(true);
                      setErr("");
                      try {
                        let next: RepairOrder;
                        if (!draftPart.id) {
                          next = await api.addPart(order.id, draftItem.id, {
                            description: draftPart.description,
                            part_number: draftPart.part_number || "",
                            manufacturer: draftPart.manufacturer || order.make || "",
                          });
                          const added = (next.work_items || [])
                            .find((w) => w.id === draftItem.id)
                            ?.parts?.slice(-1)[0];
                          if (
                            added &&
                            draftPart.status &&
                            draftPart.status !== "new_request"
                          ) {
                            next = await api.patchPart(
                              order.id,
                              draftItem.id,
                              added.id,
                              { status: draftPart.status },
                            );
                          }
                        } else {
                          next = await api.patchPart(
                            order.id,
                            draftItem.id,
                            draftPart.id,
                            {
                              description: draftPart.description,
                              part_number: draftPart.part_number || "",
                              manufacturer: draftPart.manufacturer || order.make || "",
                              status: draftPart.status,
                              wrong_note:
                                draftPart.status === "received_wrong"
                                  ? window.prompt(
                                      "What was wrong?",
                                      "Received wrong part",
                                    ) || "Received wrong part"
                                  : undefined,
                            },
                          );
                        }
                        setOrder(next);
                        const wi = (next.work_items || []).find(
                          (w) => w.id === draftItem.id,
                        );
                        if (wi) setDraftItem({ ...wi });
                        setDraftPart(emptyPartDraft(order.make));
                        setMsg(draftPart.id ? `Updated part` : "Part added");
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Part save failed");
                      } finally {
                        setItemBusy(false);
                      }
                    })()
                  }
                >
                  {draftPart.id ? "Update part" : "Add part"}
                </Button>
                {draftPart.id ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={itemBusy}
                    onClick={() => setDraftPart(emptyPartDraft(order.make))}
                  >
                    Clear part form
                  </Button>
                ) : null}
              </div>
            </div>
          ) : (
            <p className="text-xs text-muted">
              Save the work item first, then add parts on this card.
            </p>
          )}
          <Button
            type="button"
            disabled={
              itemBusy ||
              !order.id ||
              !draftItem.concern.trim() ||
              (!draftItem.id && !(draftItem.item_type || "").trim())
            }
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
                    private_notes: draftItem.private_notes || "",
                    item_type: draftItem.item_type || undefined,
                    status: draftItem.status,
                  });
                  setOrder(next);
                  setDraftItem(emptyItem());
                  setDraftPart(emptyPartDraft(order.make));
                  setItemEditorOpen(false);
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
        ) : null}
      </section>

      <section className="space-y-4 rounded-2xl border border-border bg-surface p-5">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Found issues
            </h2>
            <p className="mt-1 text-xs text-muted">
              Push a discovery to the advisor for customer approval without leaving your job. Typing
              pauses the work timer and banks as downtime.
            </p>
          </div>
          <Button
            type="button"
            variant="secondary"
            disabled={fiBusy || itemBusy || !order.id || !me}
            onClick={() =>
              void (async () => {
                setFiBusy(true);
                setErr("");
                try {
                  const next = await api.beginFoundIssueCompose(
                    order.id,
                    order.current_item_id || undefined,
                  );
                  setOrder(next);
                  setDraftFi({ description: "", notes: "" });
                  setFiEditorOpen(true);
                  const cur = next.current_item_id || "";
                  if (cur) {
                    const item = (next.work_items || []).find((w) => w.id === cur);
                    setBayItemId(cur);
                    setBayFocus("notes");
                    setBayNotes(item?.notes || "");
                    setBayPrivateNotes(item?.private_notes || "");
                    setBayPart(emptyPartDraft(next.make));
                  }
                  setMsg("Work timer paused — describe the found issue");
                } catch (e) {
                  setErr(e instanceof Error ? e.message : "Could not start found-issue request");
                } finally {
                  setFiBusy(false);
                }
              })()
            }
          >
            New found issue
          </Button>
        </div>

        {(order.found_issues || []).length === 0 ? (
          <p className="text-sm text-muted">No found-issue requests yet.</p>
        ) : (
          <ul className="space-y-3">
            {(order.found_issues || []).map((fi: FoundIssue) => (
              <li
                key={fi.id}
                className="rounded-xl border border-border bg-bg/40 px-4 py-3 text-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="font-mono text-xs text-muted">
                      {fi.id} · {formatStatus(fi.status)}
                      {fi.found_by ? ` · ${fi.found_by}` : ""}
                      {fi.work_item_id ? ` → ${fi.work_item_id}` : ""}
                    </div>
                    <p className="mt-1 whitespace-pre-wrap">{fi.description}</p>
                    {(fi.notes || "").trim() ? (
                      <p className="mt-1 text-xs text-muted">{fi.notes}</p>
                    ) : null}
                  </div>
                  {me && fi.status === "pending" ? (
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        size="sm"
                        disabled={fiBusy}
                        onClick={() =>
                          void (async () => {
                            setFiBusy(true);
                            setErr("");
                            try {
                              const next = await api.approveFoundIssue(order.id, fi.id, "repair");
                              setOrder(next);
                              setMsg(`Approved ${fi.id} → new work item`);
                            } catch (e) {
                              setErr(e instanceof Error ? e.message : "Approve failed");
                            } finally {
                              setFiBusy(false);
                            }
                          })()
                        }
                      >
                        Approve → work item
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        disabled={fiBusy}
                        onClick={() =>
                          void (async () => {
                            setFiBusy(true);
                            setErr("");
                            try {
                              const next = await api.declineFoundIssue(order.id, fi.id);
                              setOrder(next);
                              setMsg(`Declined ${fi.id}`);
                            } catch (e) {
                              setErr(e instanceof Error ? e.message : "Decline failed");
                            } finally {
                              setFiBusy(false);
                            }
                          })()
                        }
                      >
                        Decline
                      </Button>
                    </div>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}

        {fiEditorOpen ? (
          <div className="space-y-3 border-t border-border pt-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-xs font-medium uppercase tracking-wide text-muted">
                New found-issue request
              </div>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={fiBusy}
                onClick={() =>
                  void (async () => {
                    setFiBusy(true);
                    setErr("");
                    try {
                      const next = await api.cancelFoundIssueCompose(
                        order.id,
                        order.current_item_id || undefined,
                      );
                      setOrder(next);
                      setFiEditorOpen(false);
                      setDraftFi({ description: "", notes: "" });
                      setMsg("Cancelled — work timer resumed");
                    } catch (e) {
                      setErr(e instanceof Error ? e.message : "Cancel failed");
                    } finally {
                      setFiBusy(false);
                    }
                  })()
                }
              >
                Cancel
              </Button>
            </div>
            <Field label="What did you find?">
              <Textarea
                value={draftFi.description}
                onChange={(e) => setDraftFi((d) => ({ ...d, description: e.target.value }))}
                placeholder="e.g. Inner CV boot torn, grease on axle"
              />
            </Field>
            <Field label="Shop notes for advisor (optional)">
              <Textarea
                value={draftFi.notes}
                onChange={(e) => setDraftFi((d) => ({ ...d, notes: e.target.value }))}
                placeholder="Context for the advisor — not customer-facing until approved"
              />
            </Field>
            <Button
              type="button"
              disabled={fiBusy || !draftFi.description.trim()}
              onClick={() =>
                void (async () => {
                  setFiBusy(true);
                  setErr("");
                  try {
                    const next = await api.createFoundIssue(order.id, {
                      description: draftFi.description,
                      notes: draftFi.notes,
                      source_work_item_id: order.current_item_id || undefined,
                      finish_compose: true,
                    });
                    setOrder(next);
                    setFiEditorOpen(false);
                    setDraftFi({ description: "", notes: "" });
                    setMsg("Found issue sent to advisor — work timer resumed");
                  } catch (e) {
                    setErr(e instanceof Error ? e.message : "Could not send found issue");
                  } finally {
                    setFiBusy(false);
                  }
                })()
              }
            >
              {fiBusy ? "Sending…" : "Send to advisor"}
            </Button>
          </div>
        ) : null}
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
