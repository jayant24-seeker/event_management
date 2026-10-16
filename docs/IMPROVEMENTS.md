# Overnight improvements log (branch `auto-improvements`)

Work done on its own branch, one commit per item. `main` and the phase branches are untouched.
Every item keeps `pytest` green. Newest at the bottom.

## How to look at it
    git checkout auto-improvements
    source .venv/bin/activate && flask --app run run --debug

## Backlog (ideas, roughly in order)
- [x] Security pass: OTP rate limits, open redirects, ownership checks
- [x] PWA: web app manifest, offline "My tickets", installable
- [ ] Cancel a booking (attendee side) following the refund policy
- [ ] Transfer a ticket to someone else
- [x] Follow organizers; "From organizers you follow" on the homepage
- [ ] Reviews and ratings on past events
- [ ] Calendar (month) view on Explore
- [ ] Organizer analytics: sales over time chart, ticket mix, check-in rate
- [ ] Site admin: review events, read contact messages
- [ ] Printable / downloadable ticket
- [ ] Social share image per event (Open Graph)
- [ ] Typo-tolerant search
- [ ] Dark mode
- [ ] Accessibility audit and fixes
- [ ] Speed: cache the event list per request burst

## Done
- Security: per-IP limits on sign-in codes, waitlist and contact form; blocked `/\host` open redirect; bad coupon expiry no longer crashes. Ownership checks reviewed (all OK).
- Installable app (PWA): manifest, icons, service worker. Ticket pages you have opened work with no signal; offline page lists them; signing out wipes them. Checked in Chromium with the network switched off.
- Follow organizers: Follow button on organizer and event pages (works without JS), follower count on profile and dashboard, "From organizers you follow" row on the homepage.
