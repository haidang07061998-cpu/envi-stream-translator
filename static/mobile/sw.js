/* Service worker toi gian cho PWA Hop En-Vi.
   - Chi cache app shell: /m va /static/mobile/manifest.json (+ icon.svg).
   - TUYET DOI khong cache: /health, /session/, /room/, /ws/, /docs, /openapi.json
     hay bat ky phan hoi API nao.
   - Khong go vao WebSocket: trinh duyet khong gui WS qua fetch handler. */

var CACHE = "envi-shell-v1";
var SHELL = ["/m", "/static/mobile/manifest.json", "/static/mobile/icon.svg"];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (c) {
      // cache.addAll that bai neu 1 URL loi -> them tung cai cho an toan.
      return Promise.all(SHELL.map(function (u) {
        return c.add(new Request(u, { cache: "reload" })).catch(function () {});
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        return k === CACHE ? null : caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

function isShell(url) {
  var p = url.pathname;
  return p === "/m" || p === "/m/" ||
    p === "/static/mobile/manifest.json" ||
    p === "/static/mobile/icon.svg" ||
    p === "/static/mobile/index.html";
}

self.addEventListener("fetch", function (event) {
  var req = event.request;
  if (req.method !== "GET") return;             // POST/DELETE: di thang ra mang

  var url;
  try { url = new URL(req.url); } catch (e) { return; }
  if (url.origin !== self.location.origin) return; // khong dinh gi toi ben ngoai

  // API / realtime: KHONG BAO GIO cache.
  var p = url.pathname;
  if (p.indexOf("/session/") === 0 || p === "/session/create" ||
      p === "/health" || p.indexOf("/ws/") === 0 || p.indexOf("/room/") === 0 ||
      p === "/docs" || p === "/openapi.json" || p.indexOf("/translate") === 0 ||
      p.indexOf("/doctranslate") === 0 || p.indexOf("/summarize") === 0) {
    return;
  }

  if (!isShell(url)) return;

  // App shell: stale-while-revalidate (luon uu tien ban moi khi co mang).
  event.respondWith(
    caches.open(CACHE).then(function (cache) {
      return cache.match(req).then(function (cached) {
        var net = fetch(req).then(function (res) {
          if (res && res.ok && res.type === "basic") cache.put(req, res.clone());
          return res;
        }).catch(function () { return cached; });
        return cached || net;
      });
    })
  );
});
