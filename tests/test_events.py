from datetime import datetime

import pytest

from app import create_app
from app.events import IST, EventStore, problems

# Fixed "today" so tests don't change as real dates pass.
TODAY = datetime(2026, 10, 16, 12, 0, tzinfo=IST)


@pytest.fixture
def store():
    return EventStore()


def test_all_dummy_events_pass_publish_checks(store):
    assert store.invalid == {}
    assert len(store.events) == 8


def test_upcoming_and_past_are_split_and_sorted(store):
    up, past = store.upcoming(TODAY), store.past(TODAY)
    assert [e.slug for e in past] == ["jaipur-blue-pottery-workshop", "kota-standup-night"]
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
    assert [e.slug for e in store.search("marathon", at=TODAY)] == ["jaipur-night-run-2026"]
    assert {e.city for e in store.search(city="Kota", at=TODAY)} == {"Kota"}
    assert all(e.price_from <= 300 for e in store.search(max_price=300, at=TODAY))
    assert [e.slug for e in store.search(when="past", category="Comedy", at=TODAY)] == ["kota-standup-night"]


def test_pages_render():
    client = create_app().test_client()
    assert client.get("/styleguide").status_code == 200
    assert client.get("/events/jaipur-night-run-2026").status_code == 200
    assert client.get("/events/nope").status_code == 404


def test_inr_format():
    app = create_app()
    assert app.jinja_env.filters["inr"](150000) == "₹1,50,000"
    assert app.jinja_env.filters["inr"](799) == "₹799"
