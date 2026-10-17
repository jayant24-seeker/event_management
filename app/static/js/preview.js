// Static preview (GitHub Pages): there's no server, so search, filters and anything that
// needs an account are handled here. Loaded only when the site is built with STATIC_PREVIEW.
(function () {
  const root = document.body.dataset.root || "";
  const json = (path) => fetch(`${root}${path}`).then((r) => r.json());
  let index, pages;
  const getIndex = () => (index ||= json("/preview/search.json"));
  const getPages = () => (pages ||= json("/preview/pages.json"));

  // Search suggestions from a prebuilt index instead of /api/suggest.
  const realFetch = window.fetch.bind(window);
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (u.includes("/api/suggest")) {
      const q = new URL(u, location.href).searchParams.get("q").toLowerCase();
      const data = await getIndex();
      return new Response(JSON.stringify({
        events: data.events.filter((e) => e.text.includes(q)).slice(0, 5),
        cities: data.cities.filter((c) => c.name.toLowerCase().includes(q)),
        categories: data.categories.filter((c) => c.name.toLowerCase().includes(q)),
      }), { headers: { "Content-Type": "application/json" } });
    }
    if (u.includes("/api/")) return new Response("{}", { status: 401 });
    return realFetch(url, opts);
  };

  // Forms: Explore filters go to their prebuilt page (or the closest one); searches filter the
  // Explore grid in the browser; everything else needs the live app.
  const ORDER = ["sort", "price", "date", "q", "category", "city", "view", "month", "when"];
  document.addEventListener("submit", async (ev) => {
    const form = ev.target;
    const action = new URL(form.action || location.href, location.href);
    ev.preventDefault();
    if ((form.method || "get").toLowerCase() !== "get" || !action.pathname.replace(/\/$/, "").endsWith("/events")) {
      location.href = `${root}/preview/`;
      return;
    }
    const params = [...new FormData(form)].filter(([k, v]) => v && k !== "page");
    const q = (params.find(([k]) => k === "q") || [])[1];
    let rest = params.filter(([k]) => k !== "q");
    const map = await getPages();
    const key = (list) => list.map(([k, v]) => [k, v]).sort().map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v).replace(/%20/g, "+")}`).join("&");
    let target = `${root}/events/`;
    while (rest.length) {
      if (map[key(rest)]) { target = map[key(rest)]; break; }
      const drop = ORDER.find((k) => rest.some(([n]) => n === k));
      rest = rest.filter(([n]) => n !== drop);
    }
    location.href = target + (q ? `#q=${encodeURIComponent(q)}` : "");
  }, true);

  // "#q=..." on an Explore page: show only matching events.
  const m = location.hash.match(/^#q=(.+)/);
  if (m) {
    const q = decodeURIComponent(m[1]).toLowerCase();
    const cards = [...document.querySelectorAll("main a[href*='/events/']")].filter((a) => a.querySelector("h3"));
    let shown = 0;
    cards.forEach((a) => { const hit = a.textContent.toLowerCase().includes(q); a.hidden = !hit; shown += hit; });
    const status = document.querySelector("main [role=status]");
    if (status) status.textContent = `${shown} event${shown === 1 ? "" : "s"} for “${decodeURIComponent(m[1])}”`;
    const input = document.querySelector("#explore-q");
    if (input) input.value = decodeURIComponent(m[1]);
  }

  document.querySelector("[data-back]")?.addEventListener("click", () => history.length > 1 ? history.back() : (location.href = `${root}/`));
})();
