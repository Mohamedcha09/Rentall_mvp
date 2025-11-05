// static/sw.js
const CACHE = "sevor-v4";
const ASSETS = ["/static/style.css"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  const accept = req.headers.get("accept") || "";

  // لا نخزّن صفحات HTML
  if (req.mode === "navigate" || accept.includes("text/html")) {
    e.respondWith(fetch(req).catch(() => caches.match("/offline.html")));
    return;
  }

  // شبكة أول لصور البروفايل (Cloudinary أو مجلد avatars المحلي)
  const isAvatar =
    url.hostname.endsWith("res.cloudinary.com") ||
    url.pathname.startsWith("/uploads/avatars/");

  if (isAvatar) {
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // باقي الملفات: كاش أول مع تحديث بالخلفية
  e.respondWith(
    caches.match(req).then((r) => r || fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy));
      return res;
    }))
  );
});
