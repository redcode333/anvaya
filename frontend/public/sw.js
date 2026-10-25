// Minimal app-shell cache so the kiosk UI loads without connectivity.
// API calls are never cached here; the offline rule bundle lives in localStorage.
// Bump CACHE whenever shell assets change (v2: new Anvaya logo and icons) so returning users get them.
const CACHE = "anvaya-shell-v2";
const SHELL = ["/", "/index.html", "/brand/favicon.svg", "/brand/anvaya-mark.svg", "/brand/icon-192.png"];
self.addEventListener("install", (e) => { self.skipWaiting(); e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL))); });
self.addEventListener("activate", (e) => e.waitUntil(
  caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())
));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/")) return;
  e.respondWith(
    fetch(e.request).then((res) => { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); return res; })
      .catch(() => caches.match(e.request).then((m) => m || caches.match("/index.html")))
  );
});
