"""Database tables. SQLite in development; any SQLAlchemy database in production.

Events keep their flexible details (schedule, FAQs, kit...) in one JSON column, so the
Event wrapper in events.py and every template work the same as with the JSON files.
"""
import secrets
import string
from datetime import datetime, timedelta, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON, UniqueConstraint, func, or_

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def short_code(n=8):
    # No 0/O or 1/I, so codes are easy to read out at a gate.
    alphabet = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1I")
    return "".join(secrets.choice(alphabet) for _ in range(n))


class Organizer(db.Model):
    slug = db.Column(db.String(80), primary_key=True)
    data = db.Column(JSON, nullable=False)  # name, city, since, verified, about, socials


class EventRow(db.Model):
    __tablename__ = "event"
    slug = db.Column(db.String(120), primary_key=True)
    organizer_slug = db.Column(db.String(80), db.ForeignKey("organizer.slug"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="published")  # published | draft
    data = db.Column(JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(15), unique=True, nullable=False)  # +91XXXXXXXXXX
    name = db.Column(db.String(120), nullable=False, default="")
    email = db.Column(db.String(200), nullable=False, default="")
    organizer_slug = db.Column(db.String(80), db.ForeignKey("organizer.slug"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    @property
    def first_name(self):
        return (self.name or "").split(" ")[0] or "there"


class OtpCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(15), nullable=False, index=True)
    code_hash = db.Column(db.String(200), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    used = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_slug = db.Column(db.String(120), db.ForeignKey("event.slug"), nullable=False, index=True)
    code = db.Column(db.String(30), nullable=False)
    percent_off = db.Column(db.Integer, nullable=False, default=0)
    max_uses = db.Column(db.Integer, nullable=True)
    valid_until = db.Column(db.DateTime, nullable=True)  # stored in IST, no timezone
    __table_args__ = (UniqueConstraint("event_slug", "code"),)


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ref = db.Column(db.String(12), unique=True, nullable=False, default=lambda: short_code(8))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    event_slug = db.Column(db.String(120), db.ForeignKey("event.slug"), nullable=False, index=True)
    # pending = waiting for payment, confirmed = paid or free, cancelled = seats released
    status = db.Column(db.String(20), nullable=False, default="pending")
    subtotal = db.Column(db.Integer, nullable=False, default=0)
    discount = db.Column(db.Integer, nullable=False, default=0)
    coupon_code = db.Column(db.String(30), nullable=True)
    payment_ref = db.Column(db.String(60), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    confirmed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref="bookings")
    attendees = db.relationship("Attendee", backref="booking", cascade="all, delete-orphan", order_by="Attendee.id")

    @property
    def total(self):
        return max(self.subtotal - self.discount, 0)


class Attendee(db.Model):
    """One ticket = one attendee. The QR code on the ticket carries `code`."""
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), nullable=False, index=True)
    ticket_name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    code = db.Column(db.String(16), unique=True, nullable=False, default=lambda: short_code(10))
    details = db.Column(JSON, nullable=False, default=dict)  # name, gender, age, tshirt, emergency...
    checked_in_at = db.Column(db.DateTime, nullable=True)

    @property
    def name(self):
        return self.details.get("name", "")


class SavedEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    event_slug = db.Column(db.String(120), db.ForeignKey("event.slug"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "event_slug"),)


class WaitlistEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_slug = db.Column(db.String(120), db.ForeignKey("event.slug"), nullable=False, index=True)
    phone = db.Column(db.String(15), nullable=False)
    name = db.Column(db.String(120), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    __table_args__ = (UniqueConstraint("event_slug", "phone"),)


# A pending booking holds its seats this long while the person pays.
PAYMENT_HOLD = timedelta(minutes=15)


def seats_taken(event_slug=None):
    """{(event_slug, ticket_name): seats} for confirmed bookings and recent pending ones."""
    q = (
        db.session.query(Booking.event_slug, Attendee.ticket_name, func.count(Attendee.id))
        .join(Attendee, Attendee.booking_id == Booking.id)
        .filter(or_(Booking.status == "confirmed",
                    (Booking.status == "pending") & (Booking.created_at > utcnow() - PAYMENT_HOLD)))
        .group_by(Booking.event_slug, Attendee.ticket_name)
    )
    if event_slug:
        q = q.filter(Booking.event_slug == event_slug)
    return {(slug, name): n for slug, name, n in q}
