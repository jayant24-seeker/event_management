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

## Layout

| Path | What |
| --- | --- |
| `app/events.py` | Event model: Upcoming/Past split, badges (Free, Selling fast, Sold out, Event ended), search, filters, search suggestions, city/category counts, publish checks that block blank fields and placeholder text |
| `app/routes.py` | `/` homepage, `/events` search results (full Explore page in phase 3), `/api/suggest` search suggestions, `/events/<slug>` |
| `app/static/js/` | `hero.js` (homepage slider), `search.js` (live suggestions) |
| `app/data/events.json` | 8 dummy events (6 cities, 2 past) |
| `app/templates/components/_macros.html` | Poster card, badge, date chip, price label |
| `app/static/src/input.css` | Color tokens and component classes |
| `tailwind.config.js` | Fonts, colors, shadows |
| `tools/make_posters.py` | Generates original placeholder posters and banners |
| `/styleguide` | Live design-system page |

## Build plan

1. ✅ Setup, design system, dummy data
2. ✅ Homepage
3. Explore Events (search, filters, Upcoming/Past tabs)
4. Event page
5. Account and booking
6. For Organizers, About, Contact
7. SEO, speed, mobile testing, launch
