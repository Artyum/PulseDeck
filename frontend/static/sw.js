const CACHE_NAME = "pulsedeck-static-v1";
const OFFLINE_URL = "/offline";
const PRECACHE_URLS = [
  OFFLINE_URL,
  "/static/images/android-chrome-192x192.png",
];

function isSameOrigin(url) {
  return url.origin === self.location.origin;
}

function canCacheResponse(request, response) {
  if (request.method !== "GET") return false;
  let url;
  try {
    url = new URL(request.url);
  } catch (e) {
    return false;
  }
  if (!isSameOrigin(url)) return false;
  if (!url.pathname.startsWith("/static/")) return false;
  if (!response || !response.ok) return false;
  if (response.type !== "basic") return false;
  if (response.headers.get("Set-Cookie")) return false;
  var cc = response.headers.get("Cache-Control") || "";
  if (cc.toLowerCase().includes("no-store")) return false;
  return true;
}

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(PRECACHE_URLS);
    })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys
          .filter(function (key) {
            return key !== CACHE_NAME;
          })
          .map(function (key) {
            return caches.delete(key);
          })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener("fetch", function (event) {
  var request = event.request;

  if (request.method !== "GET") {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(function () {
        return caches.match(OFFLINE_URL).then(function (cached) {
          return cached || Response.error();
        });
      })
    );
    return;
  }

  var url;
  try {
    url = new URL(request.url);
  } catch (e) {
    return;
  }

  if (!isSameOrigin(url) || !url.pathname.startsWith("/static/")) {
    return;
  }

  event.respondWith(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.match(request).then(function (cached) {
        if (cached) return cached;
        return fetch(request).then(function (response) {
          if (canCacheResponse(request, response)) {
            cache.put(request, response.clone());
          }
          return response;
        });
      });
    })
  );
});
