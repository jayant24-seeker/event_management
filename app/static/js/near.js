// "Near me": find the closest city with events, entirely on this device. The location
// never leaves the phone; we only navigate to that city's page.
(function () {
  const buttons = document.querySelectorAll("[data-near-me]");
  if (!buttons.length || !("geolocation" in navigator)) return;
  const cities = JSON.parse(buttons[0].dataset.nearMe);  // {name: [lat, lng, url]}
  const km = (a, b) => {
    const r = Math.PI / 180, dLat = (b[0] - a[0]) * r, dLng = (b[1] - a[1]) * r;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.sin(dLng / 2) ** 2;
    return 12742 * Math.asin(Math.sqrt(h));
  };
  buttons.forEach((btn) => {
    btn.hidden = false;
    btn.addEventListener("click", () => {
      const label = btn.querySelector("[data-near-label]");
      const original = label.textContent;
      label.textContent = btn.dataset.finding;
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const here = [pos.coords.latitude, pos.coords.longitude];
          const nearest = Object.values(cities).sort((a, b) => km(here, a) - km(here, b))[0];
          location.href = nearest[2];
        },
        () => { label.textContent = btn.dataset.denied; setTimeout(() => { label.textContent = original; }, 3000); },
        { maximumAge: 60000, timeout: 10000, enableHighAccuracy: false }
      );
    });
  });
})();
