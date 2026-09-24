const VERSION = 'd6d3c02acce6fb18';
const SHELL_CACHE = `spun-shell-${VERSION}`;
const DATA_CACHE = `spun-data-${VERSION}`;
const INDEX_URL = "specimens/index.json";
const SHELL = [
  "./",
  "index.html",
  "style.css",
  "app.js",
  "silk.js",
  "core/stage.js",
  "core/instances.js",
  "core/render2d.js",
  "core/overlay.js",
  "core/ui.js",
  "core/settings.js",
  "core/panel.js",
  "core/view.js",
  "core/spiderPose.js",
  "gl/glRenderer.js",
  "gl/shaders.js",
  "gl/sunlit.js",
  "gl/sunlitShaders.js",
  "gl/canopy.js",
  "gl/leafMesh.js",
  "gl/spiders.js",
  "gl/spiderShaders.js",
  "gl/spiderModels.js",
  "manifest.webmanifest",
  "offline.html",
  "icons/favicon.svg",
  "icons/apple-touch-icon.png",
];

const scoped = path => new URL(path, self.registration.scope).href;

self.addEventListener("install", event => {
  event.waitUntil((async () => {
    const shell = await caches.open(SHELL_CACHE);
    await shell.addAll(SHELL.map(scoped));
    const data = await caches.open(DATA_CACHE);
    const response = await fetch(scoped(INDEX_URL), { cache: "no-store" });
    if (!response.ok) throw new Error(`index.json ${response.status}`);
    const index = await response.clone().json();
    await data.put(scoped(INDEX_URL), response);
    const entry = index.specimens.find(specimen => specimen.id === index.defaultSpecimen);
    if (entry) await data.add(scoped(`specimens/${encodeURIComponent(entry.file)}`));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const keep = new Set([SHELL_CACHE, DATA_CACHE]);
    for (const name of await caches.keys()) {
      if (name.startsWith("spun-") && !keep.has(name)) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});

async function navigate(request) {
  try {
    return await fetch(request);
  } catch {
    const index = await caches.match(scoped(INDEX_URL), { cacheName: DATA_CACHE });
    const page = index && await caches.match(scoped("index.html"), { cacheName: SHELL_CACHE });
    return page || await caches.match(scoped("offline.html"), { cacheName: SHELL_CACHE }) || Response.error();
  }
}

async function silk(request) {
  const cache = await caches.open(DATA_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

async function staleWhileRevalidate(request, event) {
  const cache = await caches.open(DATA_CACHE);
  const cached = await cache.match(request);
  const refresh = fetch(request).then(async response => {
    if (response.ok) await cache.put(request, response.clone());
    return response;
  });
  if (cached) {
    event.waitUntil(refresh.catch(() => undefined));
    return cached;
  }
  return refresh;
}

async function shellAsset(request) {
  const cached = await caches.match(request, { cacheName: SHELL_CACHE, ignoreSearch: true });
  return cached || fetch(request);
}

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (request.mode === "navigate") {
    event.respondWith(navigate(request));
    return;
  }
  const path = url.pathname;
  if (path.endsWith(".silk")) event.respondWith(silk(request));
  else if (url.href.split("?")[0] === scoped(INDEX_URL)) event.respondWith(staleWhileRevalidate(request, event));
  else if (SHELL.some(item => scoped(item) === url.href.split("?")[0])) event.respondWith(shellAsset(request));
});
