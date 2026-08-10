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
  waiting_parts: "Waiting on parts",
  done: "Done",
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
