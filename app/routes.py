import re
from datetime import timezone
from html import escape

from flask import (Blueprint, Response, abort, current_app, flash, g, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)

from .events import DATE_FILTERS, PRICE_FILTERS, SORTS, EventStore, now_ist
from .models import rating_summary
from .ratelimit import hit

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
    followed = set(followed_slugs())
    return render_template(
        "home.html",
        from_followed=[e for e in upcoming if e.organizer in followed][:4],
        featured=s.featured() or upcoming[:4],
        upcoming=upcoming,
        # Each city tile uses the banner of its next event as the background.
        cities=[(c, n, next(e for e in upcoming if e.city == c)) for c, n in s.counts("city")],
        category_counts=s.counts("category"),
        past=s.past()[:4],
        # "When are you free?" shortcuts with how many events each one finds.
        when_counts=[(key, label, len(s.search(date=key))) for key, label in DATE_FILTERS],
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
    calendar = month_calendar(s, args.get("month"), base) if when == "upcoming" and args.get("view") == "calendar" else None
    per_page = 10_000 if current_app.config.get("STATIC_PREVIEW") else PER_PAGE  # no paging in the static preview
    page = max(args.get("page", 1, type=int), 1)
    pages = max((len(results) + per_page - 1) // per_page, 1)
    page = min(page, pages)
    return render_template(
        "explore.html",
        results=results[(page - 1) * per_page: page * per_page],
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
        calendar=calendar,
    )


def month_calendar(s, month_arg, filters):
    """Weeks (Monday first) of the month, each day with the upcoming events running that day."""
    import calendar as cal
    from datetime import date, timedelta

    today = now_ist().date()
    try:
        year, month = (int(x) for x in (month_arg or "").split("-"))
        first = date(year, month, 1)
    except ValueError:
        first = today.replace(day=1)
    # Only this month and the next 23 can be browsed (keeps crawlers out of endless months).
    first = min(max(first, today.replace(day=1)), (today.replace(day=1) + timedelta(days=31 * 23)).replace(day=1))
    by_day = {}
    for e in s.search(when="upcoming", **filters):
        # A night that ends at 1 am belongs to the day it started; multi-day events show on each day.
        day, last = e.start.date(), min((e.end - timedelta(hours=6)).date(), e.start.date() + timedelta(days=6))
        last = max(last, day)
        while day <= last:
            by_day.setdefault(day, []).append(e)
            day += timedelta(days=1)
    weeks = [[(d, by_day.get(d, [])) for d in week] for week in cal.Calendar().monthdatescalendar(first.year, first.month)]
    prev_month = (first - timedelta(days=1)).replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    return {
        "first": first, "weeks": weeks, "today": today,
        "prev": prev_month.strftime("%Y-%m") if prev_month >= today.replace(day=1) else None,
        "next": next_month.strftime("%Y-%m"),
        "agenda": [(d, evs) for week in weeks for d, evs in week if evs and d.month == first.month and d >= today],
        "count": len({e.slug for week in weeks for d, evs in week if d.month == first.month for e in evs}),
    }


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
    from .booking import questions_context, review_context

    org_slugs = [x.slug for x in s.by_organizer(e.organizer)]
    return render_template("event.html", e=e, similar=s.similar(e), org_events=len(org_slugs),
                           org_rating=rating_summary(org_slugs), **review_context(e), **questions_context(e))


@bp.app_template_global()
def announcements_for(slug, limit=3):
    """Latest organizer updates for an event, newest first."""
    from .models import Announcement

    return Announcement.query.filter_by(event_slug=slug).order_by(Announcement.created_at.desc()).limit(limit).all()


@bp.route("/share.png")
def site_share_image():
    from flask import send_file

    from .share import site_card_path

    return send_file(site_card_path(), mimetype="image/png", max_age=86400)


@bp.route("/events/<slug>/share.png")
def event_share_image(slug):
    """Link preview card (Open Graph image)."""
    from flask import send_file

    from .share import card_path

    e = store().get(slug)
    if not e:
        abort(404)
    return send_file(card_path(e), mimetype="image/png", max_age=3600)


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
                           registered=sum(e.registered for e in events), followers=follower_count(slug),
                           rating=rating_summary([e.slug for e in events]))


# ---------- Following organizers ----------
@bp.app_template_global()
def followed_slugs():
    from .models import Follow

    if g.get("user") is None:
        return []
    return [f.organizer_slug for f in Follow.query.filter_by(user_id=g.user.id)]


def follower_count(slug):
    from .models import Follow

    return Follow.query.filter_by(organizer_slug=slug).count()


@bp.route("/organizers/<slug>/follow", methods=["POST"])
def follow(slug):
    from .auth import safe_next
    from .models import Follow, db

    if slug not in store().organizers:
        abort(404)
    back = safe_next(request.form.get("next") or url_for("main.organizer", slug=slug))
    if g.user is None:
        return redirect(url_for("auth.login", next=back))
    row = Follow.query.filter_by(user_id=g.user.id, organizer_slug=slug).first()
    if request.form.get("follow") == "0":
        if row:
            db.session.delete(row)
            db.session.commit()
    elif row is None:
        db.session.add(Follow(user_id=g.user.id, organizer_slug=slug))
        db.session.commit()
        flash(f"You're following {store().organizers[slug]['name']}. Their new events will show up on your homepage.")
    return redirect(back)


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
        if not errors and not hit("contact"):
            errors.append("We've had a lot of messages from your connection. Please try again in an hour.")
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


# Rough city centres for "Near me" (worked out in the browser; the location never reaches us).
CITY_CENTRES = {
    "Jaipur": (26.912, 75.787), "Kota": (25.213, 75.865), "Jodhpur": (26.239, 73.024), "Ajmer": (26.450, 74.640),
    "Surat": (21.170, 72.831), "Chandigarh": (30.733, 76.779), "Udaipur": (24.585, 73.712), "Bikaner": (28.022, 73.312),
    "Ahmedabad": (23.023, 72.571), "Delhi": (28.614, 77.209), "Pushkar": (26.490, 74.551), "Mohali": (30.704, 76.717),
}


@bp.app_template_global()
def near_me_cities():
    """{city: [lat, lng, url]} for cities that have upcoming events and a known centre."""
    return {c: [*CITY_CENTRES[c], city_url(c)] for c, _ in store().counts("city") if c in CITY_CENTRES}


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
    lines += [f"Disallow: {p}" for p in ("/organizer", "/account", "/tickets", "/bookings", "/pay", "/t/", "/pass/", "/admin", "/login", "/api", "/saved")]
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


@bp.route("/preview-only")
def preview_only():
    """Shown in the static GitHub Pages preview in place of pages that need the live server."""
    if not current_app.config.get("STATIC_PREVIEW"):
        abort(404)
    return render_template("preview.html")


@bp.route("/healthz")
def healthz():
    """For the host's health checks and uptime monitors: 200 when the app and database answer."""
    from sqlalchemy import text

    from .models import db

    try:
        db.session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001  any database failure means "unhealthy"
        current_app.logger.exception("Health check: database unreachable")
        return jsonify(status="error", database="unreachable"), 503
    return jsonify(status="ok"), 200, {"Cache-Control": "no-store"}


# ---------- Installable app (PWA) ----------
@bp.route("/manifest.webmanifest")
def manifest():
    icon = lambda size: {"src": url_for("static", filename=f"icons/icon-{size}.png"), "sizes": f"{size}x{size}",  # noqa: E731
                         "type": "image/png", "purpose": "any maskable"}
    return jsonify(
        name="Eventouse: events near you", short_name="Eventouse", start_url="/?source=app", scope="/",
        display="standalone", background_color="#FFF8F0", theme_color="#1A1423",
        description="Discover and book runs, concerts, workshops and festivals.",
        icons=[icon(192), icon(512)],
        shortcuts=[{"name": "My tickets", "url": "/tickets"}, {"name": "Explore events", "url": "/events"}],
    ), 200, {"Content-Type": "application/manifest+json"}


@bp.route("/sw.js")
def service_worker():
    # Served from the root so it can look after every page; never cached long, so updates arrive.
    res = send_from_directory(current_app.static_folder, "js/sw.js", mimetype="text/javascript", max_age=0)
    res.headers["Cache-Control"] = "no-cache"
    return res


@bp.route("/offline")
def offline():
    g.user = None  # the service worker keeps this page; it must not carry anyone's name
    return render_template("offline.html")
