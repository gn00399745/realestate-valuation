/* 不動產估價工具箱 service worker
   - 網頁本體：網路優先，離線時用快取
   - data/*.json：先回快取、背景更新（資料每旬更新一次）
   - 字型：快取優先 */
const VERSION = "rev-v1";
const SHELL = ["./", "index.html", "manifest.webmanifest",
  "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png", "icons/favicon-64.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (url.origin === location.origin && url.pathname.includes("/data/")) {
    e.respondWith(caches.open(VERSION).then(async c => {
      const hit = await c.match(req);
      const net = fetch(req).then(r => { if (r.ok) c.put(req, r.clone()); return r; }).catch(() => hit);
      return hit || net;
    }));
    return;
  }
  if (url.hostname.endsWith("fonts.googleapis.com") || url.hostname.endsWith("fonts.gstatic.com")) {
    e.respondWith(caches.open(VERSION).then(async c => (await c.match(req)) ||
      fetch(req).then(r => { c.put(req, r.clone()); return r; })));
    return;
  }
  if (url.origin === location.origin) {
    e.respondWith(fetch(req).then(r => {
      if (r.ok) caches.open(VERSION).then(c => c.put(req, r.clone()));
      return r;
    }).catch(() => caches.match(req).then(h => h || caches.match("index.html"))));
  }
});
