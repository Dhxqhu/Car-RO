import type { RoEvent } from "@/lib/api";
import { formatEmbeddedLabels, formatLabel } from "@/lib/utils";

/** Open RO editors listen for this and refetch when they have no unsaved draft. */
export const RO_CHANGED_EVENT = "carro:ro-changed";

export function dispatchRoChanged(events: RoEvent[]): void {
  const roIds = [
    ...new Set(
      events
        .map((e) => String(e.ro_id || "").trim())
        .filter((id) => id && id !== "_message" && id !== "_shift"),
    ),
  ];
  if (!roIds.length) return;
  window.dispatchEvent(new CustomEvent(RO_CHANGED_EVENT, { detail: { roIds } }));
}

/** True if this event was created by the signed-in tech/advisor — never notify the maker. */
export function isSelfEvent(
  event: RoEvent,
  self?: { name?: string | null; id?: string | null } | null,
): boolean {
  if (!self) return false;
  const name = (self.name || "").trim().toLowerCase();
  const id = (self.id || "").trim().toLowerCase();
  const actorId = (
    event.actor_id ||
    event.payload?.actor_id ||
    event.payload?.from_id ||
    ""
  )
    .toString()
    .trim()
    .toLowerCase();
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
    // shop_message is personal — only the addressed recipient, never the sender
    if (e.type === "shop_message") {
      const myId = (self?.id || "").trim().toLowerCase();
      if (!myId) return false;
      const toId = String(e.payload?.to_id || "").trim().toLowerCase();
      const fromId = String(
        e.payload?.from_id || e.payload?.actor_id || e.actor_id || "",
      )
        .trim()
        .toLowerCase();
      if (fromId && fromId === myId) return false;
      if (!toId || toId !== myId) return false;
    }
    return true;
  });
}

export type TechNotifyScope = {
  roIds: Set<string>;
  itemIds: Set<string>;
};

function assignmentTargetsSelf(
  event: RoEvent,
  self?: { name?: string | null; id?: string | null } | null,
): boolean {
  if (!self) return false;
  const myId = (self.id || "").trim().toLowerCase();
  const myName = (self.name || "").trim().toLowerCase();
  const payload = event.payload || {};
  const assigneeId = String(
    payload.assigned_to_id || payload.assignee_id || payload.to_id || "",
  )
    .trim()
    .toLowerCase();
  if (myId && assigneeId && assigneeId === myId) return true;
  const assigneeName = String(payload.assigned_to_name || "").trim().toLowerCase();
  if (myName && assigneeName && assigneeName === myName) return true;
  const summary = String(event.summary || "").trim().toLowerCase();
  // Older shop servers only put the assignee name in summary (no payload ids).
  if (myName && summary) {
    if (summary === myName) return true;
    // "Needs done by end of day · Name · concern"
    if (summary.includes(`· ${myName} ·`) || summary.startsWith(`${myName} ·`)) {
      return true;
    }
    if (!summary.includes("·") && summary.includes(myName)) return true;
  }
  if (myId && summary && summary === myId) return true;
  return false;
}

/** Tech bell: messages to me, work assigned to me, or wait cleared back to me. */
export function filterTechRelevantEvents(
  events: RoEvent[],
  self?: { name?: string | null; id?: string | null } | null,
  _scope?: TechNotifyScope | null,
): RoEvent[] {
  return events.filter((e) => {
    if (e.type === "shop_message") {
      const myId = (self?.id || "").trim().toLowerCase();
      if (!myId) return false;
      const toId = String(e.payload?.to_id || "").trim().toLowerCase();
      const fromId = String(
        e.payload?.from_id || e.payload?.actor_id || e.actor_id || "",
      )
        .trim()
        .toLowerCase();
      if (fromId && fromId === myId) return false;
      return Boolean(toId && toId === myId);
    }
    if (e.type === "item_assigned" || e.type === "ro_assigned" || e.type === "item_due_eod") {
      const quiet = String(e.payload?.quiet_tech || "")
        .trim()
        .toLowerCase();
      if (quiet === "1" || quiet === "true" || quiet === "yes") return false;
      return assignmentTargetsSelf(e, self);
    }
    if (e.type === "next_day_approved" || e.type === "next_day_declined") {
      const myId = (self?.id || "").trim().toLowerCase();
      const payload = e.payload || {};
      const byId = String(
        payload.requested_by_id || payload.by_id || payload.to_id || "",
      )
        .trim()
        .toLowerCase();
      if (myId && byId && byId === myId) return true;
      return assignmentTargetsSelf(e, self);
    }
    // Wait cleared (parts received / customer approved) and returned to this tech
    if (e.type === "item_wait_cleared" || e.type === "item_ready_for_work") {
      const payload = e.payload || {};
      const assigneeId = String(payload.assigned_to_id || "").trim();
      const assigneeName = String(payload.assigned_to_name || "").trim();
      // Unassigned pool clears must not ping every tech
      if (!assigneeId && !assigneeName) return false;
      return assignmentTargetsSelf(e, self);
    }
    return false;
  });
}

/** Advisor desk-ops allowlist when global notifications are off. */
export const ADVISOR_DESK_EVENT_TYPES = new Set([
  "item_added",
  "item_assigned",
  "ro_assigned",
  "item_queue_lane",
  "ro_waiting_parts",
  "ro_parts_requested",
  "item_status_changed",
  "ro_ready_to_bill",
  "ro_billed_out",
  "ro_canceled",
  "ro_no_call_no_show",
  "ro_reopened",
  "ro_status_changed",
  "item_merged",
  "item_unmerged",
  "ro_approval_requested",
  "found_issue_created",
  "found_issue_approved",
  "found_issue_declined",
  "next_day_requested",
  "next_day_approved",
  "next_day_declined",
  "ro_waiter_flag",
  "ro_urgent_flag",
  "tech_day_start",
  "tech_day_end",
  "shop_message",
]);

/** Event types that are logged for audit but never shown in the bell. */
export const SILENT_EVENT_TYPES = new Set(["ro_created"]);

export function filterAdvisorDeskEvents(events: RoEvent[]): RoEvent[] {
  return events.filter(
    (e) => ADVISOR_DESK_EVENT_TYPES.has(e.type) && !SILENT_EVENT_TYPES.has(e.type),
  );
}

export function filterSilentEvents(events: RoEvent[]): RoEvent[] {
  return events.filter((e) => !SILENT_EVENT_TYPES.has(e.type));
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
    case "item_merged":
      return "Work items merged";
    case "item_unmerged":
      return "Work items unmerged";
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
    case "day_plan_sent":
      return "Day plan";
    case "day_plan_scheduled":
      return "Day plan scheduled";
    case "item_wait_cleared":
    case "item_ready_for_work":
      return "Ready for work";
    case "item_due_eod":
      return "Needs done by end of day";
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
    case "ro_canceled":
    case "canceled":
      return "Canceled";
    case "ro_no_call_no_show":
    case "no_call_no_show":
      return "No call / no show";
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
