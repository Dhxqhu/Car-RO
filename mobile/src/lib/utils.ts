import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const STATUS_LABELS: Record<string, string> = {
  open: "Open",
  assigned: "Assigned",
  in_progress: "In progress",
  waiting_parts: "Waiting on parts",
  waiting_customer: "Awaiting approval",
  done: "Done",
  billed_out: "Billed out",
  canceled: "Canceled",
  no_call_no_show: "No call / no show",
  declined: "Declined",
};

export function formatWorkedMinutes(minutes: number | undefined | null): string {
  const n = Math.max(0, Math.round(Number(minutes) || 0));
  if (n < 60) return `${n}m`;
  const h = Math.floor(n / 60);
  const m = n % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}

export function formatStatus(status: string | undefined | null): string {
  const raw = (status || "").trim();
  if (!raw) return "—";
  return STATUS_LABELS[raw.toLowerCase()] || raw.replace(/_/g, " ");
}

export function vehicleLabel(o: {
  year?: string;
  make?: string;
  model?: string;
}): string {
  return [o.year, o.make, o.model].filter(Boolean).join(" ") || "No vehicle";
}

export function customerLabel(o: {
  first_name?: string;
  last_name?: string;
}): string {
  const name = `${o.last_name || ""}, ${o.first_name || ""}`.replace(/^,\s*|,\s*$/g, "").trim();
  return name || "No customer";
}

export function formatShopTime(iso: string | undefined | null): string {
  const raw = (iso || "").trim();
  if (!raw) return "";
  const m = raw.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/);
  if (m) return `${m[1]} ${m[2]}`;
  return raw.slice(0, 16);
}

/** Compact time for chat rows: today → 14:32, else 08-11. */
export function formatMsgTime(iso: string | undefined | null): string {
  const full = formatShopTime(iso);
  const m = full.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}:\d{2})$/);
  if (!m) return full;
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  if (`${m[1]}-${m[2]}-${m[3]}` === today) return m[4];
  return `${m[2]}-${m[3]}`;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ""}${parts[parts.length - 1][0] || ""}`.toUpperCase();
}
