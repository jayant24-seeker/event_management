from flask import Blueprint, abort, current_app, redirect, render_template, url_for

bp = Blueprint("main", __name__)


def store():
    return current_app.extensions["events"]


@bp.route("/")
def home():
    # Homepage is phase 2; until then, show the design system.
    return redirect(url_for("main.styleguide"))


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
