/* Atlas World service worker.
 * Versioned cache so a new sw.js replaces old caches.
 * HTML and JSON: network first (updates still arrive), cache fallback when offline.
 * Other same-origin assets (covers, scripts, manifest): stale-while-revalidate.
 * Pages are cached when visited, not precached in full.
 */
const VERSION = "v1";
const CACHE_NAME = "atlas-world-" + VERSION;

self.addEventListener("install", function (event) {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(["./", "./404.html", "./manifest.webmanifest"]).catch(function () {
        /* first visit may run before those are available; ignore */
      });
    })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys
          .filter(function (k) {
            return k.indexOf("atlas-world-") === 0 && k !== CACHE_NAME;
          })
          .map(function (k) {
            return caches.delete(k);
          })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

function inScope(url) {
  try {
    return url.origin === self.location.origin && url.href.indexOf(self.registration.scope) === 0;
  } catch (e) {
    return false;
  }
}

function isDocument(request, url) {
  if (request.mode === "navigate") return true;
  var accept = request.headers.get("accept") || "";
  if (accept.indexOf("text/html") !== -1) return true;
  var path = url.pathname;
  return /\/$/.test(path) || /\.html$/i.test(path) || /\.json$/i.test(path) || /\.webmanifest$/i.test(path);
}

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") return;
  var url;
  try {
    url = new URL(request.url);
  } catch (e) {
    return;
  }
  if (!inScope(url)) return;

  if (isDocument(request, url)) {
    event.respondWith(networkFirst(request));
    return;
  }
  event.respondWith(staleWhileRevalidate(request));
});

function networkFirst(request) {
  return caches.open(CACHE_NAME).then(function (cache) {
    return fetch(request)
      .then(function (response) {
        if (response && response.ok) cache.put(request, response.clone());
        return response;
      })
      .catch(function () {
        return cache.match(request).then(function (cached) {
          if (cached) return cached;
          if (request.mode === "navigate") {
            return cache.match(new URL("404.html", self.registration.scope));
          }
          return Promise.reject(new Error("offline"));
        });
      });
  });
}

function staleWhileRevalidate(request) {
  return caches.open(CACHE_NAME).then(function (cache) {
    return cache.match(request).then(function (cached) {
      var fetching = fetch(request)
        .then(function (response) {
          if (response && response.ok) cache.put(request, response.clone());
          return response;
        })
        .catch(function () {
          return cached;
        });
      return cached || fetching;
    });
  });
}
