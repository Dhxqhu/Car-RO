/**
 * Per-PC notification preferences (localStorage).
 * Shared by Config → Notifications and the header bell.
 */

export type NotifyPrefs = {
  /** Play chime when something new arrives */
  sound: boolean;
  /**
   * When true (default): shop-wide team/idle feed.
   * When false: desk-ops only (needs assign, waiting parts, completed, billing, etc.).
   */
  globalNotifications: boolean;
  /** RO / work-item updates from others (excludes specialized categories below) */
  teamUpdates: boolean;
  /** Found-issue requests sent for customer approval */
  foundIssues: boolean;
  /** Person-to-person shop messages */
  shopMessages: boolean;
  /** Idle nudge “Needs attention” (threshold is idle_nudge_hours in shop config) */
  idleNudges: boolean;
  /** Waiter / urgent flag events */
  waiterUrgent: boolean;
  /** Tech day start / day end punches */
  punches: boolean;
  /** Next-day request / approve / decline */
  nextDay: boolean;
};

export const NOTIFY_PREFS_CHANGED = "carro-notify-prefs";

const SOUND_KEY = "carro.notifications.sound";
const PREFS_KEY = "carro.notifications.prefs";

export const DEFAULT_NOTIFY_PREFS: NotifyPrefs = {
  sound: true,
  globalNotifications: true,
  teamUpdates: true,
  foundIssues: true,
  shopMessages: true,
  idleNudges: true,
  waiterUrgent: true,
  punches: true,
  nextDay: true,
};

function readOnOff(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(key);
    if (v === "off" || v === "0" || v === "false") return false;
    if (v === "on" || v === "1" || v === "true") return true;
  } catch {
    /* ignore */
  }
  return fallback;
}

export function loadNotifyPrefs(): NotifyPrefs {
  const prefs = { ...DEFAULT_NOTIFY_PREFS };
  prefs.sound = readOnOff(SOUND_KEY, true);
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return prefs;
    const parsed = JSON.parse(raw) as Partial<NotifyPrefs>;
    if (typeof parsed.globalNotifications === "boolean") {
      prefs.globalNotifications = parsed.globalNotifications;
    }
    if (typeof parsed.teamUpdates === "boolean") prefs.teamUpdates = parsed.teamUpdates;
    if (typeof parsed.foundIssues === "boolean") prefs.foundIssues = parsed.foundIssues;
    if (typeof parsed.shopMessages === "boolean") prefs.shopMessages = parsed.shopMessages;
    if (typeof parsed.idleNudges === "boolean") prefs.idleNudges = parsed.idleNudges;
    if (typeof parsed.waiterUrgent === "boolean") prefs.waiterUrgent = parsed.waiterUrgent;
    if (typeof parsed.punches === "boolean") prefs.punches = parsed.punches;
    if (typeof parsed.nextDay === "boolean") prefs.nextDay = parsed.nextDay;
    // Prefer dedicated sound key (bell mute) when present; allow prefs.sound as fallback
    if (localStorage.getItem(SOUND_KEY) == null && typeof parsed.sound === "boolean") {
      prefs.sound = parsed.sound;
    }
  } catch {
    /* keep defaults */
  }
  return prefs;
}

export function saveNotifyPrefs(patch: Partial<NotifyPrefs>): NotifyPrefs {
  const next = { ...loadNotifyPrefs(), ...patch };
  try {
    localStorage.setItem(SOUND_KEY, next.sound ? "on" : "off");
    localStorage.setItem(
      PREFS_KEY,
      JSON.stringify({
        globalNotifications: next.globalNotifications,
        teamUpdates: next.teamUpdates,
        foundIssues: next.foundIssues,
        shopMessages: next.shopMessages,
        idleNudges: next.idleNudges,
        waiterUrgent: next.waiterUrgent,
        punches: next.punches,
        nextDay: next.nextDay,
      }),
    );
    window.dispatchEvent(new CustomEvent(NOTIFY_PREFS_CHANGED, { detail: next }));
  } catch {
    /* private mode / quota */
  }
  return next;
}

/** Which specialized / general bucket an RO event falls into for prefs gating. */
export type NotifyEventBucket =
  | "shopMessages"
  | "waiterUrgent"
  | "punches"
  | "nextDay"
  | "foundIssues"
  | "teamUpdates";

export function eventNotifyBucket(type: string): NotifyEventBucket {
  switch (type) {
    case "shop_message":
      return "shopMessages";
    case "ro_waiter_flag":
    case "ro_urgent_flag":
      return "waiterUrgent";
    case "tech_day_start":
    case "tech_day_end":
      return "punches";
    case "next_day_requested":
    case "next_day_approved":
    case "next_day_declined":
      return "nextDay";
    case "found_issue_created":
    case "found_issue_approved":
    case "found_issue_declined":
      return "foundIssues";
    default:
      return "teamUpdates";
  }
}

export function prefsAllowEvent(prefs: NotifyPrefs, type: string): boolean {
  const bucket = eventNotifyBucket(type);
  return Boolean(prefs[bucket]);
}
