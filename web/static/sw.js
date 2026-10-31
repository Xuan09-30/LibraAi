// Project Libra PWA Service Worker (v10.2.5)
const CACHE_NAME = 'libra-pwa-v10.5.2';

const STATIC_ASSETS = [
  '/',
  '/static/index.html',
  '/static/manifest.json',
  '/static/icon.png',
  '/static/three.min.js',
  '/static/html2canvas.min.js',
  '/static/prism.min.js',
  '/static/prism.css',
  '/static/style.css',
  '/static/app.js'
];

// Install: pre-cache all core static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      // Use individual caching so missing single assets don't fail the whole install
      return Promise.allSettled(
        STATIC_ASSETS.map((asset) => cache.add(asset).catch((err) => {
          console.warn(`[PWA SW] Pre-cache warning for ${asset}:`, err);
        }))
      );
    }).then(() => self.skipWaiting())
  );
});

// Activate: purge obsolete caches and claim all open clients immediately
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => {
          console.log(`[PWA SW] Purging old cache: ${key}`);
          return caches.delete(key);
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: Stale-While-Revalidate for static assets, network-first for navigation, bypass APIs
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // 1. Bypass dynamic API routes, WebSockets, auth endpoints, and downloads
  if (
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/ws') ||
    url.pathname.startsWith('/auth/') ||
    url.pathname.startsWith('/docs') ||
    url.pathname.startsWith('/openapi.json')
  ) {
    return;
  }

  // 2. Navigation requests: Network-first with cache fallback
  if (event.request.mode === 'navigate' || (event.request.headers.get('accept') || '').includes('text/html')) {
    event.respondWith(
      fetch(event.request)
        .then((networkResp) => {
          if (networkResp && networkResp.status === 200) {
            const respClone = networkResp.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, respClone));
          }
          return networkResp;
        })
        .catch(() => {
          return caches.match(event.request).then((cached) => {
            return cached || caches.match('/') || caches.match('/static/index.html');
          });
        })
    );
    return;
  }

  // 3. Static assets: Stale-While-Revalidate
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      const fetchPromise = fetch(event.request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseToCache = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseToCache);
            });
          }
          return networkResponse;
        })
        .catch(() => cachedResponse);

      // Return cached version immediately if available, otherwise wait for network
      return cachedResponse || fetchPromise;
    })
  );
});
