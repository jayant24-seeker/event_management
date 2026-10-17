import html

import pytest

from app import create_app
from app.models import Attendee, Booking, OtpCode, User, WaitlistEntry, db

CSRF = "test-token"


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "MEDIA_ROOT": str(tmp_path)})


@pytest.fixture
def client(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s["csrf"] = CSRF
    return c


def text(res):
    return html.unescape(res.get_data(as_text=True))


def post(client, url, **data):
    return client.post(url, data=dict(data, csrf_token=CSRF))


def sign_in(client, phone="9876543210", name="Asha Verma"):
    post(client, "/login", phone=phone)
    with client.session_transaction() as s:
        code = s["dev_otp"]
    res = post(client, "/login/verify", code=code)
    if "/account" in res.headers.get("Location", ""):
        post(client, "/account", name=name, email="asha@example.com")
    return res


def test_post_without_csrf_is_rejected(client):
    assert client.post("/login", data={"phone": "9876543210"}).status_code == 400


def test_otp_sign_in_creates_user_and_asks_for_name(app, client):
    res = post(client, "/login", phone="+91 98765 43210")
    assert res.status_code == 302 and "/login/verify" in res.headers["Location"]
    wrong = post(client, "/login/verify", code="000000")
    assert "isn't right" in text(wrong)
    with client.session_transaction() as s:
        code = s["dev_otp"]
    res = post(client, "/login/verify", code=code)
    assert "/account" in res.headers["Location"]
    with app.app_context():
        assert User.query.filter_by(phone="+919876543210").count() == 1
        assert OtpCode.query.first().used


def test_bad_phone_and_rate_limit(client):
    assert "10-digit" in post(client, "/login", phone="12345").get_data(as_text=True)
    for _ in range(5):
        post(client, "/login", phone="9000000001")
    assert "Too many codes" in post(client, "/login", phone="9000000001").get_data(as_text=True)


def test_checkout_needs_sign_in(client):
    res = client.get("/events/deepotsav-kavi-sammelan/register?t0=2")
    assert res.status_code == 302 and "/login?next=" in res.headers["Location"]


def test_free_booking_is_confirmed_and_can_be_cancelled(app, client):
    sign_in(client)
    page = client.get("/events/deepotsav-kavi-sammelan/register?t0=2").get_data(as_text=True)
    assert "Ticket 2" in page and "Confirm registration" in page
    # Missing details are reported, nothing is saved.
    res = post(client, "/events/deepotsav-kavi-sammelan/register", t0="2", action="book", **{"a0-name": "Asha", "a0-age": "30"})
    assert "Ticket 2: full name is required" in res.get_data(as_text=True)
    res = post(client, "/events/deepotsav-kavi-sammelan/register", t0="2", action="book",
               **{"a0-name": "Asha", "a0-age": "30", "a1-name": "Ravi", "a1-age": "34"})
    assert res.status_code == 302 and "/bookings/" in res.headers["Location"]
    ticket_page = client.get(res.headers["Location"]).get_data(as_text=True)
    assert "You're going to" in html.unescape(ticket_page) and "<svg" in ticket_page  # QR codes
    with app.app_context():
        b = Booking.query.one()
        assert b.status == "confirmed" and len(b.attendees) == 2
        code, ref = b.attendees[0].code, b.ref
    assert "Valid ticket" in client.get(f"/t/{code}").get_data(as_text=True)
    # Seats sold on the site show up on the event page.
    assert "514" in client.get("/events/deepotsav-kavi-sammelan").get_data(as_text=True)
    post(client, f"/bookings/{ref}/cancel")
    with app.app_context():
        assert Booking.query.one().status == "cancelled"
    assert "Not a valid ticket" in client.get(f"/t/{code}").get_data(as_text=True)


def run_details(k):
    return {f"a{k}-name": f"Runner {k}", f"a{k}-gender": "Female", f"a{k}-age": "28", f"a{k}-tshirt": "M",
            f"a{k}-emergency": "Ravi 9876500000"}


def test_paid_booking_with_coupon_and_test_payment(app, client):
    sign_in(client)
    applied = post(client, "/events/amer-hills-trail-ultra/register", t0="1", coupon="earlybird10", action="apply")
    summary = text(applied)
    assert "−₹249" in summary and "₹2,250" in summary
    assert "isn't valid" in text(post(client, "/events/amer-hills-trail-ultra/register", t0="1", coupon="NOPE", action="apply"))
    too_young = post(client, "/events/amer-hills-trail-ultra/register", t0="1", action="book", **dict(run_details(0), **{"a0-age": "14"}))
    assert "minimum age is 16" in too_young.get_data(as_text=True)
    res = post(client, "/events/amer-hills-trail-ultra/register", t0="1", coupon="EARLYBIRD10", action="book", **run_details(0))
    assert "/pay/" in res.headers["Location"]
    ref = res.headers["Location"].rsplit("/", 1)[1]
    with app.app_context():
        b = Booking.query.filter_by(ref=ref).one()
        assert (b.status, b.subtotal, b.discount, b.total) == ("pending", 2499, 249, 2250)
    res = post(client, f"/pay/{ref}", action="pay")
    assert f"/bookings/{ref}" in res.headers["Location"]
    with app.app_context():
        b = Booking.query.filter_by(ref=ref).one()
        assert b.status == "confirmed" and b.payment_ref.startswith("TEST-")


def test_cannot_oversell_last_seats(app, client):
    sign_in(client)
    # Workshop-sized event: shrink the 4K tier to 2 seats left.
    from app.models import EventRow
    with app.app_context():
        row = db.session.get(EventRow, "little-legs-kids-run")
        data = dict(row.data)
        data["tickets"] = [dict(data["tickets"][0], capacity=90, sold=88), data["tickets"][1]]
        row.data = data
        db.session.commit()
    details = {**run_details(0), **run_details(1)}
    for k in (0, 1):
        details[f"a{k}-age"] = "7"
    first = post(client, "/events/little-legs-kids-run/register", t0="2", action="book", **details)
    assert "/pay/" in first.headers["Location"]
    # The two seats are now held for the first booking, so a second can't take them.
    second = client.get("/events/little-legs-kids-run/register?t0=1")
    assert second.status_code == 302


def test_waitlist_and_saved_events(app, client):
    page = post(client, "/events/jodhpur-blue-city-cyclothon/notify", name="Asha", phone="98765 43210")
    assert "You're on the list" in text(page)
    post(client, "/events/jodhpur-blue-city-cyclothon/notify", name="Asha", phone="9876543210")
    with app.app_context():
        assert WaitlistEntry.query.count() == 1  # no duplicates
    assert client.post("/api/saved", json={"slugs": ["jaipur-night-run-2026"]}, headers={"X-CSRF-Token": CSRF}).status_code == 401
    sign_in(client)
    res = client.post("/api/saved", json={"slugs": ["jaipur-night-run-2026", "not-real"], "saved": True}, headers={"X-CSRF-Token": CSRF})
    assert res.get_json()["saved"] == ["jaipur-night-run-2026"]
    assert "Jaipur Night Run 2026" in client.get("/saved").get_data(as_text=True)
    assert "My tickets" in client.get("/tickets").get_data(as_text=True)


def test_other_people_cannot_see_your_booking(app, client):
    sign_in(client)
    res = post(client, "/events/pushkar-sunrise-yoga/register", t0="1", action="book",
               **{"a0-name": "Asha", "a0-gender": "Female", "a0-age": "30"})
    ref = res.headers["Location"].rsplit("/", 1)[1]
    post(client, "/logout")
    with client.session_transaction() as s:
        s["csrf"] = CSRF
    sign_in(client, phone="9123456780", name="Someone Else")
    assert client.get(f"/bookings/{ref}").status_code == 404


def test_group_discount_beats_or_yields_to_codes(app, client):
    from app.models import EventRow

    with app.app_context():
        row = db.session.get(EventRow, "amer-hills-trail-ultra")
        row.data = dict(row.data, group_discount={"min": 3, "percent": 15})
        db.session.commit()
    sign_in(client)
    assert "15% off when you book 3 or more" in text(client.get("/events/amer-hills-trail-ultra"))
    two = text(client.get("/events/amer-hills-trail-ultra/register?t0=2"))
    assert "Add tickets to 3 or more for 15% off" in two
    three = text(client.get("/events/amer-hills-trail-ultra/register?t0=3"))
    assert "Group discount (15% off 3+ tickets)" in three
    # EARLYBIRD10 saves less than 15%, so the group discount stays.
    with_code = text(client.get("/events/amer-hills-trail-ultra/register?t0=3&coupon=EARLYBIRD10"))
    assert "Group discount" in with_code and "isn't needed" in with_code


def test_confirmation_is_texted_and_emailed(app, client, caplog):
    import logging

    sign_in(client)
    with caplog.at_level(logging.INFO):
        post(client, "/events/deepotsav-kavi-sammelan/register", t0="1", action="book", **{"a0-name": "Asha", "a0-age": "30"})
    logs = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("SMS to +919876543210: You're booked for") for m in logs)
    email = next(m for m in logs if m.startswith("Email to asha@example.com"))
    assert "/pass/" in email and "/bookings/" in email and "Asha" in email


def test_waitlist_shows_place_in_line(app, client):
    first = post(client, "/events/jaipur-night-run-2026/notify", name="A", phone="9800000001")
    assert "#1" in text(first)
    second = text(post(client, "/events/jaipur-night-run-2026/notify", name="B", phone="9800000002"))
    assert "#2" in second
    again = text(post(client, "/events/jaipur-night-run-2026/notify", name="A", phone="9800000001"))
    assert "#1" in again  # joining twice keeps your place
