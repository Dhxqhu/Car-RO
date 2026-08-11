/** Local dismiss / auto-clear helpers for the notification bell (tech + advisor). */

const DISMISS_KEY = "carro.notifications.dismissed";
const MAX_DISMISSED = 400;

export type DismissKind = "ev" | "idle" | "msg";

export function eventDismissKey(id: string | number | undefined | null): string | null {
  if (id == null || id === "") return null;
  return `ev:${id}`;
}

export function idleDismissKey(fingerprint: string | undefined | null): string | null {
  const fp = (fingerprint || "").trim();
  return fp ? `idle:${fp}` : null;
}

export function msgDismissKey(id: string | number | undefined | null): string | null {
  if (id == null || id === "") return null;
  return `msg:${id}`;
}

export function loadDismissed(): Set<string> {
  try {
    const raw = JSON.parse(localStorage.getItem(DISMISS_KEY) || "[]");
    return new Set(Array.isArray(raw) ? raw.map(String) : []);
  } catch {
    return new Set();
  }
}

export function saveDismissed(set: Set<string>) {
  const arr = [...set];
  localStorage.setItem(DISMISS_KEY, JSON.stringify(arr.slice(-MAX_DISMISSED)));
}

export function isDismissed(set: Set<string>, key: string | null | undefined): boolean {
  return !!key && set.has(key);
}

/** Resolving event types that clear an earlier “action needed” notification. */
export function resolvingClearsType(type: string): string | null {
  switch (type) {
    case "found_issue_approved":
    case "found_issue_declined":
      return "found_issue_created";
    case "next_day_approved":
    case "next_day_declined":
      return "next_day_requested";
    default:
      return null;
  }
}

export function sameWorkTarget(
  a: { ro_id?: string; item_id?: string; payload?: Record<string, unknown> | null },
  b: { ro_id?: string; item_id?: string; payload?: Record<string, unknown> | null },
): boolean {
  const aRo = (a.ro_id || "").trim();
  const bRo = (b.ro_id || "").trim();
  if (!aRo || !bRo || aRo !== bRo) return false;
  const aItem = String(a.item_id || a.payload?.item_id || a.payload?.work_item_id || "").trim();
  const bItem = String(b.item_id || b.payload?.item_id || b.payload?.work_item_id || "").trim();
  if (aItem && bItem) return aItem === bItem;
  // found issues often key on issue id in payload
  const aFi = String(a.payload?.found_issue_id || a.payload?.id || "").trim();
  const bFi = String(b.payload?.found_issue_id || b.payload?.id || "").trim();
  if (aFi && bFi) return aFi === bFi;
  return !aItem && !bItem;
}
