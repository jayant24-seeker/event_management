// Service worker: makes the site installable and keeps tickets readable with no signal
// (at the gate, in a crowd). Pages are always fetched fresh when online.
const VERSION = "v3";
const SHELL = `eventouse-shell-${VERSION}`;
const PAGES = "eventouse-pages"; // account ticket pages the person opened; cleared on sign-out (site.js)
const PASSES = "eventouse-passes"; // single tickets sent to someone (/pass/...); no account, so kept
const OFFLINE = "/offline";

self.addEventListener("install", (ev) => {
  ev.waitUntil(caches.open(SHELL).then((c) => c.addAll([OFFLINE, "/static/icons/icon-192.png"])).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (ev) => {
  ev.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith("eventouse-shell-") && k !== SHELL).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

const isPass = (url) => url.pathname.startsWith("/pass/");
const isTicketPage = (url) => url.pathname.startsWith("/bookings/") || url.pathname === "/tickets";

self.addEventListener("fetch", (ev) => {
  const req = ev.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;

  if (req.mode === "navigate") {
    ev.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok && !res.redirected && (isTicketPage(url) || isPass(url))) {
            const copy = res.clone();
            caches.open(isPass(url) ? PASSES : PAGES).then((c) => c.put(url.pathname, copy));
          }
          return res;
        })
        .catch(async () => (await caches.match(url.pathname, { cacheName: isPass(url) ? PASSES : PAGES })) || caches.match(OFFLINE))
    );
    return;
  }

  // Static files carry ?v=<version>, so a cached copy is always the right one.
  if (url.pathname.startsWith("/static/")) {
    ev.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(SHELL).then((c) => c.put(req, copy));
        }
        return res;
      }))
    );
  }
});
