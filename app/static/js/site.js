// Small things every page needs: close open menus on outside click or Esc,
// and move events saved as a guest into the account after sign-in.
(function () {
  const menus = [...document.querySelectorAll("details[data-menu]")];
  document.addEventListener("click", (ev) => menus.forEach((m) => { if (m.open && !m.contains(ev.target)) m.open = false; }));
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") menus.forEach((m) => { m.open = false; }); });

  // Preview notice (GitHub Pages only): the × hides it on every page from now on.
  document.querySelector("[data-preview-note-close]")?.addEventListener("click", (ev) => {
    ev.currentTarget.closest("[data-preview-note]").remove();
    try { localStorage.setItem("eventouse:preview-note", "hidden"); } catch {}
  });

  const root = document.body.dataset.root || "";
  if (document.body.dataset.auth !== "1") return;
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
