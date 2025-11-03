// static/sw.js
const CACHE = "sevor-v3";
const ASSETS = ["/static/style.css"]; // لا نضع "/"

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting())
  );
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
  const accept = req.headers.get("accept") || "";

  // HTML: شبكة أول — لا نخزّن صفحات HTML لتفادي رجفة المودال
  if (req.mode === "navigate" || accept.includes("text/html")) {
    e.respondWith(fetch(req).catch(() => caches.match("/offline.html")));
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
