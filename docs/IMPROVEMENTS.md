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
- [x] Printable / downloadable ticket
- [x] Social share image per event (Open Graph)
- [x] Typo-tolerant search
- [x] Dark mode
- [x] Self-host fonts (faster on slow mobile networks, works offline, no third-party requests)
- [x] Saved events: text when registration is about to close (reopening is covered by the waitlist)
- [x] Optimise uploaded posters (resize + WebP)
- [x] Recurring events / series (weekly classes with many dates)
- [ ] Organizer co-admins (more than one person managing an organizer)
- [x] Razorpay integration path behind settings (replace test payment page)
- [x] Accessibility audit and fixes
- [x] Speed: measured every main page (3-8 queries, under 40 ms); fixed the one N+1
- [x] Organizers: message all attendees (SMS announcement, e.g. venue change)
- [x] Organizers: duplicate an event (next edition in one click)
- [x] Group discount (e.g. 10% off 4+ tickets) set by the organizer
- [x] Booking confirmation by email (console in development)
- [x] "Near me": sort Explore by distance from the visitor
- [x] Waitlist position shown to the person waiting
- [x] README refresh for everything added overnight
- [x] Gate scanner page (camera QR scanning on phones)
- [x] Check-in staff: organizer adds volunteer phone numbers who can scan tickets
- [x] Questions & answers on event pages (attendees ask, organizer answers)
- [x] Dark mode
- [x] Self-host fonts (faster on slow mobile networks, works offline, no third-party requests)
- [x] Saved events: text when registration is about to close (reopening is covered by the waitlist)
- [x] Optimise uploaded posters (resize + WebP)
- [x] Recurring events / series (weekly classes with many dates)
- [ ] Organizer co-admins (more than one person managing an organizer)
- [x] Razorpay integration path behind settings (replace test payment page)

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
- Printable tickets: "Print tickets" button; print layout drops header, footer and buttons, keeps colours and QR codes, never splits a ticket across pages.
- Organizer updates: "Message ticket holders" on the event admin page texts everyone who booked (3 a day max) and pins the update on the event page and on their tickets.
- Duplicate for next year: one click copies an event as a draft 52 weeks later (same weekday), updates the year in the title, resets sales and drops results. Also checked the site in the iPhone simulator (Safari): homepage, event page, calendar agenda all render well.
- Group discounts: organizer sets "N+ tickets → X% off" (2+ tickets, up to 50%); event page advertises it, checkout nudges ("add 1 more for 15% off") and applies whichever of group discount or code saves more.
- Booking confirmations: SMS plus a plain-text email (when, where, one link per ticket, refund policy) as soon as a booking is confirmed; console in development, SMTP via MAIL_* settings in production; never blocks a booking if mail is down.
- Waitlist place: joining shows "#N in line" (joining again keeps your place).
- "Near me" on the homepage and Explore: the browser finds the closest city with events and opens its page. The location is used only on the device (never sent to the server or put in a URL). Permissions-Policy now allows geolocation for this site only.
- Speed: profiled query counts per page; public pages run 3-8 queries. The organizer attendee list ran one query per attendee (~100); now 14, with a test guarding it. Caching the event list is not needed at this size.
- README: new settings (mail, admin, proxy, refunds), new modules and routes, demo admin login.
- Gate scanner (/organizer/scan, "Scan with camera" on the dashboard): live camera QR scanning with big green/amber/red results, vibration, running "X of Y checked in", manual code entry. Uses the browser's BarcodeDetector where available and bundled jsQR (Apache-2.0) on iPhone; decoding verified against a real ticket QR.
- Gate team: organizers add volunteers by phone number on the dashboard; volunteers sign in and get "Scan tickets" in their menu, can check tickets in for that organizer only, and see nothing else (no dashboard, attendee data or editing).
- Questions & answers: signed-in visitors ask on the event page (5 a day); the organizer answers or removes inline, the asker gets an SMS; only answered questions are public; the event admin page flags questions waiting.
- Content-Security-Policy: only our own scripts run (inline ones need a per-request nonce); all inline onclick/onsubmit handlers replaced with data-confirm/data-print/data-reload; search suggestions now escape every value. Verified zero CSP violations across public and organizer pages.
- Homepage polish (design pass 1): "Find your next plan" search card with date shortcuts that show live counts (empty ones hidden); city tiles always on one row on desktop; category chips swipe on phones; fewer all-caps labels; cards and tiles show the poster colour while images load instead of black; shorter hero on phones so search is visible on the first screen (checked on iPhone).
- Event page polish (design pass 2): fixed the organizer card on phones (name and details were squeezed into a one-word column by the new Follow button); removed the all-caps label above every section (the sticky section tabs already name them); kit list uses checkmarks instead of numbers (it is not a sequence); the map box shows the venue name and a pin while the map loads or if it cannot load.
- Public preview on GitHub Pages: tools/build_static.py renders every public page (homepage, Explore with common filters, all events, organizers, cities, info pages, link previews) to static files under the repo path; search and filters work in the browser (static/js/preview.js); sign-in, booking and organizer tools show a "needs the live app" page. A GitHub Actions workflow runs the tests, builds and deploys on every push.
- Sign-in and booking polish (design pass 3): sign-in sits at the top on phones instead of floating mid-screen, shows the event you were booking, drops the "Google sign-in coming soon" promise; the 6-digit code submits itself (works with SMS autofill); the sticky Register bar slides away while the ticket box is on screen.
- Checkout polish: gender and T-shirt size are one-tap pill buttons instead of dropdowns; checkout and payment pages get a minimal "Secure checkout" footer instead of the full site footer, keeping attention on finishing the booking; discount-code placeholder no longer shouts in caps.
- Booking confirmed moment: a one-time confetti burst on the green card right after booking (skipped with reduced motion), an "In N days" countdown pill, no duplicate "You're in" flash; tickets now look like tickets with perforation notches where the QR stub tears off.
- Explore: 24 events per page (no lonely single event on page 2), heading without the redundant caps label.
- My tickets redesign: your next event is a big card with its artwork, an "In N days" countdown and a one-tap "Show tickets"; other upcoming bookings show countdowns instead of a redundant Confirmed badge; a friendly empty state; "You might like" suggestions from the categories and cities you book.
- Phone tab bar: app-style bottom navigation (Home, Explore, Tickets, Saved, Profile/Sign in) with the current tab highlighted and iPhone safe-area padding; hidden on event, checkout, payment and scanner pages that have their own bottom actions.
- Smooth navigation: cross-page View Transitions; tapping an event card makes its poster grow into the event page (poster on desktop, banner on phones); off with reduced motion and wherever a card could appear twice on a page.
- Organizer dashboard: "Needs your attention" list (unanswered questions, unpublished drafts, nearly sold-out events, sold-out events with people waiting) with one-tap actions; revenue and tickets lead as dark tiles, other numbers are quieter; rate limits relaxed in development so testing sign-ins does not lock you out.
- Event form: live preview beside the form (desktop) showing the Explore card as you type (title, date chip, category, city and venue, "From ₹" price) and the chosen poster instantly; group discount moved below the ticket rows; wider layout.
- For organizers page: feature grid rewritten to sell what now exists (gate scanner and team, live sales and to-dos, messaging ticket holders, automatic refunds and waitlists, group discounts, Q&A) with icons instead of 1-6 numbers (the features are not steps).
- Hindi: event page UI now fully switches (breadcrumb, Save/Saved, Start/Finish, prizes heading, countdown units, organizer line with natural Hindi word order, review count, Verified).
- Hindi: checkout fully translated (headings, field labels, gender options shown in Hindi while saving the same values, discount code, totals, buttons).
- Hindi: booking confirmation and payment pages translated.
- Hindi: sign-in, profile, Explore, city, organizer profile, saved, waitlist, ticket pass and 404 pages translated (about 230 phrases in total now).
- "Pick up where you left off": homepage row of events you recently opened (kept in this browser only, finished events dropped).
- Dark mode: follows the phone/computer setting. New always-dark night/day tokens keep hero, footer and dark cards consistent; pages, cards, text and lines swap; pink text gets a lighter tone while pink buttons keep white text at 4.8:1; yellow badges and white buttons keep dark text; QR codes stay on white. axe reports no contrast issues on 10 pages in both themes at phone and desktop widths.
- Honest social proof: event ticket box shows "N booked in the last day" from real bookings, only when there are at least 3.
- Where bookings come from: organizers copy tagged share links (?src=instagram, whatsapp, partner or any word; utm_source works too); bookings remember the source and the event admin page shows bookings and revenue per source. Copy buttons now work on every page.
- Automatic texts: `flask send-reminders` (run hourly) sends "see you tomorrow" with the ticket link the day before, and "how was it?" with the review link 2-72 hours after; each once per booking.
- City pages: "Also within reach" shows upcoming events in nearby cities (within 450 km, nearest first) with "130 km from Jaipur", so small cities never feel empty.
- Printable flyer: "Print a flyer" on the event admin page opens an A4 sheet with the artwork, details and a big QR code to the event page (tagged ?src=flyer so flyer bookings show up in "Where bookings come from").
- Self-hosted fonts: Bricolage Grotesque, Plus Jakarta Sans and Mukta now load from the site (440 KB total, only the subsets a page needs are fetched, the two main ones preloaded). No requests to Google, faster on slow networks, cached by the offline worker; CSP no longer allows Google Fonts.
- Uploaded posters are re-encoded on upload: at most 900x1200 (portrait) WebP, rotated per the camera, photo metadata (incl. GPS) removed, unreadable files rejected with a clear message.
- Saved-event nudges: send-reminders also texts people who saved (but have not booked) an event once, when its registration closes within 48 hours, with spots left and a tagged link.
- Razorpay payments (switch on with PAYMENT_PROVIDER=razorpay and keys): order per booking, Razorpay Checkout on the pay page, server-side signature check, signed webhook as a backup (idempotent), automatic refunds on cancellation, CSP opened for Razorpay only when enabled. Test mode stays the default. Covered by tests with the API mocked; needs real test keys for a live trial.
- About page: live numbers (events, cities, people registered, organizers) and a tilted strip of current event posters linking to each event.
- Repeating events: "Add more dates" (every week / 2 weeks / 4 weeks, up to 12) creates linked copies with their own tickets and freshly drawn posters; the event page shows "Other dates" chips; listings show a series once with "+N more dates".
