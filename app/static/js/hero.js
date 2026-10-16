// Homepage hero slider. The slides are a scroll-snap row (swipe works without JS);
// this adds dots with a progress bar, prev/next, keyboard arrows and autoplay.
(function () {
  const root = document.querySelector("[data-hero]");
  if (!root) return;
  const track = root.querySelector("[data-hero-track]");
  const slides = [...root.querySelectorAll("[data-hero-slide]")];
  const dots = [...root.querySelectorAll("[data-hero-dot]")];
  const bars = [...root.querySelectorAll("[data-hero-bar]")];
  const pauseBtn = root.querySelector("[data-hero-pause]");
  if (slides.length < 2) return;

  const DELAY = 6000;
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let index = 0;
  let userPaused = reduceMotion; // no autoplay for people who asked for less motion
  let focusPaused = false;
  let timer = null;
  let startedAt = 0;
  let elapsed = 0;

  function goTo(i) {
    index = (i + slides.length) % slides.length;
    track.scrollTo({ left: index * track.clientWidth, behavior: reduceMotion ? "auto" : "smooth" });
    mark();
    restart();
  }

  function mark() {
    dots.forEach((d, i) => d.setAttribute("aria-selected", i === index ? "true" : "false"));
    bars.forEach((b, i) => {
      b.style.transition = "none";
      b.style.width = i < index ? "100%" : "0%";
    });
  }

  function running() {
    return !userPaused && !focusPaused && !document.hidden;
  }

  function animateBar(remaining) {
    const bar = bars[index];
    if (!bar) return;
    // Force a reflow so the transition starts from the current width.
    void bar.offsetWidth;
    bar.style.transition = `width ${remaining}ms linear`;
    bar.style.width = "100%";
  }

  function schedule() {
    clearTimeout(timer);
    if (!running()) return;
    const remaining = Math.max(DELAY - elapsed, 0);
    startedAt = performance.now();
    animateBar(remaining);
    timer = setTimeout(() => goTo(index + 1), remaining);
  }

  function hold() {
    clearTimeout(timer);
    elapsed += performance.now() - startedAt;
    const bar = bars[index];
    if (bar) {
      bar.style.transition = "none";
      bar.style.width = `${Math.min(elapsed / DELAY, 1) * 100}%`;
    }
  }

  function restart() {
    elapsed = 0;
    schedule();
  }

  function refresh() {
    running() ? schedule() : hold();
  }

  dots.forEach((d, i) => d.addEventListener("click", () => goTo(i)));
  root.querySelector("[data-hero-prev]")?.addEventListener("click", () => goTo(index - 1));
  root.querySelector("[data-hero-next]")?.addEventListener("click", () => goTo(index + 1));

  pauseBtn?.addEventListener("click", () => {
    userPaused = !userPaused;
    pauseBtn.setAttribute("aria-label", userPaused ? "Play slideshow" : "Pause slideshow");
    pauseBtn.querySelector('[data-icon="pause"]').classList.toggle("hidden", userPaused);
    pauseBtn.querySelector('[data-icon="play"]').classList.toggle("hidden", !userPaused);
    refresh();
  });
  if (userPaused && pauseBtn) {
    pauseBtn.setAttribute("aria-label", "Play slideshow");
    pauseBtn.querySelector('[data-icon="pause"]').classList.add("hidden");
    pauseBtn.querySelector('[data-icon="play"]').classList.remove("hidden");
  }

  // Pause while keyboard focus is inside (the hero fills the screen, so mouse
  // hover would stop it almost always), or while the tab is hidden.
  root.addEventListener("focusin", (ev) => {
    if (ev.target.matches(":focus-visible")) { focusPaused = true; refresh(); }
  });
  root.addEventListener("focusout", (ev) => {
    if (!root.contains(ev.relatedTarget)) { focusPaused = false; refresh(); }
  });
  document.addEventListener("visibilitychange", refresh);

  root.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowRight") goTo(index + 1);
    else if (ev.key === "ArrowLeft") goTo(index - 1);
  });

  // Keep the dots in sync when someone swipes.
  let scrollEnd;
  track.addEventListener("scroll", () => {
    clearTimeout(scrollEnd);
    scrollEnd = setTimeout(() => {
      const i = Math.round(track.scrollLeft / track.clientWidth);
      if (i !== index) { index = i; mark(); restart(); }
    }, 120);
  }, { passive: true });

  window.addEventListener("resize", () => {
    track.scrollTo({ left: index * track.clientWidth, behavior: "auto" });
  });

  mark();
  restart();
})();
