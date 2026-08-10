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
  return events.filter((e) => !isSelfEvent(e, self));
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
    default:
      return formatLabel(type);
  }
}

/** Event summary with status tokens rendered as UI labels. */
export function formatEventSummary(summary: string | undefined | null): string {
  return formatEmbeddedLabels(summary);
}
