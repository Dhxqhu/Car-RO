function urlBase64ToUint8Array(b64: string): Uint8Array {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export function isStandalone(): boolean {
  const nav = navigator as Navigator & { standalone?: boolean };
  if (nav.standalone) return true;
  return window.matchMedia("(display-mode: standalone)").matches;
}

export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export function httpsPwaUrl(): string | null {
  const host = location.hostname;
  if (!host || location.protocol === "https:") return null;
  if (host.endsWith(".ts.net")) return `https://${host}:8443/`;
  return null;
}

export function pushBlockReason(): string | null {
  if (location.protocol !== "https:" && location.hostname !== "localhost") {
    const https = httpsPwaUrl();
    if (location.hostname.endsWith(".ts.net") || location.port === "8787") {
      return https
        ? `Apple blocks notifications on http://. On the shop server run sudo ./scripts/enable-pwa-https.sh then open ${https} and Add to Home Screen from there.`
        : "Apple blocks notifications on http://. Enable Tailscale Serve HTTPS (see docs/SERVER_SETUP.md).";
    }
    return "Notifications need HTTPS. Use the Tailscale HTTPS address, not shop http://.";
  }
  if (!pushSupported()) {
    if (!isStandalone()) {
      return "On iPhone: Add to Home Screen, then open Car-RO from that icon — Safari tabs cannot enable push.";
    }
    return "This browser cannot do Web Push (need iOS 16.4+ / a current Chrome).";
  }
  return null;
}

export async function subscribePush(
  publicKey: string,
): Promise<PushSubscriptionJSON> {
  const perm = await Notification.requestPermission();
  if (perm !== "granted") {
    throw new Error("Notifications were not allowed");
  }
  const reg = await navigator.serviceWorker.ready;
  const existing = await reg.pushManager.getSubscription();
  if (existing) await existing.unsubscribe().catch(() => undefined);
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey) as BufferSource,
  });
  return sub.toJSON();
}

export async function unsubscribePush(): Promise<string> {
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  const endpoint = sub?.endpoint || "";
  if (sub) await sub.unsubscribe();
  return endpoint;
}
