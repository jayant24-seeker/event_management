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


def test_cancelling_a_sold_out_event_texts_the_waitlist(app, client):
    from app.models import EventRow, WaitlistEntry

    sign_in(client)
    ref = paid_booking(app, "jaipur-night-run-2026")
    with app.app_context():
        row = db.session.get(EventRow, "jaipur-night-run-2026")
        data = dict(row.data)
        # Make every tier full, counting the booking above (one 10K seat).
        data["tickets"] = [dict(t, sold=t["capacity"] - (1 if t["name"] == "10K" else 0)) for t in data["tickets"]]
        if not any(t["name"] == "10K" for t in data["tickets"]):
            data["tickets"].append({"name": "10K", "price": 1000, "capacity": 1, "sold": 0})
        row.data = data
        db.session.add_all([WaitlistEntry(event_slug="jaipur-night-run-2026", phone=f"+9198000000{i:02d}") for i in range(5)])
        db.session.commit()
    post(client, f"/bookings/{ref}/cancel")
    with app.app_context():
        told = WaitlistEntry.query.filter(WaitlistEntry.notified_at.isnot(None)).count()
        assert told == 3  # one seat freed: the first three people hear about it


def test_organizer_can_text_the_waitlist(app, client):
    from app.models import WaitlistEntry

    with app.app_context():
        db.session.add(WaitlistEntry(event_slug="jaipur-night-run-2026", phone="+919800000099"))
        db.session.commit()
    sign_in(client, phone="9999999999")
    res = post(client, "/organizer/events/jaipur-night-run-2026/waitlist/notify")
    assert res.status_code == 302
    assert "Texted 1 person" in text(client.get("/organizer/events/jaipur-night-run-2026"))
    post(client, "/organizer/events/jaipur-night-run-2026/waitlist/notify")
    assert "already been texted" in text(client.get("/organizer/events/jaipur-night-run-2026"))


def test_organizer_update_is_texted_and_shown(app, client, caplog):
    import logging

    from app.models import Announcement

    sign_in(client)
    ref = paid_booking(app, "jaipur-night-run-2026")
    with client.session_transaction() as s:
        s.pop("uid")
    sign_in(client, phone="9999999999")
    with caplog.at_level(logging.INFO):
        post(client, "/organizer/events/jaipur-night-run-2026/announce", text="Bib collection moved to Gate 3.")
    assert any("+919876543210" in r.getMessage() and "Gate 3" in r.getMessage() for r in caplog.records)
    assert "Gate 3" in text(client.get("/events/jaipur-night-run-2026"))
    assert "texted to 1" in text(client.get("/organizer/events/jaipur-night-run-2026"))
    post(client, "/organizer/events/jaipur-night-run-2026/announce", text="short")
    for i in range(5):
        post(client, "/organizer/events/jaipur-night-run-2026/announce", text=f"Another update number {i}")
    with app.app_context():
        assert Announcement.query.count() == 3  # 3 a day
    # Other organizers can't post on this event.
    with client.session_transaction() as s:
        s.pop("uid")
    sign_in(client, phone="9811111111", name="Other Org")
    assert post(client, "/organizer/events/jaipur-night-run-2026/announce", text="Hijacked message here").status_code == 302
    with app.app_context():
        assert Announcement.query.count() == 3


def test_reminders_and_review_requests_go_out_once(app, client, caplog):
    import logging

    from app.reminders import send_due

    sign_in(client)
    ref = paid_booking(app, "jaipur-night-run-2026")
    e = EventStore().get("jaipur-night-run-2026")
    with app.test_request_context(), caplog.at_level(logging.INFO):
        assert send_due(at=e.start - timedelta(days=3)) == 0          # too early
        assert send_due(at=e.start - timedelta(hours=20)) == 1        # day before
        assert send_due(at=e.start - timedelta(hours=10)) == 0        # only once
        assert send_due(at=e.end + timedelta(hours=5)) == 1           # review request
        assert send_due(at=e.end + timedelta(hours=6)) == 0
    texts = [r.getMessage() for r in caplog.records if r.getMessage().startswith("SMS to +919876543210")]
    assert "See you tomorrow at Jaipur Night Run 2026" in texts[0] and "How was Jaipur Night Run 2026?" in texts[1]


def test_saved_event_closing_alert(app, client, caplog):
    import logging

    from app.models import SavedEvent
    from app.reminders import send_due

    sign_in(client)
    with app.app_context():
        db.session.add(SavedEvent(user_id=User.query.filter_by(phone="+919876543210").one().id, event_slug="amer-hills-trail-ultra"))
        db.session.commit()
    e = EventStore().get("amer-hills-trail-ultra")
    with app.test_request_context(), caplog.at_level(logging.INFO):
        assert send_due(at=e.reg_closes - timedelta(days=5)) == 0
        assert send_due(at=e.reg_closes - timedelta(hours=30)) == 1
        assert send_due(at=e.reg_closes - timedelta(hours=10)) == 0  # once
    assert any("you saved it" in r.getMessage() for r in caplog.records)
