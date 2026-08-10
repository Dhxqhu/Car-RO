/**
 * Short UI chime for new shop notifications (messages / team updates / idle).
 * Uses Web Audio so we don't ship a binary asset; muted until a user gesture
 * unlocks AudioContext (browser autoplay policy).
 *
 * Bursts are coalesced: at most one chime every MIN_GAP_MS (leading + one trailing).
 */

let ctx: AudioContext | null = null;
let unlocked = false;

const MIN_GAP_MS = 2500;
let lastPlayAt = 0;
let trailingTimer: ReturnType<typeof setTimeout> | null = null;
let trailingKind: "message" | "update" = "message";

function getCtx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  const AC =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AC) return null;
  if (!ctx) ctx = new AC();
  return ctx;
}

/** Call from a click/keydown so later chimes are allowed to play. */
export function unlockNotifySound(): void {
  const c = getCtx();
  if (!c) return;
  void c.resume().then(() => {
    unlocked = true;
  });
}

function actuallyPlay(kind: "message" | "update"): void {
  const c = getCtx();
  if (!c) return;
  void c.resume().then(() => {
    unlocked = true;
    const now = c.currentTime;
    const freqs =
      kind === "message"
        ? ([523.25, 659.25, 783.99] as const) // C5 E5 G5
        : ([440, 554.37] as const); // A4 C#5
    freqs.forEach((freq, i) => {
      const osc = c.createOscillator();
      const gain = c.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      const t0 = now + i * 0.07;
      gain.gain.setValueAtTime(0.0001, t0);
      gain.gain.exponentialRampToValueAtTime(0.12, t0 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.28);
      osc.connect(gain);
      gain.connect(c.destination);
      osc.start(t0);
      osc.stop(t0 + 0.3);
    });
  });
}

/**
 * Play a notify chime. Rapid calls within MIN_GAP_MS collapse to one leading
 * tone and at most one trailing tone after the gap (no spam on bursts).
 * Pass `{ force: true }` to bypass coalescing (e.g. Sound on preview).
 */
export function playNotifyChime(
  kind: "message" | "update" = "message",
  opts?: { force?: boolean },
): void {
  if (opts?.force) {
    if (trailingTimer != null) {
      clearTimeout(trailingTimer);
      trailingTimer = null;
    }
    lastPlayAt = Date.now();
    actuallyPlay(kind);
    return;
  }

  const now = Date.now();
  const elapsed = now - lastPlayAt;
  if (elapsed >= MIN_GAP_MS) {
    if (trailingTimer != null) {
      clearTimeout(trailingTimer);
      trailingTimer = null;
    }
    lastPlayAt = now;
    actuallyPlay(kind);
    return;
  }

  // Prefer message tone if any request in the coalesce window is a message
  if (kind === "message") trailingKind = "message";
  else if (trailingTimer == null) trailingKind = kind;

  if (trailingTimer == null) {
    trailingTimer = setTimeout(() => {
      trailingTimer = null;
      lastPlayAt = Date.now();
      actuallyPlay(trailingKind);
      trailingKind = "update";
    }, MIN_GAP_MS - elapsed);
  }
}

export function notifySoundUnlocked(): boolean {
  return unlocked;
}
