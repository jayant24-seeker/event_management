"""Fill an empty database from data/*.json, plus a few demo coupons.

    flask --app run seed --reset    # wipe and reload the demo data
"""
import json
import random
from datetime import datetime, timedelta

import click
from flask import current_app

from .events import DATA_FILE, ORGANIZERS_FILE
from .models import Attendee, Booking, Coupon, EventRow, Organizer, Review, User, db, utcnow

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


# Demo bookings so the organizer dashboard has sales to chart: (event, bookings, days of selling, share checked in)
DEMO_SALES = [("jaipur-night-run-2026", 42, 30, 0.0), ("tricity-half-marathon-2026", 36, 40, 0.88),
              ("little-legs-kids-run", 14, 18, 0.0)]
DEMO_BUYER_PREFIX = "+91900000"
FIRST = ["Aarav", "Diya", "Kabir", "Meera", "Rohan", "Isha", "Arjun", "Tara", "Vivaan", "Anika", "Dev", "Riya"]
LAST = ["Sharma", "Mehta", "Singh", "Joshi", "Gupta", "Rathore", "Kaur", "Patel", "Verma", "Chauhan"]


def load_demo_sales():
    rng = random.Random(7)  # same demo data every time
    now = utcnow()
    for slug, n, span, checked_share in DEMO_SALES:
        row = db.session.get(EventRow, slug)
        if row is None:
            continue
        start = datetime.fromisoformat(row.data["start"]) - timedelta(hours=5, minutes=30)  # IST -> UTC
        end_selling = min(now, start)
        tiers = [t for t in row.data["tickets"] if t["capacity"] - t.get("sold", 0) > 5]
        for i in range(n):
            # More sales close to the end of the window, like real events.
            when = end_selling - timedelta(days=span * (1 - rng.random() ** 0.6), hours=rng.randint(0, 12))
            phone = f"{DEMO_BUYER_PREFIX}{rng.randint(10000, 99999)}"
            user = User.query.filter_by(phone=phone).first() or User(phone=phone, name=f"{rng.choice(FIRST)} {rng.choice(LAST)}")
            db.session.add(user)
            t = rng.choice(tiers)
            qty = rng.choice([1, 1, 1, 2, 2, 3])
            b = Booking(user=user, event_slug=slug, status="confirmed", subtotal=t["price"] * qty,
                        created_at=when, confirmed_at=when, payment_ref="DEMO" if t["price"] else None)
            for _ in range(qty):
                name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
                b.attendees.append(Attendee(ticket_name=t["name"], price=t["price"], details={"name": name},
                                            checked_in_at=start + timedelta(minutes=rng.randint(-60, 20))
                                            if rng.random() < checked_share else None))
            db.session.add(b)
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
    if current_app.config.get("DEMO_SALES", True):
        load_demo_sales()
    return len(events), len(organizers)


def seed_if_empty():
    if db.session.query(Organizer).first() is None:
        load_json()
        return
    # Databases made before these demo extras existed get them once.
    if db.session.query(Review).first() is None:
        load_reviews()
    if current_app.config.get("DEMO_SALES", True) and \
            not User.query.filter(User.phone.startswith(DEMO_BUYER_PREFIX)).first():
        load_demo_sales()


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
