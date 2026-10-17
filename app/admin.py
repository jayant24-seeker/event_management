"""Eventouse staff area: site numbers, every event (hide, feature), organizers (verify)
and the contact inbox. Open to the phone numbers in ADMIN_PHONES."""
from datetime import timedelta
from functools import wraps

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func

from .auth import login_required
from .models import Attendee, Booking, ContactMessage, EventRow, Organizer, User, db, utcnow

bp = Blueprint("admin", __name__, url_prefix="/admin")


def is_admin(user):
    phones = {p.strip() for p in current_app.config.get("ADMIN_PHONES", "").split(",") if p.strip()}
    return user is not None and user.phone in phones


@bp.app_template_global("is_admin")
def is_admin_global():
    return is_admin(g.get("user"))


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not is_admin(g.user):
            abort(404)  # don't reveal that the page exists
        return view(*args, **kwargs)
    return wrapped


@bp.route("/")
@admin_required
def home():
    week_ago = utcnow() - timedelta(days=7)
    confirmed = Booking.query.filter_by(status="confirmed")
    numbers = [
        ("People signed up", User.query.count(), f"{User.query.filter(User.created_at > week_ago).count()} this week"),
        ("Tickets sold", db.session.query(func.count(Attendee.id)).join(Booking).filter(Booking.status == "confirmed").scalar(),
         f"{confirmed.filter(Booking.confirmed_at > week_ago).count()} bookings this week"),
        ("Ticket revenue", confirmed.with_entities(func.coalesce(func.sum(Booking.subtotal - Booking.discount), 0)).scalar(), "inr"),
        ("Live events", EventRow.query.filter_by(status="published").count(), f"{EventRow.query.filter_by(status='draft').count()} drafts"),
        ("Organizers", Organizer.query.count(), f"{sum(1 for o in Organizer.query if o.data.get('verified'))} verified"),
        ("Open messages", ContactMessage.query.filter_by(handled_at=None).count(), "in the inbox"),
    ]
    rows = EventRow.query.order_by(EventRow.updated_at.desc()).all()
    orgs = {o.slug: o for o in Organizer.query}
    return render_template("admin/home.html", numbers=numbers, rows=rows, orgs=orgs,
                           messages=ContactMessage.query.order_by(ContactMessage.handled_at.isnot(None),
                                                                  ContactMessage.created_at.desc()).limit(50).all())


@bp.route("/events/<slug>", methods=["POST"])
@admin_required
def event_action(slug):
    row = db.session.get(EventRow, slug) or abort(404)
    action = request.form.get("action")
    if action == "hide" and row.status == "published":
        row.status = "draft"
        flash(f"{row.data.get('title')} is hidden and back in the organizer's drafts.")
    elif action in ("feature", "unfeature"):
        row.data = dict(row.data, featured=action == "feature")
        flash(f"{row.data.get('title')} {'is now featured on the homepage' if action == 'feature' else 'is no longer featured'}.")
    db.session.commit()
    return redirect(url_for("admin.home") + "#events")


@bp.route("/organizers/<slug>", methods=["POST"])
@admin_required
def organizer_action(slug):
    org = db.session.get(Organizer, slug) or abort(404)
    org.data = dict(org.data, verified=request.form.get("verified") == "1")
    db.session.commit()
    flash(f"{org.data['name']} is {'now verified' if org.data['verified'] else 'no longer verified'}.")
    return redirect(url_for("admin.home") + "#organizers")


@bp.route("/messages/<int:mid>", methods=["POST"])
@admin_required
def message_done(mid):
    m = db.session.get(ContactMessage, mid) or abort(404)
    m.handled_at = None if m.handled_at else utcnow()
    db.session.commit()
    return redirect(url_for("admin.home") + "#inbox")
