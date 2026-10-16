from app.models import Booking, Review, User, db
from test_booking import app, client, post, sign_in, text  # noqa: F401  (fixtures)

PAST = "kota-standup-night"


def give_ticket(app, phone="+919876543210", slug=PAST):
    with app.app_context():
        user = User.query.filter_by(phone=phone).one()
        db.session.add(Booking(user_id=user.id, event_slug=slug, status="confirmed"))
        db.session.commit()


def test_past_event_shows_demo_reviews_and_rating(client):
    page = text(client.get(f"/events/{PAST}"))
    assert "What people said" in page and "Ishaan P." in page and "2 reviews" in page
    # Organizer profile and their other events show the overall rating.
    assert "(2 reviews)" in text(client.get("/organizers/laugh-local"))


def test_only_attendees_can_review(app, client):
    sign_in(client)
    assert "How was it?" not in text(client.get(f"/events/{PAST}"))
    assert post(client, f"/events/{PAST}/review", rating="5").status_code == 403
    give_ticket(app)
    assert "How was it?" in text(client.get(f"/events/{PAST}"))
    res = post(client, f"/events/{PAST}/review", rating="4", text="Fun night out.")
    assert res.status_code == 302
    page = text(client.get(f"/events/{PAST}"))
    assert "Asha V." in page and "Fun night out." in page and "3 reviews" in page and "Update review" in page
    # Posting again edits the same review.
    post(client, f"/events/{PAST}/review", rating="5", text="Changed my mind, great.")
    with app.app_context():
        mine = Review.query.filter(Review.user_id.isnot(None)).all()
        assert len(mine) == 1 and mine[0].rating == 5


def test_review_rules(app, client):
    sign_in(client)
    give_ticket(app)
    post(client, f"/events/{PAST}/review", rating="9")
    with app.app_context():
        assert Review.query.filter(Review.user_id.isnot(None)).count() == 0
    # Upcoming events can't be reviewed yet, even with a ticket.
    give_ticket(app, slug="deepotsav-kavi-sammelan")
    assert post(client, "/events/deepotsav-kavi-sammelan/review", rating="5").status_code == 403
