import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Title-case a snake_case / kebab-case / spaced token for UI. */
export function formatLabel(value: string | undefined | null): string {
  const raw = (value || "").trim();
  if (!raw) return "—";
  return raw
    .split(/[_-\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

const STATUS_LABELS: Record<string, string> = {
  open: "Open",
  assigned: "Assigned",
  in_progress: "In progress",
  waiting_parts: "Waiting on parts (advisor)",
  waiting_customer: "Awaiting customer approval",
  done: "Done — ready to bill",
  billed_out: "Billed out",
  canceled: "Canceled",
  no_call_no_show: "No call / no show",
  declined: "Declined",
};

const PHOTO_TAG_LABELS: Record<string, string> = {
  intake: "Intake",
  diag: "Diagnosis",
  found_issue: "Found issue",
  other: "Other",
};

const DATA_SOURCE_LABELS: Record<string, string> = {
  local: "This machine",
  "local+server": "This machine + server",
  server: "Shop server",
};

const PACK_KIND_LABELS: Record<string, string> = {
  text: "Text",
  pdf: "PDF with photos",
  "pdf-lite": "PDF without photos",
};

const UPLOAD_MODE_LABELS: Record<string, string> = {
  phone: "Phone",
  shortcut: "Shortcut",
};

function lookup(map: Record<string, string>, value: string): string | null {
  return map[value.trim().toLowerCase()] ?? map[value.trim()] ?? null;
}

/** Human-readable RO / work-item status. */
export function formatStatus(status: string | undefined | null): string {
  const raw = (status || "").trim();
  if (!raw) return "—";
  return lookup(STATUS_LABELS, raw) ?? formatLabel(raw);
}

/** Photo tag (intake / diag / other). */
export function formatPhotoTag(tag: string | undefined | null): string {
  const raw = (tag || "").trim();
  if (!raw) return "Other";
  return lookup(PHOTO_TAG_LABELS, raw) ?? formatLabel(raw);
}

/** Assigned-board / info source key. */
export function formatDataSource(source: string | undefined | null): string {
  const raw = (source || "").trim();
  if (!raw) return "—";
  return lookup(DATA_SOURCE_LABELS, raw) ?? formatLabel(raw);
}

/** History pack kind. */
export function formatPackKind(kind: string | undefined | null): string {
  const raw = (kind || "").trim();
  if (!raw) return "—";
  return lookup(PACK_KIND_LABELS, raw) ?? formatLabel(raw);
}

/** Phone upload session mode. */
export function formatUploadMode(mode: string | undefined | null): string {
  const raw = (mode || "").trim();
  if (!raw) return "—";
  return lookup(UPLOAD_MODE_LABELS, raw) ?? formatLabel(raw);
}

/** Shop-only worked time (efficiency — not billed hours). */
export function formatWorkedMinutes(minutes: number | undefined | null): string {
  const m = Math.max(0, Math.floor(Number(minutes) || 0));
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const rem = m % 60;
  return rem ? `${h}h ${rem}m` : `${h}h`;
}

/** Wall-clock / stage duration (waiting can be days–weeks). Not worked time. */
export function formatDurationMinutes(minutes: number | undefined | null): string {
  const m = Math.max(0, Math.round(Number(minutes) || 0));
  if (m >= 48 * 60) {
    const days = Math.floor(m / (24 * 60));
    const rem = m % (24 * 60);
    const hours = Math.floor(rem / 60);
    const mins = rem % 60;
    if (hours && mins) return `${days}d ${hours}h ${mins}m`;
    if (hours) return `${days}d ${hours}h`;
    if (mins) return `${days}d ${mins}m`;
    return `${days}d`;
  }
  return formatWorkedMinutes(m);
}

/** Worked minutes as hours with two decimal places (e.g. 1.50h). */
export function formatWorkedHours(minutes: number | undefined | null): string {
  const m = Math.max(0, Number(minutes) || 0);
  return `${(m / 60).toFixed(2)}h`;
}

/** Parse shop ISO (naive local, or UTC/offset) into a Date when possible. */
function parseShopDate(iso: string): Date | null {
  let s = iso.trim();
  if (!s) return null;
  // "+0000" / "-0400" → "+00:00" / "-04:00" for reliable Date parsing
  s = s.replace(/([+-]\d{2})(\d{2})$/, "$1:$2");
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** Short shop-only timestamp for efficiency (never on customer PDF). */
export function formatShopTime(iso: string | undefined | null): string {
  const raw = (iso || "").trim();
  if (!raw) return "";
  // Timezone-aware stamps (e.g. server event UTC) → this PC's local wall clock
  if (/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw)) {
    const d = parseShopDate(raw);
    if (d) {
      return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
    }
  }
  // Prefer local-ish display from ISO without pulling in a date lib
  const m = raw.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/);
  if (m) return `${m[1]} ${m[2]}`;
  return raw.slice(0, 16);
}

/** Compact HH:MM for notification rows. */
export function formatShopClock(iso: string | undefined | null): string {
  const full = formatShopTime(iso);
  const m = full.match(/\b(\d{2}:\d{2})(?:\b|$)/);
  return m ? m[1] : full;
}

/**
 * Format free-text that may embed snake_case tokens
 * (e.g. notification summaries: "open → in_progress", "daily → long_term").
 */
export function formatEmbeddedLabels(text: string | undefined | null): string {
  const raw = (text || "").trim();
  if (!raw) return "";
  const known: Record<string, string> = {
    ...STATUS_LABELS,
    daily: "Today",
    next_day: "Next day",
    long_term: "Long-term",
    new_request: "New request",
    ordered: "Ordered",
    received: "Received",
    received_wrong: "Received wrong",
    draft: "Draft",
    pending: "Pending",
    approved: "Approved",
    declined: "Declined",
  };
  const keys = Object.keys(known).sort((a, b) => b.length - a.length);
  let out = raw;
  for (const key of keys) {
    const re = new RegExp(`\\b${key}\\b`, "gi");
    out = out.replace(re, known[key]);
  }
  // Any remaining snake_case tokens (underscores only) → Title Case words
  out = out.replace(/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/gi, (tok) => formatLabel(tok));
  return out;
}

export function turnOrdinal(n: number): string {
  const v = Math.abs(Math.trunc(n));
  const rem100 = v % 100;
  const rem10 = v % 10;
  const suf =
    rem100 >= 11 && rem100 <= 13
      ? "th"
      : rem10 === 1
        ? "st"
        : rem10 === 2
          ? "nd"
          : rem10 === 3
            ? "rd"
            : "th";
  return `${v}${suf}`;
}

/** Newest RO per car (VIN, then plate, then year/make/model + customer). */
export function latestOrdersPerCar<
  T extends {
    id: string;
    vin?: string;
    plate?: string;
    year?: string;
    make?: string;
    model?: string;
    first_name?: string;
    last_name?: string;
    updated?: string;
    created?: string;
  },
>(orders: T[] | undefined | null): T[] {
  const list = [...(orders || [])].sort((a, b) => {
    const ta = a.updated || a.created || "";
    const tb = b.updated || b.created || "";
    if (ta !== tb) return tb.localeCompare(ta);
    return b.id.localeCompare(a.id);
  });
  const seen = new Set<string>();
  const out: T[] = [];
  for (const o of list) {
    const vin = (o.vin || "").replace(/[^A-Za-z0-9]/g, "").toUpperCase();
    const plate = (o.plate || "").replace(/[^A-Za-z0-9]/g, "").toUpperCase();
    const year = (o.year || "").trim().toLowerCase();
    const make = (o.make || "").trim().toLowerCase();
    const model = (o.model || "").trim().toLowerCase();
    const last = (o.last_name || "").trim().toLowerCase();
    const first = (o.first_name || "").trim().toLowerCase();
    const key = vin
      ? `vin:${vin}`
      : plate
        ? `plate:${plate}`
        : year || make || model
          ? `veh:${year}|${make}|${model}|${last}|${first}`
          : `ro:${o.id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(o);
  }
  return out;
}
