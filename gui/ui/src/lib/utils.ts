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
  declined: "Declined",
};

const PHOTO_TAG_LABELS: Record<string, string> = {
  intake: "Intake",
  diag: "Diagnosis",
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

/** Short shop-only timestamp for efficiency (never on customer PDF). */
export function formatShopTime(iso: string | undefined | null): string {
  const raw = (iso || "").trim();
  if (!raw) return "";
  // Prefer local-ish display from ISO without pulling in a date lib
  const m = raw.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/);
  if (m) return `${m[1]} ${m[2]}`;
  return raw.slice(0, 16);
}

/**
 * Format free-text that may embed snake_case statuses
 * (e.g. notification summaries: "open → in_progress").
 */
export function formatEmbeddedLabels(text: string | undefined | null): string {
  const raw = (text || "").trim();
  if (!raw) return "";
  const keys = Object.keys(STATUS_LABELS).sort((a, b) => b.length - a.length);
  let out = raw;
  for (const key of keys) {
    const re = new RegExp(`\\b${key}\\b`, "gi");
    out = out.replace(re, STATUS_LABELS[key]);
  }
  return out;
}
