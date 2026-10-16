from flask import Blueprint, abort, current_app, jsonify, render_template, request, url_for

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
    )


@bp.route("/events")
def explore():
    # Basic results list so homepage search and shortcuts work.
    # Phase 3 turns this into the full Explore page with filters and tabs.
    q = request.args.get("q", "")
    city = request.args.get("city") or None
    category = request.args.get("category") or None
    when = "past" if request.args.get("when") == "past" else "upcoming"
    results = store().search(q, city=city, category=category, when=when)
    return render_template("explore_stub.html", results=results, q=q, city=city, category=category, when=when)


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
    e = store().get(slug)
    if not e:
        abort(404)
    return render_template("event_stub.html", e=e)
