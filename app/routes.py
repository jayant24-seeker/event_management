import re
from datetime import timezone
from html import escape

from flask import Blueprint, Response, abort, g, jsonify, redirect, render_template, request, url_for

from .events import DATE_FILTERS, PRICE_FILTERS, SORTS, EventStore, now_ist

bp = Blueprint("main", __name__)


def store():
    """Events for this request, with live ticket sales (loaded once per request)."""
    if "store" not in g:
        g.store = EventStore.from_db()
    return g.store


@bp.route("/")
def home():
    s = store()
    upcoming = s.upcoming()
    return render_template(
        "home.html",
        featured=s.featured() or upcoming[:4],
        upcoming=upcoming,
        # Each city tile uses the banner of its next event as the background.
        cities=[(c, n, next(e for e in upcoming if e.city == c)) for c, n in s.counts("city")],
        category_counts=s.counts("category"),
        past=s.past()[:4],
    )


PER_PAGE = 12
EXPLORE_DEFAULTS = {"when": "upcoming", "sort": "date", "page": 1}


@bp.app_template_global()
def explore_url(**changes):
    """Explore link that keeps the current filters, with some changed. None removes one.
    Any filter change sends you back to page 1."""
    params = request.args.to_dict() if request.endpoint == "main.explore" else {}
    params.pop("page", None)
    params.update(changes)
    clean = {k: v for k, v in params.items() if v not in (None, "") and EXPLORE_DEFAULTS.get(k) != v}
    return url_for("main.explore", **clean)


@bp.route("/events")
def explore():
    s = store()
    args = request.args
    when = "past" if args.get("when") == "past" else "upcoming"
    f = {
        "q": args.get("q", "").strip(),
        "city": args.get("city") or None,
        "category": args.get("category") or None,
        "date": args.get("date") if args.get("date") in dict(DATE_FILTERS) else None,
        "price": args.get("price") if args.get("price") in dict(PRICE_FILTERS) else None,
        "sort": args.get("sort") if args.get("sort") in dict(SORTS) else "date",
    }
    base = {k: f[k] for k in ("q", "city", "category", "price")}
    results = s.search(when=when, sort=f["sort"], date=f["date"], **base)
    # Tab counts use the same search, city, category and price, but ignore the date filter.
    tab_counts = {
        "upcoming": len(s.search(when="upcoming", **base)),
        "past": len(s.search(when="past", **base)),
    }
    page = max(args.get("page", 1, type=int), 1)
    pages = max((len(results) + PER_PAGE - 1) // PER_PAGE, 1)
    page = min(page, pages)
    return render_template(
        "explore.html",
        results=results[(page - 1) * PER_PAGE: page * PER_PAGE],
        total=len(results),
        page=page,
        pages=pages,
        when=when,
        f=f,
        tab_counts=tab_counts,
        city_options=[(c, c) for c in s.cities()],
        category_options=[(c, c) for c in s.categories()],
        # Chip counts follow the other filters, so a chip never leads to an empty page.
        categories=_category_counts(s.search(when=when, date=f["date"], q=f["q"], city=f["city"], price=f["price"])),
        date_filters=DATE_FILTERS,
        price_filters=PRICE_FILTERS,
        sorts=SORTS,
        popular=s.search(sort="popular")[:4] if not results else [],
    )


def _category_counts(events):
    totals = {}
    for e in events:
        totals[e.category] = totals.get(e.category, 0) + 1
    return sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))


@bp.route("/api/suggest")
def suggest():
    found = store().suggest(request.args.get("q", ""))
    return jsonify(
        events=[
            {
                "title": e.title,
                "url": url_for("main.event", slug=e.slug),
                "poster": url_for("static", filename=e.poster),
                "meta": f"{e.start.strftime('%d %b')} · {e.city}",
            }
            for e in found["events"]
        ],
        cities=[{"name": c, "url": url_for("main.explore", city=c)} for c in found["cities"]],
        categories=[{"name": c, "url": url_for("main.explore", category=c)} for c in found["categories"]],
    )


@bp.route("/styleguide")
def styleguide():
    s = store()
    return render_template(
        "styleguide.html",
        upcoming=s.upcoming(),
        past=s.past(),
        featured=s.featured(),
        cities=s.cities(),
        categories=s.categories(),
    )


@bp.route("/events/<slug>")
def event(slug):
    s = store()
    e = s.get(slug)
    if not e:
        abort(404)
    return render_template("event.html", e=e, similar=s.similar(e), org_events=len(s.by_organizer(e.organizer)))


@bp.route("/events/<slug>.ics")
def event_ics(slug):
    """Add-to-calendar file (works with Apple, Outlook and Google Calendar)."""
    e = store().get(slug)
    if not e:
        abort(404)
    fmt = "%Y%m%dT%H%M%S"
    where = e.venue["name"] if e.is_online else f"{e.venue['name']}, {e.venue['address']}"

    def esc(text):
        return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Eventouse//Events//EN", "BEGIN:VEVENT",
        f"UID:{e.slug}@eventouse.com",
        f"DTSTAMP:{now_ist().astimezone(timezone.utc).strftime(fmt)}Z",
        f"DTSTART:{e.start.astimezone(timezone.utc).strftime(fmt)}Z",
        f"DTEND:{e.end.astimezone(timezone.utc).strftime(fmt)}Z",
        f"SUMMARY:{esc(e.title)}",
        f"LOCATION:{esc(where)}",
        f"DESCRIPTION:{esc(e.tagline)}\\n{url_for('main.event', slug=e.slug, _external=True)}",
        "END:VEVENT", "END:VCALENDAR",
    ]
    return Response("\r\n".join(lines) + "\r\n", mimetype="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="{e.slug}.ics"'})


@bp.route("/organizers/<slug>")
def organizer(slug):
    s = store()
    org = s.organizers.get(slug)
    if not org:
        abort(404)
    events = s.by_organizer(slug)
    upcoming = sorted((e for e in events if not e.is_past()), key=lambda e: e.start)
    past = sorted((e for e in events if e.is_past()), key=lambda e: e.start, reverse=True)
    return render_template("organizer.html", org=org, upcoming=upcoming, past=past,
                           registered=sum(e.registered for e in events))


PAGES = {"about": "About us", "privacy": "Privacy policy", "terms": "Terms of use", "refunds": "Refund and cancellation policy"}


@bp.route("/<any(about, privacy, terms, refunds):name>")
def page(name):
    return render_template(f"pages/{name}.html", title=PAGES[name])


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    from .models import ContactMessage, db

    form, errors, sent = request.form, [], False
    if request.method == "POST":
        if form.get("website"):  # hidden field only bots fill in
            return redirect(url_for("main.contact"))
        name, reply_to, message = form.get("name", "").strip(), form.get("reply_to", "").strip(), form.get("message", "").strip()
        topic = form.get("topic") if form.get("topic") in TOPICS else "other"
        if len(name) < 2:
            errors.append("Please enter your name.")
        if len(reply_to) < 6:
            errors.append("Add a phone number or email so we can reply.")
        if len(message) < 10:
            errors.append("Tell us a little more in the message.")
        if not errors:
            db.session.add(ContactMessage(name=name[:120], reply_to=reply_to[:200], topic=topic, message=message[:4000]))
            db.session.commit()
            sent = True
    return render_template("pages/contact.html", title="Contact us", form=form, errors=errors, sent=sent, topics=TOPICS)


TOPICS = {"attendee": "A booking or ticket", "organizer": "Hosting an event", "partnership": "Partnership or media", "other": "Something else"}


@bp.route("/for-organizers")
def for_organizers():
    s = store()
    return render_template("pages/for_organizers.html", title="Host your event",
                           n_events=len(s.events), n_cities=len(s.cities()),
                           n_people=sum(e.registered for e in s.events), sample=s.featured()[:3])


# ---------- SEO: city landing pages, sitemap, robots ----------
def city_slug(city):
    return re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-")


@bp.app_template_global()
def city_url(city):
    """City landing page, or Explore for online events."""
    if city == "Online":
        return url_for("main.explore", city="Online")
    return url_for("main.city", slug=city_slug(city))


@bp.route("/events-in-<slug>")
def city(slug):
    s = store()
    name = next((c for c in s.cities() if city_slug(c) == slug and c != "Online"), None)
    if name is None:
        abort(404)
    upcoming = [e for e in s.upcoming() if e.city == name]
    weekend = s.search(city=name, date="weekend")
    return render_template("city.html", city=name, upcoming=upcoming, weekend=weekend,
                           past=[e for e in s.past() if e.city == name][:4],
                           categories=_category_counts(upcoming),
                           free=[e for e in upcoming if e.is_free])


@bp.route("/robots.txt")
def robots():
    lines = ["User-agent: *", "Allow: /"]
    lines += [f"Disallow: {p}" for p in ("/organizer", "/account", "/tickets", "/bookings", "/pay", "/t/", "/login", "/api", "/saved")]
    lines.append(f"Sitemap: {url_for('main.sitemap', _external=True)}")
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


@bp.route("/sitemap.xml")
def sitemap():
    from .models import EventRow

    s = store()
    updated = {r.slug: r.updated_at for r in EventRow.query.filter_by(status="published")}
    urls = [(url_for("main.home", _external=True), None, "daily"),
            (url_for("main.explore", _external=True), None, "daily"),
            (url_for("main.explore", when="past", _external=True), None, "weekly")]
    urls += [(url_for("main.city", slug=city_slug(c), _external=True), None, "daily") for c in s.cities() if c != "Online"]
    urls += [(url_for("main.event", slug=e.slug, _external=True), updated.get(e.slug), "weekly") for e in s.events]
    urls += [(url_for("main.organizer", slug=o, _external=True), None, "weekly") for o in s.organizers]
    urls += [(url_for(endpoint, _external=True, **kw), None, "monthly") for endpoint, kw in
             [("main.for_organizers", {}), ("main.contact", {})] + [("main.page", {"name": n}) for n in PAGES]]
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, freq in urls:
        xml.append(f"  <url><loc>{escape(loc)}</loc>" + (f"<lastmod>{lastmod:%Y-%m-%d}</lastmod>" if lastmod else "")
                   + f"<changefreq>{freq}</changefreq></url>")
    xml.append("</urlset>")
    return Response("\n".join(xml), mimetype="application/xml")
