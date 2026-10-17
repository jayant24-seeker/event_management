"""Texts that go out on their own: a reminder the day before, and a review request after.

Run every hour from the host's scheduler (cron, Render cron job...):

    flask --app run send-reminders

Each booking gets each message at most once, so running it often is safe.
"""
from datetime import timedelta

import click
from flask import current_app, url_for

from .events import now_ist
from .models import Booking, SavedEvent, User, db, utcnow
from .routes import store
from .sms import SmsNotConfigured, send_sms


def due_messages(at=None):
    """[(booking, kind, text)] that should go out now."""
    at = at or now_ist()
    s = store()
    out = []
    for b in Booking.query.filter(Booking.status == "confirmed",
                                  (Booking.reminded_at.is_(None)) | (Booking.review_asked_at.is_(None))):
        e = s.get(b.event_slug)
        if e is None:
            continue
        link = url_for("booking.show", ref=b.ref, _external=True)
        hours_to_go = (e.start - at).total_seconds() / 3600
        if b.reminded_at is None and 0 < hours_to_go <= 30:
            out.append((b, "reminder", f"See you {'tomorrow' if hours_to_go > 12 else 'soon'} at {e.title}, "
                                       f"{e.start.strftime('%a %-I:%M %p')}, {e.venue['name']}. Your tickets: {link}"))
        hours_since = (at - e.end).total_seconds() / 3600
        if b.review_asked_at is None and 2 <= hours_since <= 72:
            review = url_for("main.event", slug=e.slug, _external=True) + "#reviews"
            out.append((b, "review", f"How was {e.title}? Leave a quick rating for {e.org.get('name', 'the organizer')}: {review}"))
    return out


def closing_alerts(at=None):
    """[(saved row, phone, text)] for saved-but-not-booked events whose registration closes within 48 h."""
    at = at or now_ist()
    s = store()
    out = []
    for row, phone in (db.session.query(SavedEvent, User.phone).join(User, User.id == SavedEvent.user_id)
                       .filter(SavedEvent.closing_alert_at.is_(None))):
        e = s.get(row.event_slug)
        if e is None or not e.registration_open(at):
            continue
        hours_left = (e.reg_closes - at).total_seconds() / 3600
        booked = Booking.query.filter_by(user_id=row.user_id, event_slug=e.slug, status="confirmed").first()
        if 0 < hours_left <= 48 and not booked:
            link = url_for("main.event", slug=e.slug, src="saved-alert", _external=True) + "#tickets"
            out.append((row, phone, f"Registration for {e.title} (you saved it) closes {e.reg_closes.strftime('%a %-I:%M %p')}. "
                                    f"{e.spots_left} spots left: {link}"))
    return out


def send_due(at=None):
    sent = 0
    for row, phone, text in closing_alerts(at):
        try:
            send_sms(phone, text)
        except SmsNotConfigured:
            current_app.logger.exception("Saved-event alert not sent")
            break
        row.closing_alert_at = utcnow()
        sent += 1
    for b, kind, text in due_messages(at):
        try:
            send_sms(b.user.phone, text)
        except SmsNotConfigured:
            current_app.logger.exception("Reminder SMS not sent")
            break
        if kind == "reminder":
            b.reminded_at = utcnow()
        else:
            b.review_asked_at = utcnow()
        sent += 1
    db.session.commit()
    return sent


def register_cli(app):
    @app.cli.command("send-reminders")
    def send_reminders():
        """Text tomorrow's attendees, ask yesterday's for a review, and warn savers before registration closes."""
        with app.test_request_context(base_url=app.config.get("PUBLIC_URL") or "http://localhost"):
            click.echo(f"Sent {send_due()} message(s).")
