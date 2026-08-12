/* Network-first shell. API routes are never cached. */
const SHELL = "carro-pwa-v2";

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (
    /^\/(ros|session|people|messages|shifts|assigned|parts|advisor|events|technicians|advisors|health|version|push|u)\b/.test(
      url.pathname,
    )
  ) {
    return;
  }
  event.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(SHELL).then((cache) => cache.put(req, copy)).catch(() => undefined);
        return res;
      })
      .catch(() => caches.match(req)),
  );
});

self.addEventListener("push", (event) => {
  let data = { title: "Car-RO", body: "", url: "/" };
  try {
    if (event.data) data = { ...data, ...event.data.json() };
  } catch {
    try {
      data.body = event.data ? event.data.text() : "";
    } catch {
      /* ignore */
    }
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Car-RO", {
      body: data.body || "Shop update",
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: { url: data.url || "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const dest = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const w of windows) {
        if ("focus" in w) return w.focus();
      }
      return self.clients.openWindow(dest);
    }),
  );
});
