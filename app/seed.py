"""Fill an empty database from data/*.json, plus a few demo coupons.

    flask --app run seed --reset    # wipe and reload the demo data
"""
import json
from datetime import datetime

import click

from .events import DATA_FILE, ORGANIZERS_FILE
from .models import Coupon, EventRow, Organizer, db

# (event, code, % off, max uses, valid until in IST)
DEMO_COUPONS = [
    ("amer-hills-trail-ultra", "EARLYBIRD10", 10, 200, "2026-11-10T23:59"),
    ("jaipur-night-run-2026", "PINKCITY15", 15, 100, None),
    ("little-legs-kids-run", "SIBLING20", 20, None, None),
]


def load_json():
    events = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    organizers = json.loads(ORGANIZERS_FILE.read_text(encoding="utf-8"))
    for o in organizers:
        db.session.add(Organizer(slug=o["slug"], data={k: v for k, v in o.items() if k != "slug"}))
    for e in events:
        db.session.add(EventRow(slug=e["slug"], organizer_slug=e["organizer"], status="published", data=e))
    db.session.flush()
    for slug, code, pct, max_uses, until in DEMO_COUPONS:
        db.session.add(Coupon(event_slug=slug, code=code, percent_off=pct, max_uses=max_uses,
                              valid_until=datetime.fromisoformat(until) if until else None))
    db.session.commit()
    return len(events), len(organizers)


def seed_if_empty():
    if db.session.query(Organizer).first() is None:
        load_json()


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
