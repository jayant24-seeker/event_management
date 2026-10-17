# Overnight improvements log (branch `auto-improvements`)

Work done on its own branch, one commit per item. `main` and the phase branches are untouched.
Every item keeps `pytest` green. Newest at the bottom.

## How to look at it
    git checkout auto-improvements
    source .venv/bin/activate && flask --app run run --debug

## Backlog (ideas, roughly in order)
- [x] Security pass: OTP rate limits, open redirects, ownership checks
- [x] PWA: web app manifest, offline "My tickets", installable
- [x] Cancel a booking (attendee side) following the refund policy
- [x] Transfer a ticket to someone else
- [x] Follow organizers; "From organizers you follow" on the homepage
- [x] Reviews and ratings on past events
- [x] Calendar (month) view on Explore
- [x] Organizer analytics: sales over time chart, ticket mix, check-in rate
- [x] Site admin: review events, read contact messages
- [ ] Printable / downloadable ticket
- [x] Social share image per event (Open Graph)
- [x] Typo-tolerant search
- [ ] Dark mode
- [x] Accessibility audit and fixes
- [ ] Speed: cache the event list per request burst

## Done
- Security: per-IP limits on sign-in codes, waitlist and contact form; blocked `/\host` open redirect; bad coupon expiry no longer crashes. Ownership checks reviewed (all OK).
- Installable app (PWA): manifest, icons, service worker. Ticket pages you have opened work with no signal; offline page lists them; signing out wipes them. Checked in Chromium with the network switched off.
- Follow organizers: Follow button on organizer and event pages (works without JS), follower count on profile and dashboard, "From organizers you follow" row on the homepage.
- Reviews: people with a confirmed ticket can rate (1-5 stars) and review an event after it ends; edit their own; rating summary with star bars; organizer rating on profile and on their upcoming event pages; demo reviews seeded (also into older dev databases).
- Self-serve cancellation with refunds: rules read from the refund policy text ("Full refund up to 14 days before…", "50% … 7 days") or set by the organizer; booking page shows the exact amount back; vague policies fall back to "contact the organizer". Added an automatic add-missing-columns step so older databases keep working.
- Waitlist texts: when a booking on a sold-out event is cancelled, the first people on the waitlist get an SMS; organizers get a "Text the waitlist" button after adding seats; the list shows who was texted.
- Ticket passes and transfers: every ticket has its own pass page (/pass/<code>) to send on WhatsApp, which also opens offline once viewed; the booker can move a ticket to a new name (new QR, old one stops working) unless the policy says non-transferable. QR codes now scale cleanly.
- Organizer analytics: tickets-per-day bar chart with hover/tap tooltips and a table view, check-in rate, tickets per booking, average ticket, cancellations. Demo sales seeded for three Pink Pace events so the demo dashboard has data (off in tests). Checked no page scrolls sideways at 390px.
- Site admin (/admin, numbers in ADMIN_PHONES; demo 88888 88888): site totals, every event with Feature/Hide, organizer verification, contact inbox with mark-done. Invisible (404) to everyone else.
- Link previews: WhatsApp/Facebook ignore SVG, so each event now has a 1200x630 PNG card (its colours, title, date, price) drawn with Pillow and cached; a site-wide card for every other page. Bundled the Mukta font (OFL). Hindi titles fall back to "<category> in <city>" until the server has libraqm for Devanagari shaping.
- Explore calendar: Grid/Calendar toggle; month grid on tablet+ (times, +N more), day-by-day agenda with posters on phones; filters still apply; multi-day events on each day; months limited to the next two years and marked nofollow.
- Search forgives typos ("jaipr", "marathn", "jodpur") and understands everyday words (marathon→running, navratri→garba, poetry→kavi sammelan, standup→comedy) in Explore and the live suggestions.
- Accessibility: ran axe-core on 17 pages (desktop, phone, signed in/out) and fixed every violation: green "Free"/success colour darkened to 5:1 contrast, low-contrast urgency and CTA text, invalid role on hero slides, skipped heading level on Explore, unlabeled admin column, calendar contrast. All pages now report zero violations.
