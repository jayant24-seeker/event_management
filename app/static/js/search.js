// Live suggestions for every search box marked [data-suggest].
// Arrow keys move through the list, Enter opens the highlighted item, Esc closes it.
(function () {
  const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  document.querySelectorAll("[data-suggest]").forEach((form) => {
    const input = form.querySelector("input[name=q]");
    const list = form.querySelector("[role=listbox]");
    let items = [];
    let active = -1;
    let timer;
    let controller;

    function close() {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      active = -1;
    }

    function highlight(i) {
      items.forEach((el, n) => el.setAttribute("aria-selected", n === i ? "true" : "false"));
      active = i;
      if (i >= 0) {
        input.setAttribute("aria-activedescendant", items[i].id);
        items[i].scrollIntoView({ block: "nearest" });
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    function render(data, q) {
      const row = (url, html, i) =>
        `<a id="${list.id}-${i}" role="option" aria-selected="false" href="${esc(url)}" class="flex items-center gap-3 rounded-xl px-3 py-2 text-sm hover:bg-ink/5 aria-selected:bg-ink/5">${html}</a>`;
      let i = 0;
      let html = "";
      if (data.events.length) {
        html += `<p class="px-3 pb-1 pt-2 text-[11px] font-bold uppercase tracking-wider text-ink-soft">Events</p>`;
        data.events.forEach((e) => {
          html += row(e.url, `<img src="${esc(e.poster)}" alt="" class="h-12 w-9 shrink-0 rounded-md object-cover"><span class="min-w-0"><span class="block truncate font-semibold">${esc(e.title)}</span><span class="block text-xs text-ink-soft">${esc(e.meta)}</span></span>`, i++);
        });
      }
      const groups = [["Cities", data.cities], ["Categories", data.categories]];
      groups.forEach(([label, rows]) => {
        if (!rows.length) return;
        html += `<p class="px-3 pb-1 pt-2 text-[11px] font-bold uppercase tracking-wider text-ink-soft">${label}</p>`;
        rows.forEach((r) => { html += row(r.url, `<span class="font-semibold">${esc(r.name)}</span>`, i++); });
      });
      const all = `${form.action}?q=${encodeURIComponent(q)}`;
      html += row(all, `<span class="text-rani font-semibold">See all results for “${esc(q)}”</span>`, i++);
      list.innerHTML = html;
      items = [...list.querySelectorAll("[role=option]")];
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      highlight(-1);
    }

    async function fetchSuggestions() {
      const q = input.value.trim();
      if (q.length < 2) return close();
      controller?.abort();
      controller = new AbortController();
      try {
        const res = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`, { signal: controller.signal });
        if (!res.ok) return close();
        render(await res.json(), q);
      } catch (err) {
        if (err.name !== "AbortError") close();
      }
    }

    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(fetchSuggestions, 150);
    });
    input.addEventListener("focus", () => { if (items.length && input.value.trim().length >= 2) { list.hidden = false; input.setAttribute("aria-expanded", "true"); } });

    input.addEventListener("keydown", (ev) => {
      if (list.hidden) return;
      if (ev.key === "ArrowDown") { ev.preventDefault(); highlight((active + 1) % items.length); }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); highlight(active <= 0 ? items.length - 1 : active - 1); }
      else if (ev.key === "Enter" && active >= 0) { ev.preventDefault(); window.location = items[active].href; }
      else if (ev.key === "Escape") close();
    });

    document.addEventListener("click", (ev) => { if (!form.contains(ev.target)) close(); });
  });
})();
