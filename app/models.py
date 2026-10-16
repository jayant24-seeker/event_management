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
    cancelled_at = db.Column(db.DateTime, nullable=True)
    refund_amount = db.Column(db.Integer, nullable=True)  # rupees sent back when cancelled

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


class Follow(db.Model):
    """A person following an organizer, to see their new events first."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    organizer_slug = db.Column(db.String(80), db.ForeignKey("organizer.slug"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "organizer_slug"),)


class Review(db.Model):
    """A star rating and a few words from someone who went. One per person per event."""
    id = db.Column(db.Integer, primary_key=True)
    event_slug = db.Column(db.String(120), db.ForeignKey("event.slug"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)  # None for imported reviews
    name = db.Column(db.String(120), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1 to 5
    text = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "event_slug"),)


def rating_summary(event_slugs):
    """{"avg": 4.6, "count": 38, "stars": {5: 30, 4: 6, ...}} over these events, or None if no reviews."""
    if not event_slugs:
        return None
    rows = (db.session.query(Review.rating, func.count(Review.id))
            .filter(Review.event_slug.in_(list(event_slugs))).group_by(Review.rating).all())
    count = sum(n for _, n in rows)
    if not count:
        return None
    stars = {k: 0 for k in range(5, 0, -1)}
    stars.update(dict(rows))
    return {"avg": round(sum(r * n for r, n in rows) / count, 1), "count": count, "stars": stars}


class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    reply_to = db.Column(db.String(200), nullable=False)  # phone or email
    topic = db.Column(db.String(30), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class WaitlistEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_slug = db.Column(db.String(120), db.ForeignKey("event.slug"), nullable=False, index=True)
    phone = db.Column(db.String(15), nullable=False)
    name = db.Column(db.String(120), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    notified_at = db.Column(db.DateTime, nullable=True)  # texted that seats opened up
    __table_args__ = (UniqueConstraint("event_slug", "phone"),)


def add_missing_columns():
    """Add nullable columns that newer code expects to tables made by older code.
    A stand-in for real migrations (Alembic) while the schema only grows."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    for table in db.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        have = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in have and column.nullable:
                ddl = column.type.compile(dialect=db.engine.dialect)
                with db.engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl}'))


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
