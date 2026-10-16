// Explore filters: submit when a dropdown changes (desktop), and open/close the
// filter panel on phones, where people pick several filters and then tap "Show results".
(function () {
  const form = document.querySelector("[data-filters]");
  if (!form) return;
  const panel = form.querySelector("[data-filter-panel]");
  const toggle = form.querySelector("[data-filter-toggle]");
  const wide = matchMedia("(min-width: 1024px)");

  form.querySelectorAll("select").forEach((el) =>
    el.addEventListener("change", () => { if (wide.matches) form.requestSubmit(); })
  );

  toggle?.addEventListener("click", () => {
    const open = toggle.getAttribute("aria-expanded") !== "true";
    toggle.setAttribute("aria-expanded", String(open));
    panel.classList.toggle("hidden", !open);
    panel.classList.toggle("grid", open);
    panel.classList.toggle("grid-cols-2", open);
    panel.classList.toggle("mt-1", open);
  });

  // Don't send empty fields, so URLs stay short and shareable.
  form.addEventListener("submit", () => {
    form.querySelectorAll("input[name], select[name]").forEach((el) => { if (!el.value) el.disabled = true; });
  });
})();
