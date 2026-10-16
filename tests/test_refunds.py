from datetime import datetime, timedelta

from app.events import IST, EventStore, parse_refund_tiers
from app.models import Attendee, Booking, User, db
from test_booking import app, client, post, sign_in, text  # noqa: F401  (fixtures)


def test_refund_rules_are_read_from_the_policy_text():
    assert parse_refund_tiers("Full refund up to 14 days before the race. 50% refund up to 7 days before.") == [(336, 100), (168, 50)]
    assert parse_refund_tiers("Refunds up to 48 hours before the event.") == [(48, 100)]
    # Vague or negative wording never turns into an online refund.
    for vague in ("No refunds.", "Full refund until registration closes.", "No refunds after 14 days before race day.", ""):
        assert parse_refund_tiers(vague) == []


def test_refund_percent_steps_down_as_the_event_nears():
    e = EventStore().get("jaipur-night-run-2026")
    assert e.refund_percent(e.start - timedelta(days=20)) == 100
    assert e.refund_percent(e.start - timedelta(days=10)) == 50
    assert e.refund_percent(e.start - timedelta(days=2)) == 0
    # The organizer's own rules beat the text.
    e.raw["refund_tiers"] = [{"hours": 48, "percent": 25}]
    assert e.refund_percent(e.start - timedelta(days=20)) == 25
    e.raw["refund_tiers"] = []
    assert e.refund_percent(e.start - timedelta(days=20)) == 0


def paid_booking(app, slug, total=1000):
    with app.app_context():
        user = User.query.filter_by(phone="+919876543210").one()
        b = Booking(user_id=user.id, event_slug=slug, status="confirmed", subtotal=total, payment_ref="TEST-1")
        b.attendees.append(Attendee(ticket_name="10K", price=total, details={"name": "Asha"}))
        db.session.add(b)
        db.session.commit()
        return b.ref


def test_cancel_paid_booking_with_refund(app, client):
    sign_in(client)
    ref = paid_booking(app, "jaipur-night-run-2026")
    page = text(client.get(f"/bookings/{ref}"))
    assert "Cancel and get ₹1,000 back" in page
    res = post(client, f"/bookings/{ref}/cancel")
    assert res.status_code == 302
    with app.app_context():
        b = Booking.query.filter_by(ref=ref).one()
        assert b.status == "cancelled" and b.refund_amount == 1000 and b.cancelled_at
    assert "Refund of ₹1,000 sent" in text(client.get(f"/bookings/{ref}"))
    assert post(client, f"/bookings/{ref}/cancel").status_code == 400  # only once


def test_no_online_cancel_when_policy_has_no_refunds(app, client):
    sign_in(client)
    ref = paid_booking(app, "sharad-purnima-garba-night")
    assert "isn't available" in text(client.get(f"/bookings/{ref}"))
    assert post(client, f"/bookings/{ref}/cancel").status_code == 400


def test_old_databases_get_new_columns(app):
    from sqlalchemy import inspect
    with app.app_context():
        assert "refund_amount" in {c["name"] for c in inspect(db.engine).get_columns("booking")}
