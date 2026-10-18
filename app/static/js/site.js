// Small things every page needs: close open menus on outside click or Esc,
// and move events saved as a guest into the account after sign-in.
(function () {
  const menus = [...document.querySelectorAll("details[data-menu]")];
  document.addEventListener("click", (ev) => menus.forEach((m) => { if (m.open && !m.contains(ev.target)) m.open = false; }));
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") menus.forEach((m) => { m.open = false; }); });

  // Light/dark switch. With nothing saved the site follows the phone or computer setting. A choice is
  // kept on this device; picking the device's own theme again, or the device switching theme, clears it.
  const THEME = "eventouse:theme";
  const html = document.documentElement;
  const deviceDark = matchMedia("(prefers-color-scheme: dark)");
  const themeMetas = [...document.querySelectorAll('meta[name="theme-color"]')];
  themeMetas.forEach((m) => { m.dataset.default = m.content; });
  const deviceTheme = () => (deviceDark.matches ? "dark" : "light");
  const setTheme = (theme) => {
    if (theme && theme !== deviceTheme()) {
      html.dataset.theme = theme;
      try { localStorage.setItem(THEME, theme); } catch {}
    } else {
      delete html.dataset.theme;
      try { localStorage.removeItem(THEME); } catch {}
    }
    const now = html.dataset.theme || deviceTheme();
    themeMetas.forEach((m) => { m.content = html.dataset.theme ? (now === "dark" ? "#120D18" : "#FFF8F0") : m.dataset.default; });
    document.querySelectorAll("[data-theme-toggle]").forEach((b) => {
      b.setAttribute("aria-label", now === "dark" ? b.dataset.labelLight : b.dataset.labelDark);
      b.title = b.getAttribute("aria-label");
    });
  };
  setTheme(html.dataset.theme);
  document.addEventListener("click", (ev) => {
    if (!ev.target.closest("[data-theme-toggle]")) return;
    const next = (html.dataset.theme || deviceTheme()) === "dark" ? "light" : "dark";
    const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (document.startViewTransition && !calm) document.startViewTransition(() => setTheme(next));
    else setTheme(next);
  });
  deviceDark.addEventListener("change", () => setTheme(null));

  // Toasts: dismiss on tap, and on their own after 6 seconds (longer messages get a bit more time).
  document.querySelectorAll("[data-toasts] .toast").forEach((t) => {
    const leave = () => { t.classList.add("is-leaving"); setTimeout(() => t.remove(), 260); };
    t.querySelector("[data-toast-close]")?.addEventListener("click", leave);
    setTimeout(leave, 6000 + t.textContent.length * 30);
  });

  // Confirm before destructive actions: <form data-confirm="..."> or <button data-confirm="...">.
  document.addEventListener("submit", (ev) => {
    const msg = ev.submitter?.dataset.confirm || ev.target.dataset.confirm;
    if (msg && !confirm(msg)) ev.preventDefault();
  });
  document.addEventListener("click", async (ev) => {
    const copy = ev.target.closest("[data-copy]");
    if (copy) {
      try {
        await navigator.clipboard.writeText(copy.dataset.copy);
        const old = copy.textContent;
        copy.textContent = "Copied";
        setTimeout(() => { copy.textContent = old; }, 2000);
      } catch {}
    }
    if (ev.target.closest("[data-print]")) window.print();
    if (ev.target.closest("[data-reload]")) location.reload();
  });

  // One-time code: submit as soon as all 6 digits are in (typed, pasted or filled from the SMS).
  const otp = document.querySelector("[data-otp]");
  otp?.addEventListener("input", () => {
    otp.value = otp.value.replace(/\D/g, "").slice(0, 6);
    if (otp.value.length === 6) otp.form.requestSubmit();
  });

  // Recently viewed events: remembered in this browser only (no account, nothing sent anywhere).
  const RECENT = "eventouse:recent";
  const readRecent = () => { try { return JSON.parse(localStorage.getItem(RECENT)) || []; } catch { return []; } };
  const seen = document.querySelector("[data-recent]");
  if (seen) {
    try {
      const item = JSON.parse(seen.dataset.recent);
      const list = [item, ...readRecent().filter((r) => r.slug !== item.slug)].slice(0, 10);
      localStorage.setItem(RECENT, JSON.stringify(list));
    } catch {}
  }
  const row = document.querySelector("[data-recent-row]");
  if (row) {
    const items = readRecent().filter((r) => new Date(r.end) > new Date()).slice(0, 8);
    const box = row.querySelector("[data-recent-list]");
    items.forEach((r) => {
      const a = document.createElement("a");
      a.href = r.url;
      a.className = "flex w-64 shrink-0 snap-start items-center gap-3 rounded-card border border-line bg-paper-raised p-2.5 transition hover:-translate-y-0.5 hover:shadow-poster";
      const img = document.createElement("img");
      img.src = r.poster; img.alt = ""; img.loading = "lazy";
      img.className = "h-16 w-12 shrink-0 rounded-lg object-cover"; img.style.backgroundColor = r.tint;
      const text = document.createElement("span");
      text.className = "min-w-0";
      const t = document.createElement("span"); t.className = "block truncate font-semibold"; t.textContent = r.title;
      const m = document.createElement("span"); m.className = "block text-sm text-ink-soft"; m.textContent = `${r.when} · ${r.city}`;
      text.append(t, m); a.append(img, text); box.append(a);
    });
    row.hidden = items.length === 0;
  }

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
