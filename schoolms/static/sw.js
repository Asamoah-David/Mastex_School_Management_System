const CACHE_VERSION = "mastex-v1";
const STATIC_ASSETS = [
  "/static/css/styles.css",
  "/static/css/design-system.css",
  "/static/css/dashboard_enhancements.css",
  "/static/favicon.png",
  "/static/manifest.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  const isStatic = url.pathname.startsWith("/static/");

  if (isStatic) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((resp) => {
        const clone = resp.clone();
        caches.open(CACHE_VERSION).then((cache) => cache.put(request, clone));
        return resp;
      }))
    );
    return;
  }

  if (request.headers.get("accept") && request.headers.get("accept").includes("text/html")) {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match(request).then((cached) =>
          cached || new Response("<h1>Offline</h1><p>You are currently offline. Please check your internet connection.</p>", {
            headers: { "Content-Type": "text/html" },
          })
        )
      )
    );
  }
});
