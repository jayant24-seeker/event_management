# Event Management by Soft Technologies

New event discovery and booking website for Eventouse (owned by N Square Digital Solutions, built by Shree Soft Technologies).

**Stack:** Flask (Jinja templates, server-rendered for SEO) + Tailwind CSS 3. Small bits of JS will be added per page where needed.

## Run locally (Mac)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm install                 # only needed to rebuild CSS
npm run css:watch           # keep running in a second terminal while editing templates
flask --app run run --debug # open http://127.0.0.1:5000
pytest                      # run tests
```

The built CSS (`app/static/css/app.css`) is committed, so the site runs without Node.

The first run creates `instance/eventouse.db` (SQLite) and loads the demo events. To start fresh:

```bash
flask --app run seed --reset
```

**Signing in locally:** enter any 10-digit mobile number. No SMS is sent in development; the code is shown on the next screen (`SMS_PROVIDER=console`). **Demo organizer:** sign in with `99999 99999` to open the Pink Pace Runners Club dashboard (Organizer dashboard in the account menu). Any other number can become an organizer at `/organizer/start`. **Demo admin:** `88888 88888` opens `/admin` (set `ADMIN_PHONES` in production). Demo discount codes: `EARLYBIRD10` (Amer Hills Trail Ultra), `PINKCITY15` (Jaipur Night Run), `SIBLING20` (Little Legs Kids Run). Payments run in **test mode**.

### Deploy

```bash
pip install -r requirements.txt
SECRET_KEY=... DATABASE_URL=... flask --app run seed   # once, on a new database
SECRET_KEY=... DATABASE_URL=... gunicorn --workers 3 --bind 0.0.0.0:8000 run:app
```
Put it behind HTTPS (Nginx, Render, Railway or similar) and point the health check at `/healthz`. `.env.example` lists the settings. Static files are versioned (`app.css?v=...`) and cached for a year.

### SEO built in
Unique titles and descriptions, Open Graph tags, Event JSON-LD on event pages, FAQ JSON-LD on city pages, `/sitemap.xml`, `/robots.txt`, and city pages like `/events-in-jaipur`. Filtered Explore pages are `noindex`.

### Before launch
| Setting | Why |
| --- | --- |
| `SECRET_KEY` | Signs the login cookie. Use a long random value. |
| `DATABASE_URL` | Postgres in production (SQLite is fine for development). |
| `SMS_PROVIDER` + key | Real OTP SMS (MSG91 or Twilio), wired in `app/sms.py`. |
| Razorpay keys | Replace the test payment page (`/pay/<ref>`) with Razorpay Checkout + webhook. |
| `SESSION_COOKIE_SECURE=1` | Cookies over HTTPS only. |
| `MAIL_PROVIDER=smtp` + `MAIL_*` | Booking confirmation emails (logged to the console in development). |
| `ADMIN_PHONES` | Eventouse staff numbers that can open `/admin`. |
| `TRUSTED_PROXY=1` | Behind Nginx/Render, so per-IP rate limits see the real visitor. |
| Real refunds | `booking.cancel` records the refund; call the payment provider's refund API there. |

## Layout

| Path | What |
| --- | --- |
| `app/events.py` | Event model: Upcoming/Past split, badges (Free, Selling fast, Sold out, Event ended), search, filters, search suggestions, city/category counts, publish checks that block blank fields and placeholder text |
| `app/routes.py` | `/` homepage, `/events` Explore page (search, filters, Upcoming/Past tabs, Grid/Calendar), `/api/suggest` search suggestions, `/events/<slug>` event page, `/events/<slug>.ics` calendar file, `/events/<slug>/share.png` link preview, `/organizers/<slug>` organizer profile (+ follow), PWA files (`/manifest.webmanifest`, `/sw.js`, `/offline`) |
| `app/static/js/` | `hero.js` (homepage slider), `search.js` (live suggestions), `explore.js` (filter bar), `event.js` (ticket picker, countdown, save, share, results search), `near.js` (Near me, on-device), `sw.js` (offline tickets), `site.js` |
| `app/data/events.json` | 16 dummy events (7 cities incl. Online, 3 past with results) |
| `app/data/organizers.json` | 9 organizer profiles |
| `app/models.py` | Database tables: organizers, events, users, OTP codes, bookings, attendees (tickets), coupons, saved events, waitlist, follows, reviews, organizer updates, contact messages. New nullable columns are added to older databases on startup |
| `app/auth.py` | Phone + OTP sign-in, profile, sign out |
| `app/booking.py` | Checkout with attendee details, coupons and group discounts, test payment, confirmations (SMS + email), QR tickets and per-ticket passes, transfers, cancellations with refunds, waitlist (with SMS when seats open), reviews, saved events |
| `app/organizer.py` | Organizer profile, dashboard, create/edit/duplicate events (publish checks), sales chart and key numbers, attendee list + CSV, coupons, waitlist, messages to ticket holders, QR check-in |
| `app/admin.py` | `/admin` for the Eventouse team: totals, feature/hide events, verify organizers, contact inbox |
| `app/share.py` | 1200x630 PNG link previews (Pillow, Mukta font in `app/fonts/`) |
| `app/mailer.py` | Email sending (console in development, SMTP in production) |
| `app/ratelimit.py` | Per-IP limits on OTP, waitlist and contact form |
| `app/posters.py` | Original SVG posters/banners for demo events and organizer events without artwork |
| `app/sms.py` | SMS sending (console in development) |
| `app/seed.py` | Loads `data/*.json` into an empty database; `flask seed --reset` |
| `app/seo.py` | Event and FAQ JSON-LD for Google, calendar helpers |
| `app/i18n.py` | Hindi/English toggle for the site's own words |
| `app/templates/components/_macros.html` | Poster card, badge, date chip, price label |
| `app/static/src/input.css` | Color tokens and component classes |
| `tailwind.config.js` | Fonts, colors, shadows |
| `tools/make_posters.py` | Regenerates the demo events' posters and banners |
| `/styleguide` | Live design-system page |

## Overnight improvements

Branch `auto-improvements` adds reviews, follows, refunds, transfers, offline tickets, analytics, an admin area and more. The full list, newest last, is in [docs/IMPROVEMENTS.md](docs/IMPROVEMENTS.md).

## Build plan

1. ✅ Setup, design system, dummy data
2. ✅ Homepage
3. ✅ Explore Events (search, filters, Upcoming/Past tabs)
4. ✅ Event page
5. ✅ Account and booking
6. ✅ For Organizers, About, Contact
7. ✅ SEO, speed, mobile testing, Hindi/English, launch prep
