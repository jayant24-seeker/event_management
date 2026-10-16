from datetime import datetime

import pytest

from app import create_app
from app.events import IST, EventStore, date_window, problems

# Fixed "today" so tests don't change as real dates pass.
TODAY = datetime(2026, 10, 16, 12, 0, tzinfo=IST)


@pytest.fixture
def store():
    return EventStore()


def test_all_dummy_events_pass_publish_checks(store):
    assert store.invalid == {}
    assert len(store.events) == 16


def test_upcoming_and_past_are_split_and_sorted(store):
    up, past = store.upcoming(TODAY), store.past(TODAY)
    assert [e.slug for e in past] == ["tricity-half-marathon-2026", "jaipur-blue-pottery-workshop", "kota-standup-night"]
    assert all(not e.is_past(TODAY) for e in up)
    assert [e.start for e in up] == sorted(e.start for e in up)


def test_badges(store):
    assert ("Sold out", "soldout") in store.get("jodhpur-blue-city-cyclothon").badges(TODAY)
    assert ("Selling fast", "hot") in store.get("jaipur-night-run-2026").badges(TODAY)
    assert ("Free", "free") in store.get("chandigarh-startup-mixer").badges(TODAY)
    assert store.get("kota-standup-night").badges(TODAY) == [("Event ended", "muted")]


def test_price_from_skips_sold_out_tiers(store):
    assert store.get("jaipur-night-run-2026").price_from == 799


@pytest.mark.parametrize("bad", ["Route: Final route race one month ago", "TBD", "Lorem ipsum"])
def test_placeholder_text_blocks_publish(store, bad):
    raw = dict(store.get("jaipur-night-run-2026").raw, about=bad)
    assert any("placeholder" in p for p in problems(raw))


def test_blank_venue_field_blocks_publish(store):
    raw = dict(store.get("jaipur-night-run-2026").raw, venue={"name": "", "address": "x"})
    assert "venue 'name' is required" in problems(raw)


def test_search_and_filters(store):
    assert [e.slug for e in store.search("night run", at=TODAY)] == ["jaipur-night-run-2026"]
    assert "amer-hills-trail-ultra" in [e.slug for e in store.search("desert stride", at=TODAY)]  # organizer name
    assert {e.city for e in store.search(city="Kota", at=TODAY)} == {"Kota"}
    assert all(e.price_from <= 300 for e in store.search(max_price=300, at=TODAY))
    assert [e.slug for e in store.search(when="past", category="Comedy", at=TODAY)] == ["kota-standup-night"]


def test_counts_and_suggest(store):
    cities = dict(store.counts("city", TODAY))
    assert cities["Jaipur"] == 2  # the past pottery workshop isn't counted
    assert "Kota" in cities
    found = store.suggest("ja", at=TODAY)
    slugs = [e.slug for e in found["events"]]
    assert slugs[0] == "jaipur-night-run-2026"  # title starts with the query, so it ranks first
    assert "amer-hills-trail-ultra" in slugs
    assert found["cities"] == ["Jaipur"]
    assert store.suggest("j", at=TODAY)["events"] == []  # too short to search


def test_home_and_search_pages():
    client = create_app().test_client()
    home = client.get("/").get_data(as_text=True)
    assert "data-hero-slide" in home and "Find something to do" in home
    assert "Kota Stand-up Night" not in home  # past events stay off the homepage
    page = client.get("/events?q=comedy&when=past").get_data(as_text=True)
    assert "Kota Stand-up Night" in page
    data = client.get("/api/suggest?q=surat").get_json()
    assert data["events"][0]["url"] == "/events/surat-street-food-fest"
    assert data["cities"][0]["url"] == "/events?city=Surat"


def test_pages_render():
    client = create_app().test_client()
    assert client.get("/styleguide").status_code == 200
    assert client.get("/events/jaipur-night-run-2026").status_code == 200
    assert client.get("/events/nope").status_code == 404


def test_inr_format():
    app = create_app()
    assert app.jinja_env.filters["inr"](150000) == "₹1,50,000"
    assert app.jinja_env.filters["inr"](799) == "₹799"


def test_date_window():
    # TODAY is Friday 16 Oct 2026, noon.
    start, end = date_window("weekend", TODAY)
    assert (start.day, end.day) == (17, 19)
    assert date_window("week", TODAY)[1].day == 19
    assert date_window("month", TODAY)[1].month == 11
    assert date_window("any", TODAY) is None
    sunday = datetime(2026, 10, 18, 9, 0, tzinfo=IST)
    assert date_window("weekend", sunday) == (sunday, datetime(2026, 10, 19, tzinfo=IST))


def test_date_and_price_filters(store):
    month = [e.slug for e in store.search(date="month", at=TODAY)]
    assert month == ["sharad-purnima-garba-night", "chandigarh-startup-mixer"]
    assert all(e.is_free for e in store.search(price="free", at=TODAY))
    assert not any(e.is_free for e in store.search(price="paid", at=TODAY))
    assert all(e.price_from <= 500 for e in store.search(price="u500", at=TODAY))
    popular = store.search(sort="popular", at=TODAY)
    assert popular[0].sold_ratio >= popular[-1].sold_ratio


def test_registration_closed_and_online_badges(store):
    run = store.get("amer-hills-trail-ultra")
    after_close = datetime(2026, 11, 25, tzinfo=IST)
    assert run.registration_open(TODAY)
    assert not run.registration_open(after_close)
    assert ("Registration closed", "muted") in run.badges(after_close)
    assert ("Online", "muted") in store.get("race-day-nutrition-masterclass").badges(TODAY)


def test_organizer_is_attached_and_required(store):
    assert store.get("amer-hills-trail-ultra").org["name"] == "Desert Stride Events"
    assert {e.slug for e in store.by_organizer("sahitya-sangam")} >= {"deepotsav-kavi-sammelan", "pushkar-sunrise-yoga"}
    raw = dict(store.get("jaipur-night-run-2026").raw, organizer="")
    assert "'organizer' is required" in problems(raw)


def test_similar_prefers_same_category(store):
    similar = store.similar(store.get("jaipur-night-run-2026"), at=TODAY)
    assert similar[0].category == "Running"
    assert all(e.slug != "jaipur-night-run-2026" for e in similar)


def test_explore_page_filters_and_tabs():
    client = create_app().test_client()
    page = client.get("/events?city=Jaipur").get_data(as_text=True)
    assert "Events in Jaipur" in page
    assert "Jaipur Night Run 2026" in page and "Surat Street Food Fest" not in page
    past = client.get("/events?when=past").get_data(as_text=True)
    assert "Tricity Half Marathon 2026" in past and "Amer Hills Trail Ultra" not in past
    # Unknown filter values are ignored instead of erroring.
    assert client.get("/events?date=someday&sort=weird&price=x&page=99").status_code == 200
    empty = client.get("/events?q=zzzz").get_data(as_text=True)
    assert "No events match" in empty and "Popular right now" in empty
