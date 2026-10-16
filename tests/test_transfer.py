from app.models import Attendee, db
from test_booking import app, client, post, sign_in, text  # noqa: F401  (fixtures)
from test_refunds import paid_booking


def only_attendee(app, ref):
    with app.app_context():
        a = Attendee.query.one()
        return a.id, a.code


def test_ticket_pass_page(app, client):
    sign_in(client)
    ref = paid_booking(app, "jaipur-night-run-2026")
    _, code = only_attendee(app, ref)
    page = text(client.get(f"/pass/{code}"))  # works without signing in too
    assert "Asha" in page and code in page and "<svg" in page
    assert client.get("/pass/NOPE").status_code == 404
    assert f"/pass/{code}" in text(client.get(f"/bookings/{ref}"))


def test_transfer_changes_name_and_code(app, client):
    sign_in(client)
    ref = paid_booking(app, "jaipur-night-run-2026")
    aid, old_code = only_attendee(app, ref)
    assert post(client, f"/bookings/{ref}/tickets/{aid}/transfer", name="R").status_code == 302  # too short: no change
    assert only_attendee(app, ref)[1] == old_code
    post(client, f"/bookings/{ref}/tickets/{aid}/transfer", name="Ravi Kumar")
    _, new_code = only_attendee(app, ref)
    assert new_code != old_code
    assert client.get(f"/pass/{old_code}").status_code == 404
    with app.app_context():
        a = db.session.get(Attendee, aid)
        assert a.name == "Ravi Kumar" and a.details["transferred_from"] == "Asha"


def test_transfer_rules(app, client):
    sign_in(client)
    ref = paid_booking(app, "jaipur-night-run-2026")
    aid, _ = only_attendee(app, ref)
    with client.session_transaction() as s:
        s.pop("uid")
    sign_in(client, phone="9811111112", name="Someone Else")
    assert post(client, f"/bookings/{ref}/tickets/{aid}/transfer", name="Thief").status_code == 404
