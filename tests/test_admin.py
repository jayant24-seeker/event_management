from app.models import ContactMessage, EventRow, Organizer, db
from test_booking import app, client, post, sign_in, text  # noqa: F401  (fixtures)

ADMIN = "8888888888"


def test_admin_is_hidden_from_everyone_else(client):
    assert client.get("/admin/").status_code == 302  # sign in first
    sign_in(client)
    assert client.get("/admin/").status_code == 404
    assert post(client, "/admin/events/jaipur-night-run-2026", action="hide").status_code == 404
    assert "/admin" not in text(client.get("/"))


def test_admin_overview_and_actions(app, client):
    with app.app_context():
        db.session.add(ContactMessage(name="Asha", reply_to="9876543210", topic="other", message="Where is my refund?"))
        db.session.commit()
    sign_in(client, phone=ADMIN, name="Staff Member")
    page = text(client.get("/admin/"))
    assert "Ticket revenue" in page and "Jaipur Night Run 2026" in page and "Where is my refund?" in page
    assert 'href="/admin/"' in text(client.get("/"))  # menu link

    post(client, "/admin/events/kota-campus-beats", action="feature")
    post(client, "/admin/events/jaipur-night-run-2026", action="hide")
    post(client, "/admin/organizers/campus-beats", verified="1")
    post(client, "/admin/messages/1")
    with app.app_context():
        assert db.session.get(EventRow, "kota-campus-beats").data["featured"] is True
        assert db.session.get(EventRow, "jaipur-night-run-2026").status == "draft"
        assert db.session.get(Organizer, "campus-beats").data["verified"] is True
        assert db.session.get(ContactMessage, 1).handled_at is not None
    assert client.get("/events/jaipur-night-run-2026").status_code == 404


def test_admin_finds_bookings_and_resends(app, client):
    from app.models import Booking

    sign_in(client)
    post(client, "/events/deepotsav-kavi-sammelan/register", t0="1", action="book", **{"a0-name": "Asha", "a0-age": "30"})
    with app.app_context():
        b = Booking.query.one()
        ref, code = b.ref, b.attendees[0].code
    with client.session_transaction() as s:
        s.pop("uid")
    sign_in(client, phone=ADMIN, name="Staff Member")
    for q in (ref, code.lower(), "98765 43210"):
        assert ref in text(client.get(f"/admin/?q={q}"))
    assert "No booking matches" in text(client.get("/admin/?q=NOPE1234"))
    res = post(client, f"/admin/bookings/{ref}/resend")
    assert res.status_code == 302
    assert "sent again" in text(client.get(res.headers["Location"]))
