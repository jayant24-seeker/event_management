// Small things every page needs: close open menus on outside click or Esc,
// and move events saved as a guest into the account after sign-in.
(function () {
  const menus = [...document.querySelectorAll("details[data-menu]")];
  document.addEventListener("click", (ev) => menus.forEach((m) => { if (m.open && !m.contains(ev.target)) m.open = false; }));
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") menus.forEach((m) => { m.open = false; }); });

  // Confirm before destructive actions: <form data-confirm="..."> or <button data-confirm="...">.
  document.addEventListener("submit", (ev) => {
    const msg = ev.submitter?.dataset.confirm || ev.target.dataset.confirm;
    if (msg && !confirm(msg)) ev.preventDefault();
  });
  document.addEventListener("click", (ev) => {
    if (ev.target.closest("[data-print]")) window.print();
    if (ev.target.closest("[data-reload]")) location.reload();
  });

  // One-time code: submit as soon as all 6 digits are in (typed, pasted or filled from the SMS).
  const otp = document.querySelector("[data-otp]");
  otp?.addEventListener("input", () => {
    otp.value = otp.value.replace(/\D/g, "").slice(0, 6);
    if (otp.value.length === 6) otp.form.requestSubmit();
  });

  // Installable app + tickets that open offline. Signed out: forget any saved ticket pages.
  const root = document.body.dataset.root || "";
  if ("serviceWorker" in navigator && !document.body.dataset.preview) navigator.serviceWorker.register(`${root}/sw.js`).catch(() => {});
  if (document.body.dataset.auth !== "1") {
    if ("caches" in window) caches.delete("eventouse-pages").catch(() => {});
    return;
  }
  const KEY = "eventouse:saved";
  let guestSaved = [];
  try { guestSaved = JSON.parse(localStorage.getItem(KEY)) || []; } catch {}
  if (!guestSaved.length) return;
  fetch(`${root}/api/saved`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content },
    body: JSON.stringify({ slugs: guestSaved, saved: true }),
  }).then((res) => { if (res.ok) { try { localStorage.removeItem(KEY); } catch {} } });
})();
