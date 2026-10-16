from app.models import Follow
from test_booking import app, client, post, sign_in, text  # noqa: F401  (fixtures)

ORG = "pink-pace-runners"


def test_guest_follow_goes_to_sign_in(client):
    res = post(client, f"/organizers/{ORG}/follow", follow="1")
    assert res.status_code == 302 and "/login" in res.headers["Location"]


def test_follow_shows_events_on_homepage_and_unfollow(app, client):
    sign_in(client)
    assert "From organizers you follow" not in text(client.get("/"))
    res = post(client, f"/organizers/{ORG}/follow", follow="1", next="/")
    assert res.headers["Location"] == "/"
    post(client, f"/organizers/{ORG}/follow", follow="1")  # twice is harmless
    with app.app_context():
        assert Follow.query.count() == 1
    home = text(client.get("/"))
    assert "From organizers you follow" in home
    profile = text(client.get(f"/organizers/{ORG}"))
    assert "1 follower" in profile and "Following" in profile
    post(client, f"/organizers/{ORG}/follow", follow="0")
    with app.app_context():
        assert Follow.query.count() == 0


def test_follow_rejects_unknown_organizer_and_outside_redirects(client):
    sign_in(client)
    assert post(client, "/organizers/nobody/follow").status_code == 404
    res = post(client, f"/organizers/{ORG}/follow", next="https://evil.com")
    assert res.headers["Location"] == "/"


def test_dashboard_shows_followers(client):
    sign_in(client, phone="9999999999")
    assert "Followers" in text(client.get("/organizer/"))
