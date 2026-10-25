// Minimal app-shell cache so the kiosk UI loads without connectivity.
// Only same-origin GETs for the app's own files are cached. API answers, document links, job calls and metrics are never
// cached or even touched here (the browser goes straight to the network), and any response marked no-store is not stored.
// The offline rule bundle lives in localStorage.
const CACHE = "anvaya-shell-v2";
const NEVER = ["/api/", "/internal/", "/metrics"];
self.addEventListener("install", (e) => { self.skipWaiting(); e.waitUntil(caches.open(CACHE).then((c) => c.addAll(["/", "/index.html"]))); });
self.addEventListener("activate", (e) => e.waitUntil(
  caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())
));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== self.location.origin || NEVER.some((p) => url.pathname.startsWith(p))) return;
  e.respondWith(
    fetch(e.request).then((res) => {
      const cc = res.headers.get("Cache-Control") || "";
      if (res.ok && res.type === "basic" && !/no-store|private/.test(cc)) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
      return res;
    }).catch(() => caches.match(e.request).then((m) => m || (e.request.mode === "navigate" ? caches.match("/index.html") : Response.error())))
  );
});
