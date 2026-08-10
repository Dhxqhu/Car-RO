import type { RoEvent } from "@/lib/api";
import { formatEmbeddedLabels, formatLabel } from "@/lib/utils";

/** True if this event was created by the signed-in tech/advisor — never notify the maker. */
export function isSelfEvent(
  event: RoEvent,
  self?: { name?: string | null; id?: string | null } | null,
): boolean {
  if (!self) return false;
  const name = (self.name || "").trim().toLowerCase();
  const id = (self.id || "").trim().toLowerCase();
  const actorId = (event.actor_id || event.payload?.actor_id || "").toString().trim().toLowerCase();
  if (id && actorId && actorId === id) return true;
  const actor = (event.actor || "").trim().toLowerCase();
  if (name && actor && actor === name) return true;
  return false;
}

export function filterOthersEvents(
  events: RoEvent[],
  self?: { name?: string | null; id?: string | null } | null,
): RoEvent[] {
  return events.filter((e) => {
    if (isSelfEvent(e, self)) return false;
    // shop_message is personal — only ping the addressed recipient
    if (e.type === "shop_message") {
      const toId = String(e.payload?.to_id || "").trim();
      const myId = (self?.id || "").trim();
      if (!toId || !myId || toId !== myId) return false;
    }
    return true;
  });
}

export function eventLabel(type: string): string {
  switch (type) {
    case "item_added":
      return "New work item";
    case "item_concern_updated":
      return "Concern updated";
    case "item_notes_updated":
      return "Notes updated";
    case "item_status_changed":
      return "Status changed";
    case "item_removed":
      return "Work item removed";
    case "ro_vehicle_updated":
      return "Vehicle info updated";
    case "ro_created":
      return "RO created";
    case "photo_added":
      return "Photo added";
    case "ro_assigned":
      return "RO assigned";
    case "item_assigned":
      return "Item assigned";
    case "ro_current_started":
      return "Started working";
    case "ro_current_cleared":
      return "Stopped working";
    case "ro_approval_requested":
      return "Customer approval requested";
    case "ro_parts_requested":
      return "Parts order requested";
    case "ro_ready_to_bill":
      return "Ready to bill";
    case "ro_billed_out":
      return "Billed out";
    case "ro_reopened":
      return "Reopened";
    case "ro_waiting_parts":
      return "Waiting on parts";
    case "ro_status_changed":
      return "Status changed";
    case "found_issue_created":
      return "Found issue reported";
    case "found_issue_approved":
      return "Found issue approved";
    case "found_issue_declined":
      return "Found issue declined";
    case "shop_message":
      return "Shop message";
    case "tech_day_start":
      return "Day start";
    case "tech_day_end":
      return "Day end";
    case "next_day_requested":
      return "Next-day requested";
    case "next_day_approved":
      return "Next-day approved";
    case "next_day_declined":
      return "Next-day declined";
    case "item_queue_lane":
      return "Queue lane changed";
    case "ro_waiter_flag":
      return "Waiter flag";
    case "ro_urgent_flag":
      return "Urgent flag";
    default:
      return formatLabel(type);
  }
}

/** Event summary with status tokens rendered as UI labels. */
export function formatEventSummary(summary: string | undefined | null): string {
  return formatEmbeddedLabels(summary);
}
