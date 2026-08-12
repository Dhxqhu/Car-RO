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
