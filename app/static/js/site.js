// Small things every page needs: close open menus on outside click or Esc,
// and move events saved as a guest into the account after sign-in.
(function () {
  const menus = [...document.querySelectorAll("details[data-menu]")];
  document.addEventListener("click", (ev) => menus.forEach((m) => { if (m.open && !m.contains(ev.target)) m.open = false; }));
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") menus.forEach((m) => { m.open = false; }); });

  // Installable app + tickets that open offline. Signed out: forget any saved ticket pages.
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  if (document.body.dataset.auth !== "1") {
    if ("caches" in window) caches.delete("eventouse-pages").catch(() => {});
    return;
  }
  const KEY = "eventouse:saved";
  let guestSaved = [];
  try { guestSaved = JSON.parse(localStorage.getItem(KEY)) || []; } catch {}
  if (!guestSaved.length) return;
  fetch("/api/saved", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content },
    body: JSON.stringify({ slugs: guestSaved, saved: true }),
  }).then((res) => { if (res.ok) { try { localStorage.removeItem(KEY); } catch {} } });
})();
