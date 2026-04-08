const CACHE_NAME = 'dup-detector-v2';
const ASSETS = ['/', '/manifest.json'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE_NAME).then((c) => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  // Delete all old caches when new SW activates
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  // Never cache API calls or POST requests
  if (e.request.method !== 'GET') return;
  if (e.request.url.includes('/api/')) return;

  // Network-first for HTML pages, cache-first for static assets
  if (e.request.mode === 'navigate') {
    // HTML pages: always try network first
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
  } else {
    // Static assets: network first, cache fallback
    e.respondWith(
      fetch(e.request).then((r) => {
        const clone = r.clone();
        caches.open(CACHE_NAME).then((c) => c.put(e.request, clone));
        return r;
      }).catch(() => caches.match(e.request))
    );
  }
});
