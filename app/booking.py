"""Checkout, payment (test mode for now), tickets with QR codes, waitlist and saved events."""
import re
import secrets
import threading
from datetime import datetime

import segno
from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from .auth import login_required, normalize_phone
from .events import IST, now_ist
from .models import (PAYMENT_HOLD, Attendee, Booking, Coupon, EventRow, SavedEvent, WaitlistEntry, db,
                     seats_taken, utcnow)
from .routes import store

bp = Blueprint("booking", __name__)

MAX_PER_TIER = 10

# What we can ask each attendee. Organizers pick from these per event ("attendee_fields").
FIELDS = {
    "name": {"label": "Full name", "type": "text", "required": True},
    "gender": {"label": "Gender", "type": "select", "options": ["Female", "Male", "Other"], "required": True},
    "age": {"label": "Age", "type": "number", "required": True},
    "tshirt": {"label": "T-shirt size", "type": "select", "options": ["XS", "S", "M", "L", "XL", "XXL"], "required": True},
    "emergency": {"label": "Emergency contact (name and phone)", "type": "text", "required": True},
    "email": {"label": "Email", "type": "email", "required": True},
    "company": {"label": "Company or college", "type": "text", "required": False},
    "fide_id": {"label": "FIDE ID (Open section only)", "type": "text", "required": False},
}
SPORT_FIELDS = ["name", "gender", "age", "tshirt", "emergency"]
DEFAULT_FIELDS = ["name", "gender", "age"]

# Stops two people buying the last seat at the same moment (one server process).
# On Postgres the row lock below does the same job across processes.
_booking_lock = threading.Lock()


def field_keys(raw):
    """Attendee details asked for this event: the organizer's choice, else a default by category."""
    keys = raw.get("attendee_fields") or (SPORT_FIELDS if raw.get("category") in ("Running", "Cycling") else DEFAULT_FIELDS)
    return [k for k in keys if k in FIELDS]


def fields_for(e):
    return [(k, FIELDS[k]) for k in field_keys(e.raw)]


def get_event_or_404(slug):
    e = store().get(slug)
    if not e:
        abort(404)
    return e


def picked_from(e, source):
    """[(tier index, ticket, qty)] from t0=2&t1=1 style fields, capped to what's on sale."""
    out = []
    for i, t in enumerate(e.tickets):
        n = source.get(f"t{i}", 0, type=int) or 0
        if n > 0 and not t.sold_out:
            out.append((i, t, min(n, MAX_PER_TIER, t.left)))
    return out


def find_coupon(e, code, subtotal):
    """(coupon, discount, error)."""
    code = (code or "").strip().upper()
    if not code:
        return None, 0, None
    c = Coupon.query.filter_by(event_slug=e.slug, code=code).first()
    if c is None:
        return None, 0, "That code isn't valid for this event."
    if c.valid_until and now_ist().replace(tzinfo=None) > c.valid_until:
        return None, 0, "That code has expired."
    if c.max_uses is not None:
        used = Booking.query.filter(Booking.event_slug == e.slug, Booking.coupon_code == c.code,
                                    Booking.status.in_(["confirmed", "pending"])).count()
        if used >= c.max_uses:
            return None, 0, "That code has been fully used."
    return c, subtotal * c.percent_off // 100, None


def read_attendees(e, picked, form):
    """Attendee details from the form, one per ticket, plus a list of problems."""
    fields = fields_for(e)
    people, errors = [], []
    k = 0
    for _, t, n in picked:
        for _ in range(n):
            details = {}
            for key, spec in fields:
                value = form.get(f"a{k}-{key}", "").strip()[:200]
                if spec["required"] and not value:
                    errors.append(f"Ticket {k + 1}: {spec['label'].lower()} is required.")
                elif key == "age" and value and not (value.isdigit() and 1 <= int(value) <= 100):
                    errors.append(f"Ticket {k + 1}: enter an age between 1 and 100.")
                elif spec["type"] == "select" and value and value not in spec["options"]:
                    errors.append(f"Ticket {k + 1}: pick a {spec['label'].lower()}.")
                elif key == "email" and value and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
                    errors.append(f"Ticket {k + 1}: that email doesn't look right.")
                details[key] = value
            age_min = e.raw.get("age_min")
            if age_min and details.get("age", "").isdigit() and int(details["age"]) < age_min:
                errors.append(f"Ticket {k + 1}: the minimum age is {age_min}.")
            people.append((t, details))
            k += 1
    return people, errors


@bp.route("/events/<slug>/register", methods=["GET", "POST"])
@login_required
def register(slug):
    e = get_event_or_404(slug)
    if not e.registration_open():
        flash("Registration for this event is closed." if not e.sold_out else "This event is sold out.")
        return redirect(url_for("main.event", slug=slug))
    source = request.form if request.method == "POST" else request.args
    picked = picked_from(e, source)
    if not picked:
        flash("Pick at least one ticket.")
        return redirect(url_for("main.event", slug=slug) + "#tickets")

    subtotal = sum(t.price * n for _, t, n in picked)
    coupon, discount, coupon_error = find_coupon(e, source.get("coupon"), subtotal)
    errors = []

    if request.method == "POST" and request.form.get("action") == "book":
        people, errors = read_attendees(e, picked, request.form)
        if coupon_error:
            errors.append(coupon_error)
        if not errors:
            booking, error = create_booking(e, people, subtotal, discount, coupon)
            if error:
                errors.append(error)
            elif booking.status == "confirmed":
                flash("You're in! Your tickets are below.")
                return redirect(url_for("booking.show", ref=booking.ref))
            else:
                return redirect(url_for("booking.pay", ref=booking.ref))

    return render_template("booking/checkout.html", e=e, picked=picked, fields=fields_for(e), subtotal=subtotal,
                           coupon=coupon, coupon_code=source.get("coupon", ""), coupon_error=coupon_error,
                           discount=discount, errors=errors, form=request.form)


def create_booking(e, people, subtotal, discount, coupon):
    """Re-check seats and save the booking. Free bookings are confirmed straight away."""
    with _booking_lock:
        # Lock the event row (Postgres) so seat counts can't change under us.
        EventRow.query.filter_by(slug=e.slug).with_for_update().first()
        taken = seats_taken(e.slug)
        wanted = {}
        for t, _ in people:
            wanted[t.name] = wanted.get(t.name, 0) + 1
        for raw_t in e.raw["tickets"]:
            n = wanted.get(raw_t["name"], 0)
            left = raw_t["capacity"] - raw_t.get("sold", 0) - taken.get((e.slug, raw_t["name"]), 0)
            if n > left:
                db.session.rollback()
                return None, f"Only {max(left, 0)} {raw_t['name']} ticket(s) left. Please change your selection."
        booking = Booking(user_id=g.user.id, event_slug=e.slug, subtotal=subtotal, discount=discount,
                          coupon_code=coupon.code if coupon else None)
        for t, details in people:
            booking.attendees.append(Attendee(ticket_name=t.name, price=t.price, details=details))
        if booking.total == 0:
            booking.status, booking.confirmed_at = "confirmed", utcnow()
        db.session.add(booking)
        db.session.commit()
        return booking, None


def own_booking_or_404(ref):
    booking = Booking.query.filter_by(ref=ref).first()
    if booking is None or booking.user_id != g.user.id:
        abort(404)
    return booking


@bp.route("/pay/<ref>", methods=["GET", "POST"])
@login_required
def pay(ref):
    """TEST MODE payment page. Swap for Razorpay Checkout before launch (see docs)."""
    booking = own_booking_or_404(ref)
    e = get_event_or_404(booking.event_slug)
    if booking.status == "confirmed":
        return redirect(url_for("booking.show", ref=ref))
    expired = booking.status == "cancelled" or booking.created_at < utcnow() - PAYMENT_HOLD
    if request.method == "POST" and not expired:
        if request.form.get("action") == "pay":
            booking.status, booking.confirmed_at = "confirmed", utcnow()
            booking.payment_ref = "TEST-" + secrets.token_hex(6).upper()
            db.session.commit()
            flash("Payment received. You're in!")
            return redirect(url_for("booking.show", ref=ref))
        booking.status = "cancelled"
        db.session.commit()
        flash("Payment cancelled. Your seats were released.")
        return redirect(url_for("main.event", slug=e.slug))
    if expired and booking.status == "pending":
        booking.status = "cancelled"
        db.session.commit()
    return render_template("booking/pay.html", b=booking, e=e, expired=expired,
                           hold_ends=booking.created_at + PAYMENT_HOLD)


def ticket_qr(attendee):
    url = url_for("booking.check_ticket", code=attendee.code, _external=True)
    return segno.make(url, error="m").svg_inline(scale=4, border=2, dark="#1A1423")


@bp.route("/bookings/<ref>")
@login_required
def show(ref):
    booking = own_booking_or_404(ref)
    e = get_event_or_404(booking.event_slug)
    return render_template("booking/booking.html", b=booking, e=e, qr=ticket_qr)


@bp.route("/bookings/<ref>/cancel", methods=["POST"])
@login_required
def cancel(ref):
    booking = own_booking_or_404(ref)
    e = get_event_or_404(booking.event_slug)
    # Free registrations can be cancelled any time before the event. Paid refunds follow
    # the organizer's policy and are handled by them until refunds are built.
    if booking.status != "confirmed" or booking.total > 0 or e.is_past():
        abort(400)
    booking.status = "cancelled"
    db.session.commit()
    flash("Registration cancelled. Your seat is free for someone else.")
    return redirect(url_for("booking.tickets"))


@bp.route("/tickets")
@login_required
def tickets():
    s = store()
    rows = (Booking.query.filter(Booking.user_id == g.user.id, Booking.status != "pending")
            .order_by(Booking.created_at.desc()).all())
    pending = Booking.query.filter(Booking.user_id == g.user.id, Booking.status == "pending",
                                   Booking.created_at > utcnow() - PAYMENT_HOLD).all()
    items = [(b, s.get(b.event_slug)) for b in rows if s.get(b.event_slug)]
    upcoming = sorted([(b, e) for b, e in items if not e.is_past() and b.status == "confirmed"], key=lambda x: x[1].start)
    past = [(b, e) for b, e in items if e.is_past() or b.status == "cancelled"]
    return render_template("booking/tickets.html", upcoming=upcoming, past=past,
                           pending=[(b, s.get(b.event_slug)) for b in pending if s.get(b.event_slug)])


@bp.route("/t/<code>")
def check_ticket(code):
    """What the QR code opens. Shows only whether the ticket is valid, and a first name."""
    attendee = Attendee.query.filter_by(code=code).first()
    if attendee is None:
        return render_template("booking/check.html", valid=False, a=None, e=None), 404
    e = store().get(attendee.booking.event_slug)
    valid = attendee.booking.status == "confirmed"
    return render_template("booking/check.html", valid=valid, a=attendee, e=e)


@bp.route("/events/<slug>/notify", methods=["GET", "POST"])
def notify(slug):
    e = get_event_or_404(slug)
    done = False
    error = None
    name = request.form.get("name", g.user.name if g.user else "")
    phone_raw = request.form.get("phone", g.user.phone[3:] if g.user else "")
    if request.method == "POST":
        phone = normalize_phone(phone_raw)
        if not phone:
            error = "Enter a 10-digit Indian mobile number."
        else:
            if not WaitlistEntry.query.filter_by(event_slug=slug, phone=phone).first():
                db.session.add(WaitlistEntry(event_slug=slug, phone=phone, name=name.strip()[:120]))
                db.session.commit()
            done = True
    return render_template("booking/notify.html", e=e, done=done, error=error, name=name, phone=phone_raw)


# ---- Saved events
@bp.route("/saved")
@login_required
def saved():
    s = store()
    rows = SavedEvent.query.filter_by(user_id=g.user.id).order_by(SavedEvent.created_at.desc()).all()
    events = [s.get(r.event_slug) for r in rows if s.get(r.event_slug)]
    return render_template("booking/saved.html", upcoming=[e for e in events if not e.is_past()],
                           past=[e for e in events if e.is_past()])


@bp.route("/api/saved", methods=["POST"])
def api_saved():
    """Save or unsave. Body: {"slugs": [...], "saved": true|false}. Guests keep saves in the browser."""
    if g.user is None:
        return jsonify(error="sign-in required"), 401
    data = request.get_json(silent=True) or {}
    s = store()
    slugs = [x for x in data.get("slugs", []) if isinstance(x, str) and s.get(x)][:200]
    for slug in slugs:
        row = SavedEvent.query.filter_by(user_id=g.user.id, event_slug=slug).first()
        if data.get("saved", True) and row is None:
            db.session.add(SavedEvent(user_id=g.user.id, event_slug=slug))
        elif not data.get("saved", True) and row is not None:
            db.session.delete(row)
    db.session.commit()
    return jsonify(saved=[r.event_slug for r in SavedEvent.query.filter_by(user_id=g.user.id)])


@bp.app_template_global()
def saved_slugs():
    if g.get("user") is None:
        return []
    return [r.event_slug for r in SavedEvent.query.filter_by(user_id=g.user.id)]


@bp.app_template_filter("ist")
def ist(dt, fmt="%d %b %Y, %-I:%M %p"):
    """Show a stored UTC time in Indian time."""
    from datetime import timezone
    return dt.replace(tzinfo=timezone.utc).astimezone(IST).strftime(fmt) if isinstance(dt, datetime) else ""
