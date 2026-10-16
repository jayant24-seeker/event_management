// Event page: ticket picker with live total, countdown, save, share, copy link,
// section highlighting and the results search on past events.
(function () {
  const inr = (n) => "₹" + n.toLocaleString("en-IN");

  // ---- Ticket picker: total updates live; the button stays off until a ticket is picked.
  const form = document.querySelector("[data-ticket-form]");
  if (form) {
    const tiers = [...form.querySelectorAll("[data-tier]")].filter((t) => t.querySelector("input"));
    const submit = form.querySelector("[data-submit]");
    const update = () => {
      let count = 0;
      let total = 0;
      tiers.forEach((tier) => {
        const input = tier.querySelector("input");
        const max = +input.max;
        const n = Math.min(Math.max(parseInt(input.value, 10) || 0, 0), max);
        input.value = n;
        tier.querySelector('[data-step="-1"]').disabled = n === 0;
        tier.querySelector('[data-step="1"]').disabled = n >= max;
        tier.classList.toggle("border-rani", n > 0);
        tier.classList.toggle("bg-rani/5", n > 0);
        count += n;
        total += n * +tier.dataset.price;
      });
      form.querySelector("[data-count]").textContent = count;
      form.querySelector("[data-total]").textContent = inr(total);
      submit.disabled = count === 0;
      submit.textContent = count === 0 ? "Select tickets to continue" : `Continue · ${inr(total)}`;
    };
    tiers.forEach((tier) => {
      const input = tier.querySelector("input");
      tier.querySelectorAll("[data-step]").forEach((btn) =>
        btn.addEventListener("click", () => {
          input.value = (parseInt(input.value, 10) || 0) + +btn.dataset.step;
          update();
        })
      );
      input.addEventListener("input", update);
    });
    // Only send tiers that were picked, so the next page's URL stays short.
    form.addEventListener("submit", () => tiers.forEach((t) => {
      const input = t.querySelector("input");
      if (+input.value === 0) input.disabled = true;
    }));
    update();
  }

  // ---- Countdown to the start.
  const countdown = document.querySelector("[data-countdown]");
  if (countdown) {
    const target = new Date(countdown.dataset.countdown).getTime();
    const cells = Object.fromEntries([...countdown.querySelectorAll("[data-unit]")].map((el) => [el.dataset.unit, el]));
    const tick = () => {
      let s = Math.max(Math.floor((target - Date.now()) / 1000), 0);
      const parts = { days: Math.floor(s / 86400), hrs: Math.floor((s % 86400) / 3600), min: Math.floor((s % 3600) / 60), sec: s % 60 };
      Object.entries(parts).forEach(([k, v]) => { cells[k].textContent = String(v).padStart(2, "0"); });
      return s > 0;
    };
    if (tick()) setInterval(tick, 1000);
  }

  // ---- Save (kept on this device until accounts arrive).
  const KEY = "eventouse:saved";
  const read = () => { try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch { return []; } };
  const write = (list) => { try { localStorage.setItem(KEY, JSON.stringify(list)); } catch {} };
  document.querySelectorAll("[data-save]").forEach((btn) => {
    const slug = btn.dataset.save;
    const paint = () => {
      const on = read().includes(slug);
      btn.setAttribute("aria-pressed", on);
      btn.querySelector("svg").setAttribute("fill", on ? "currentColor" : "none");
      btn.querySelector("[data-save-label]").textContent = on ? "Saved" : "Save";
    };
    btn.addEventListener("click", () => {
      const list = read();
      write(list.includes(slug) ? list.filter((s) => s !== slug) : [...list, slug]);
      paint();
    });
    paint();
  });

  // ---- Share: the phone's share sheet when there is one, else jump to the share buttons.
  document.querySelectorAll("[data-share]").forEach((link) =>
    link.addEventListener("click", async (ev) => {
      if (!navigator.share) return;
      ev.preventDefault();
      try { await navigator.share({ title: link.dataset.title, url: link.dataset.url }); } catch {}
    })
  );
  document.querySelectorAll("[data-copy]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(btn.dataset.copy);
        const old = btn.textContent;
        btn.textContent = "Link copied";
        setTimeout(() => { btn.textContent = old; }, 2000);
      } catch {}
    })
  );

  // ---- Highlight the section you're reading in the section bar.
  const links = [...document.querySelectorAll("[data-section-link]")];
  const byId = Object.fromEntries(links.map((a) => [a.getAttribute("href").slice(1), a]));
  const seen = new Map();
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((en) => seen.set(en.target.id, en.isIntersecting));
    const current = links.map((a) => a.getAttribute("href").slice(1)).find((id) => seen.get(id));
    links.forEach((a) => a.setAttribute("aria-current", a === byId[current] ? "true" : "false"));
    byId[current]?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, { rootMargin: "-130px 0px -55% 0px" });
  Object.keys(byId).forEach((id) => { const el = document.getElementById(id); if (el) observer.observe(el); });

  // ---- Results: filter finishers by bib or name.
  const results = document.querySelector("[data-results]");
  if (results) {
    const rows = [...results.querySelectorAll("[data-results-row]")];
    const empty = results.querySelector("[data-results-empty]");
    results.querySelector("[data-results-search]").addEventListener("input", (ev) => {
      const q = ev.target.value.trim().toLowerCase();
      let shown = 0;
      rows.forEach((r) => { const hit = r.dataset.resultsRow.includes(q); r.hidden = !hit; shown += hit; });
      empty.classList.toggle("hidden", shown > 0);
    });
  }
})();
