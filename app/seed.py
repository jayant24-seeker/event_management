"""Fill an empty database from data/*.json, plus a few demo coupons.

    flask --app run seed --reset    # wipe and reload the demo data
"""
import json
from datetime import datetime

import click

from .events import DATA_FILE, ORGANIZERS_FILE
from .models import Coupon, EventRow, Organizer, Review, User, db

DEMO_ORGANIZER_PHONE = "+919999999999"

# (event, code, % off, max uses, valid until in IST)
DEMO_COUPONS = [
    ("amer-hills-trail-ultra", "EARLYBIRD10", 10, 200, "2026-11-10T23:59"),
    ("jaipur-night-run-2026", "PINKCITY15", 15, 100, None),
    ("little-legs-kids-run", "SIBLING20", 20, None, None),
]


# Reviews from past editions, so past event pages and organizer ratings aren't empty in the demo.
DEMO_REVIEWS = [
    ("tricity-half-marathon-2026", "Harpreet K.", 5, "Well marked route, water every 2 km and the medal is lovely. Will run again."),
    ("tricity-half-marathon-2026", "Rohit S.", 4, "Great crowd support near Sukhna Lake. Bag counter was slow after the finish."),
    ("tricity-half-marathon-2026", "Neha G.", 5, "My first half marathon. Pacers were friendly and kept us on time."),
    ("jaipur-blue-pottery-workshop", "Ananya M.", 5, "Small batch, patient teacher, and we took home two pieces each."),
    ("jaipur-blue-pottery-workshop", "Vikram R.", 4, "Loved it. Would have liked a little more time for painting."),
    ("kota-standup-night", "Ishaan P.", 5, "Laughed for two hours straight. The Kota coaching jokes hit home."),
    ("kota-standup-night", "Sakshi T.", 3, "Good comics, but the show started 40 minutes late."),
]


def load_reviews():
    slugs = {r.slug for r in EventRow.query}
    for slug, name, rating, text in DEMO_REVIEWS:
        if slug in slugs:
            db.session.add(Review(event_slug=slug, name=name, rating=rating, text=text))
    db.session.commit()


def load_json():
    events = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    organizers = json.loads(ORGANIZERS_FILE.read_text(encoding="utf-8"))
    for o in organizers:
        db.session.add(Organizer(slug=o["slug"], data={k: v for k, v in o.items() if k != "slug"}))
    for e in events:
        db.session.add(EventRow(slug=e["slug"], organizer_slug=e["organizer"], status="published", data=e))
    db.session.flush()
    # Demo organizer login: sign in with 99999 99999 to see the Pink Pace Runners Club dashboard.
    db.session.add(User(phone=DEMO_ORGANIZER_PHONE, name="Demo Organizer", organizer_slug="pink-pace-runners"))
    for slug, code, pct, max_uses, until in DEMO_COUPONS:
        db.session.add(Coupon(event_slug=slug, code=code, percent_off=pct, max_uses=max_uses,
                              valid_until=datetime.fromisoformat(until) if until else None))
    db.session.commit()
    load_reviews()
    return len(events), len(organizers)


def seed_if_empty():
    if db.session.query(Organizer).first() is None:
        load_json()
    elif db.session.query(Review).first() is None:
        load_reviews()  # databases made before reviews existed


def register_cli(app):
    @app.cli.command("seed")
    @click.option("--reset", is_flag=True, help="Delete everything (bookings and users too) and reload.")
    def seed_command(reset):
        """Load the demo events and organizers."""
        if reset:
            db.drop_all()
            db.create_all()
        if db.session.query(Organizer).first() is not None:
            click.echo("Database already has data. Use --reset to reload.")
            return
        n_events, n_orgs = load_json()
        click.echo(f"Loaded {n_events} events and {n_orgs} organizers.")
