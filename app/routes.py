from datetime import timezone

from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request, url_for

from .events import DATE_FILTERS, PRICE_FILTERS, SORTS, now_ist

bp = Blueprint("main", __name__)


def store():
    return current_app.extensions["events"]


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


@bp.route("/events/<slug>/register")
def register(slug):
    # Checkout arrives in phase 5. For now, confirm what was picked.
    e = store().get(slug)
    if not e:
        abort(404)
    picked = [(t, request.args.get(f"t{i}", 0, type=int)) for i, t in enumerate(e.tickets)]
    picked = [(t, n) for t, n in picked if n > 0]
    return render_template("register_stub.html", e=e, picked=picked, notify=bool(request.args.get("notify")))


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
