export type RoEvent = {
  id?: number;
  at?: string;
  type: string;
  ro_id?: string;
  item_id?: string;
  actor?: string;
  actor_id?: string;
  summary?: string;
  payload?: Record<string, string | undefined>;
};

export function isSelfEvent(
  event: RoEvent,
  self?: { name?: string | null; id?: string | null } | null,
): boolean {
  if (!self) return false;
  const name = (self.name || "").trim().toLowerCase();
  const id = (self.id || "").trim().toLowerCase();
  const actorId = String(
    event.actor_id || event.payload?.actor_id || event.payload?.from_id || "",
  )
    .trim()
    .toLowerCase();
  if (id && actorId && actorId === id) return true;
  const actor = (event.actor || "").trim().toLowerCase();
  return Boolean(name && actor && actor === name);
}

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
  if (myName && summary) {
    if (summary === myName) return true;
    if (summary.includes(`· ${myName} ·`) || summary.startsWith(`${myName} ·`)) return true;
    if (!summary.includes("·") && summary.includes(myName)) return true;
  }
  return Boolean(myId && summary && summary === myId);
}

export function filterTechEvents(
  events: RoEvent[],
  self?: { name?: string | null; id?: string | null } | null,
): RoEvent[] {
  return events.filter((e) => {
    if (isSelfEvent(e, self)) return false;
    if (e.type === "shop_message") {
      const myId = (self?.id || "").trim().toLowerCase();
      const toId = String(e.payload?.to_id || "").trim().toLowerCase();
      const fromId = String(e.payload?.from_id || e.payload?.actor_id || "").trim().toLowerCase();
      if (fromId && fromId === myId) return false;
      return Boolean(myId && toId && toId === myId);
    }
    if (e.type === "item_assigned" || e.type === "ro_assigned" || e.type === "item_due_eod") {
      return assignmentTargetsSelf(e, self);
    }
    if (e.type === "next_day_approved" || e.type === "next_day_declined") {
      const myId = (self?.id || "").trim().toLowerCase();
      const byId = String(
        e.payload?.requested_by_id || e.payload?.by_id || e.payload?.to_id || "",
      )
        .trim()
        .toLowerCase();
      if (myId && byId && byId === myId) return true;
      return assignmentTargetsSelf(e, self);
    }
    if (e.type === "item_wait_cleared" || e.type === "item_ready_for_work") {
      const payload = e.payload || {};
      if (!String(payload.assigned_to_id || "").trim() && !String(payload.assigned_to_name || "").trim()) {
        return false;
      }
      return assignmentTargetsSelf(e, self);
    }
    return false;
  });
}

const ADVISOR_TYPES = new Set([
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

export function filterAdvisorEvents(
  events: RoEvent[],
  self?: { name?: string | null; id?: string | null } | null,
): RoEvent[] {
  return events.filter((e) => {
    if (e.type === "ro_created") return false;
    if (!ADVISOR_TYPES.has(e.type)) return false;
    if (e.type === "shop_message") {
      const myId = (self?.id || "").trim().toLowerCase();
      const toId = String(e.payload?.to_id || "").trim().toLowerCase();
      const fromId = String(e.payload?.from_id || "").trim().toLowerCase();
      if (fromId && fromId === myId) return false;
      return Boolean(myId && toId && toId === myId);
    }
    return !isSelfEvent(e, self);
  });
}

export function eventLabel(type: string): string {
  switch (type) {
    case "item_assigned":
    case "ro_assigned":
      return "Assigned";
    case "item_due_eod":
      return "End of day";
    case "item_wait_cleared":
    case "item_ready_for_work":
      return "Ready for work";
    case "shop_message":
      return "Message";
    case "found_issue_created":
      return "Found issue";
    case "found_issue_approved":
      return "Issue approved";
    case "found_issue_declined":
      return "Issue declined";
    case "ro_approval_requested":
      return "Needs approval";
    case "ro_ready_to_bill":
      return "Ready to bill";
    case "ro_billed_out":
      return "Billed out";
    case "next_day_requested":
      return "Next-day requested";
    case "next_day_approved":
      return "Next-day approved";
    case "next_day_declined":
      return "Next-day declined";
    case "ro_waiting_parts":
    case "ro_parts_requested":
      return "Parts";
    case "item_status_changed":
    case "ro_status_changed":
      return "Status";
    default:
      return type.replace(/_/g, " ");
  }
}

export function eventHref(e: RoEvent): string {
  if (e.type === "shop_message") return "/messages";
  const id = String(e.ro_id || "").trim();
  if (id && id !== "_message" && id !== "_shift") return `/ro/${id}`;
  return "/";
}
