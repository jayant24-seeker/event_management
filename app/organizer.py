"""Organizer side: sign up as an organizer, dashboard, create and edit events,
attendee lists with CSV export, coupons, waitlist and QR check-in."""
import csv
import io
import re
import secrets
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request,
                   url_for)
from sqlalchemy import func

from .auth import login_required
from .booking import FIELDS, field_keys
from .events import EventStore, now_ist, problems
from .models import Attendee, Booking, Coupon, EventRow, Organizer, User, WaitlistEntry, db, utcnow
from .posters import write_art
from .routes import follower_count, store

bp = Blueprint("org", __name__, url_prefix="/organizer")

CATEGORIES = ["Running", "Cycling", "Music", "Garba & Dandiya", "Kavi Sammelan", "Cultural", "Comedy", "Food",
              "Workshop", "Sports", "Tech", "Wellness"]
MAX_UPLOAD = 5 * 1024 * 1024
IMAGE_TYPES = {b"\x89PNG": "png", b"\xff\xd8\xff": "jpg"}


def slugify(text):
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:60] or "event"


def unique_slug(model, base):
    slug, n = base, 2
    while db.session.get(model, slug) is not None:
        slug, n = f"{base}-{n}", n + 1
    return slug


def organizer_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not g.user.organizer_slug:
            return redirect(url_for("org.start"))
        g.org = db.session.get(Organizer, g.user.organizer_slug)
        return view(*args, **kwargs)
    return wrapped


def own_event_or_404(slug):
    row = db.session.get(EventRow, slug)
    if row is None or row.organizer_slug != g.user.organizer_slug:
        abort(404)
    return row


# ---------- Become an organizer ----------
@bp.route("/start", methods=["GET", "POST"])
@login_required
def start():
    if g.user.organizer_slug:
        return redirect(url_for("org.dashboard"))
    errors = []
    form = request.form
    if request.method == "POST":
        name, city, about = form.get("name", "").strip(), form.get("city", "").strip(), form.get("about", "").strip()
        if len(name) < 3:
            errors.append("Enter your organization's name.")
        if not city:
            errors.append("Enter your city.")
        if len(about) < 20:
            errors.append("Tell attendees about you in at least a sentence.")
        if not errors:
            slug = unique_slug(Organizer, slugify(name))
            socials = {k: form.get(k, "").strip() for k in ("instagram", "facebook", "website") if form.get(k, "").strip().startswith("https://")}
            db.session.add(Organizer(slug=slug, data={"name": name[:120], "city": city[:60], "about": about[:600],
                                                      "since": now_ist().year, "verified": False, "socials": socials}))
            g.user.organizer_slug = slug
            db.session.commit()
            flash("Your organizer profile is ready. Create your first event!")
            return redirect(url_for("org.new_event"))
    return render_template("organizer/start.html", errors=errors, form=form)


# ---------- Dashboard ----------
def sales_by_event(slugs):
    """{slug: (tickets, revenue, checked_in)} for confirmed bookings."""
    if not slugs:
        return {}
    tickets = dict(db.session.query(Booking.event_slug, func.count(Attendee.id))
                   .join(Attendee, Attendee.booking_id == Booking.id)
                   .filter(Booking.event_slug.in_(slugs), Booking.status == "confirmed").group_by(Booking.event_slug))
    revenue = dict(db.session.query(Booking.event_slug, func.sum(Booking.subtotal - Booking.discount))
                   .filter(Booking.event_slug.in_(slugs), Booking.status == "confirmed").group_by(Booking.event_slug))
    checked = dict(db.session.query(Booking.event_slug, func.count(Attendee.id))
                   .join(Attendee, Attendee.booking_id == Booking.id)
                   .filter(Booking.event_slug.in_(slugs), Booking.status == "confirmed", Attendee.checked_in_at.isnot(None))
                   .group_by(Booking.event_slug))
    return {s: (tickets.get(s, 0), revenue.get(s, 0) or 0, checked.get(s, 0)) for s in slugs}


def wrap(rows):
    """Event objects for the organizer's own rows, drafts included."""
    org = g.org
    events = EventStore(raws=[r.data for r in rows], organizers=[dict(org.data, slug=org.slug)])
    by_slug = {e.slug: e for e in events.events}
    return [(r, by_slug.get(r.slug)) for r in rows]


@bp.route("/")
@organizer_required
def dashboard():
    rows = EventRow.query.filter_by(organizer_slug=g.org.slug).order_by(EventRow.created_at.desc()).all()
    items = wrap(rows)
    sales = sales_by_event([r.slug for r in rows])
    now = now_ist()
    upcoming = [(r, e) for r, e in items if e is None or not e.is_past(now)]
    past = [(r, e) for r, e in items if e is not None and e.is_past(now)]
    upcoming.sort(key=lambda x: x[1].start if x[1] else now)
    totals = [sum(v[i] for v in sales.values()) for i in range(3)]
    waitlist = WaitlistEntry.query.filter(WaitlistEntry.event_slug.in_([r.slug for r in rows])).count() if rows else 0
    return render_template("organizer/dashboard.html", upcoming=upcoming, past=past, sales=sales,
                           totals=totals, waitlist=waitlist, followers=follower_count(g.org.slug))


# ---------- Create and edit events ----------
def lines(text):
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def pairs(text):
    out = []
    for line in lines(text):
        left, _, right = line.partition("|")
        out.append((left.strip(), right.strip()))
    return out


def event_from_form(form, existing=None):
    """Build the event dict from the form. Keeps sold counts and results from the saved version."""
    raw = dict(existing or {})
    category = form.get("category_other", "").strip() if form.get("category") == "Other" else form.get("category", "")
    mode = "online" if form.get("mode") == "online" else "venue"
    raw.update({
        "title": form.get("title", "").strip()[:120],
        "tagline": form.get("tagline", "").strip()[:160],
        "category": category[:40],
        "city": "Online" if mode == "online" else form.get("city", "").strip()[:60],
        "mode": mode,
        "start": form.get("start", ""),
        "end": form.get("end", ""),
        "language": form.get("language", "").strip()[:60],
        "about": form.get("about", "").strip()[:5000],
        "highlights": lines(form.get("highlights"))[:8],
        "schedule": [{"time": t, "title": x} for t, x in pairs(form.get("schedule")) if t and x][:20],
        "kit": lines(form.get("kit"))[:15],
        "prizes": lines(form.get("prizes"))[:10],
        "faqs": [{"q": q, "a": a} for q, a in pairs(form.get("faqs")) if q and a][:15],
        "refund_policy": form.get("refund_policy", "").strip()[:1000],
        "attendee_fields": [k for k in FIELDS if form.get(f"field_{k}")] or ["name"],
        "venue": {
            "name": "Online" if mode == "online" and not form.get("venue_name", "").strip() else form.get("venue_name", "").strip()[:120],
            "address": form.get("venue_address", "").strip()[:300],
            "map_query": f"{form.get('venue_name', '').strip()} {form.get('city', '').strip()}".strip(),
        },
    })
    if "attendee_fields" in raw and "name" not in raw["attendee_fields"]:
        raw["attendee_fields"].insert(0, "name")
    for key in ("reg_closes", "age_min", "refund_tiers"):
        raw.pop(key, None)
    tiers = []
    for days, pct in pairs(form.get("refund_tiers")):
        if days.strip().isdigit() and pct.strip().rstrip("%").isdigit():
            tiers.append({"hours": int(days) * 24, "percent": min(int(pct.strip().rstrip("%")), 100)})
    if tiers:
        raw["refund_tiers"] = [t for t in tiers if t["percent"] > 0]  # "0 | 0" = no online refunds
    if form.get("reg_closes"):
        raw["reg_closes"] = form["reg_closes"]
    if form.get("age_min", "").isdigit():
        raw["age_min"] = int(form["age_min"])
    route = {k: form.get(f"route_{k}", "").strip() for k in ("start", "finish", "note")}
    raw.pop("route", None)
    if route["start"] or route["finish"]:
        raw["route"] = route

    old_sold = {t["name"]: t.get("sold", 0) for t in (existing or {}).get("tickets", [])}
    tickets = []
    for name, price, cap, note in zip(form.getlist("ticket_name"), form.getlist("ticket_price"),
                                      form.getlist("ticket_capacity"), form.getlist("ticket_note")):
        name = name.strip()[:80]
        if not name:
            continue
        ticket = {"name": name, "price": int(price) if price.strip().isdigit() else -1,
                  "capacity": int(cap) if cap.strip().isdigit() else 0, "sold": old_sold.get(name, 0)}
        if note.strip():
            ticket["note"] = note.strip()[:200]
        tickets.append(ticket)
    raw["tickets"] = tickets
    return raw


def save_upload(file, slug):
    """Store an uploaded JPG/PNG poster; returns its static path or an error message."""
    data = file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        return None, "The poster must be under 5 MB."
    ext = next((e for magic, e in IMAGE_TYPES.items() if data.startswith(magic)), None)
    if ext is None and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        ext = "webp"
    if ext is None:
        return None, "Upload the poster as a JPG, PNG or WebP image."
    rel = f"uploads/posters/{slug}-{secrets.token_hex(4)}.{ext}"
    path = Path(current_app.config["MEDIA_ROOT"]) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel, None


def checks_for(raw, first_publish=True):
    """Publish checks plus the ones only an organizer's own event needs."""
    issues = problems(raw)
    try:
        start = datetime.fromisoformat(raw["start"])
        if first_publish and start < now_ist().replace(tzinfo=None):
            issues.append("the start date is in the past")
        if raw.get("reg_closes") and datetime.fromisoformat(raw["reg_closes"]) > start:
            issues.append("registration must close before the event starts")
    except (KeyError, ValueError):
        pass
    if raw.get("mode") != "online" and not raw.get("city"):
        issues.append("'city' is required")
    names = [t["name"] for t in raw.get("tickets", [])]
    if len(names) != len(set(names)):
        issues.append("each ticket type needs a different name")
    for t in raw.get("tickets", []):
        if t.get("capacity", 0) < t.get("sold", 0):
            issues.append(f"ticket '{t['name']}' can't have fewer seats than already sold ({t['sold']})")
    return issues


def save_event(row=None):
    form = request.form
    existing = row.data if row else None
    raw = event_from_form(form, existing)
    if not raw["title"]:
        return None, ["Give the event a title."], raw
    if row is None:
        year = raw["start"][:4] if raw["start"][:4].isdigit() else ""
        raw["slug"] = unique_slug(EventRow, slugify(f"{raw['title']} {year}" if year and year not in raw["title"] else raw["title"]))
    else:
        raw["slug"] = row.slug
    raw["organizer"] = g.org.slug

    upload = request.files.get("poster")
    if upload and upload.filename:
        path, error = save_upload(upload, raw["slug"])
        if error:
            return None, [error], raw
        raw["poster"] = raw["banner"] = path
    elif not raw.get("poster") or raw["poster"].startswith("uploads/art/"):
        # No artwork: make (or refresh) an original poster from the title, date and city.
        if raw["start"] and raw["city"]:
            raw["poster"], raw["banner"] = write_art(raw, current_app.config["MEDIA_ROOT"], folder="uploads/art")

    action = form.get("action")
    live = row is not None and row.status == "published" and action != "unpublish"
    issues = checks_for(raw, first_publish=not live) if action == "publish" or live else []
    if live and issues:
        # Never break a live event: the published version stays until the problems are fixed.
        return None, issues, raw
    if row is None:
        row = EventRow(slug=raw["slug"], organizer_slug=g.org.slug, status="draft", data=raw)
        db.session.add(row)
    row.data = raw
    if action == "publish" and not issues:
        row.status = "published"
    elif action == "unpublish":
        row.status = "draft"
    db.session.commit()
    return row, issues, raw


def form_context(raw, issues=None, row=None):
    raw = dict(raw, attendee_fields=field_keys(raw))  # show the defaults as ticked
    return dict(raw=raw, issues=issues or [], row=row, categories=CATEGORIES, fields=FIELDS)


@bp.route("/events/new", methods=["GET", "POST"])
@organizer_required
def new_event():
    if request.method == "POST":
        row, issues, raw = save_event()
        if row is None:
            return render_template("organizer/event_form.html", **form_context(raw, issues))
        return after_save(row, issues)
    blank = {"tickets": [], "attendee_fields": ["name", "gender", "age"], "mode": "venue", "city": g.org.data.get("city", "")}
    return render_template("organizer/event_form.html", **form_context(blank))


@bp.route("/events/<slug>/edit", methods=["GET", "POST"])
@organizer_required
def edit_event(slug):
    row = own_event_or_404(slug)
    if request.method == "POST":
        saved, issues, raw = save_event(row)
        if saved is None:
            return render_template("organizer/event_form.html", **form_context(raw, issues, row))
        return after_save(saved, issues)
    return render_template("organizer/event_form.html", **form_context(row.data, None, row))


def after_save(row, issues):
    if issues:
        flash("Saved as a draft. Fix the items below to publish.")
        return render_template("organizer/event_form.html", **form_context(row.data, issues, row))
    if request.form.get("action") == "publish":
        flash("Published! Your event is live.")
        return redirect(url_for("main.event", slug=row.slug))
    flash("Draft saved." if row.status == "draft" else "Changes saved.")
    return redirect(url_for("org.edit_event", slug=row.slug))


# ---------- Attendees, coupons, waitlist ----------
def attendee_rows(slug):
    return (Attendee.query.join(Booking).filter(Booking.event_slug == slug, Booking.status == "confirmed")
            .order_by(Booking.confirmed_at.desc(), Attendee.id).all())


def daily_sales(slug, days=45):
    """[(date, tickets, revenue)] per day in IST, from the first sale (at most `days` back) to today."""
    from datetime import timedelta, timezone

    from .events import IST

    rows = (db.session.query(Booking.confirmed_at, Booking.subtotal - Booking.discount, func.count(Attendee.id))
            .join(Attendee, Attendee.booking_id == Booking.id)
            .filter(Booking.event_slug == slug, Booking.status == "confirmed", Booking.confirmed_at.isnot(None))
            .group_by(Booking.id).all())
    if not rows:
        return []
    per_day = {}
    for at, revenue, tickets in rows:
        day = at.replace(tzinfo=timezone.utc).astimezone(IST).date()
        t, r = per_day.get(day, (0, 0))
        per_day[day] = (t + tickets, r + (revenue or 0))
    # Up to today while sales are recent; for an old event, stop a few days after the last sale.
    last = min(now_ist().date(), max(per_day) + timedelta(days=3))
    first = max(min(per_day), last - timedelta(days=days - 1))
    out, day = [], first
    while day <= last:
        out.append((day, *per_day.get(day, (0, 0))))
        day += timedelta(days=1)
    return out


@bp.route("/events/<slug>")
@organizer_required
def event_admin(slug):
    row = own_event_or_404(slug)
    e = wrap([row])[0][1]
    attendees = attendee_rows(slug)
    coupons = Coupon.query.filter_by(event_slug=slug).order_by(Coupon.id).all()
    used = dict(db.session.query(Booking.coupon_code, func.count(Booking.id))
                .filter(Booking.event_slug == slug, Booking.status == "confirmed").group_by(Booking.coupon_code))
    waitlist = WaitlistEntry.query.filter_by(event_slug=slug).order_by(WaitlistEntry.created_at).all()
    keys = field_keys(row.data)
    bookings = Booking.query.filter_by(event_slug=slug, status="confirmed").count()
    cancelled = Booking.query.filter(Booking.event_slug == slug, Booking.status == "cancelled",
                                     Booking.confirmed_at.isnot(None)).count()
    return render_template("organizer/event_admin.html", row=row, e=e, attendees=attendees, coupons=coupons,
                           used=used, waitlist=waitlist, keys=keys, fields=FIELDS,
                           sales=sales_by_event([slug]).get(slug, (0, 0, 0)), daily=daily_sales(slug),
                           bookings=bookings, cancelled=cancelled)


def csv_safe(value):
    # Stop spreadsheet apps from running text that looks like a formula.
    value = str(value or "")
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


@bp.route("/events/<slug>/attendees.csv")
@organizer_required
def attendees_csv(slug):
    row = own_event_or_404(slug)
    keys = field_keys(row.data)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Ticket code", "Ticket", "Price"] + [FIELDS[k]["label"] for k in keys if k in FIELDS]
                    + ["Booked by (phone)", "Booking ref", "Booked at (IST)", "Checked in"])
    for a in attendee_rows(slug):
        writer.writerow([a.code, a.ticket_name, a.price] + [csv_safe(a.details.get(k)) for k in keys if k in FIELDS]
                        + [a.booking.user.phone, a.booking.ref, current_app.jinja_env.filters["ist"](a.booking.confirmed_at),
                           "yes" if a.checked_in_at else ""])
    return Response("﻿" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{slug}-attendees.csv"'})


@bp.route("/events/<slug>/coupons", methods=["POST"])
@organizer_required
def coupons(slug):
    own_event_or_404(slug)
    if request.form.get("delete"):
        c = Coupon.query.filter_by(id=request.form.get("delete", type=int), event_slug=slug).first_or_404()
        db.session.delete(c)
        db.session.commit()
        flash(f"Code {c.code} deleted.")
        return redirect(url_for("org.event_admin", slug=slug) + "#coupons")
    code = re.sub(r"[^A-Z0-9]", "", request.form.get("code", "").upper())[:20]
    pct = request.form.get("percent_off", type=int) or 0
    if len(code) < 3 or not 1 <= pct <= 100:
        flash("Codes need at least 3 letters or numbers, and 1 to 100% off.")
    elif Coupon.query.filter_by(event_slug=slug, code=code).first():
        flash(f"Code {code} already exists.")
    else:
        try:
            until = datetime.fromisoformat(request.form["valid_until"]) if request.form.get("valid_until") else None
        except ValueError:
            flash("Enter the expiry as a date and time.")
            return redirect(url_for("org.event_admin", slug=slug) + "#coupons")
        db.session.add(Coupon(event_slug=slug, code=code, percent_off=pct,
                              max_uses=request.form.get("max_uses", type=int) or None, valid_until=until))
        db.session.commit()
        flash(f"Code {code} created.")
    return redirect(url_for("org.event_admin", slug=slug) + "#coupons")


@bp.route("/events/<slug>/waitlist/notify", methods=["POST"])
@organizer_required
def notify_waitlist_now(slug):
    """After adding seats: text everyone on the waitlist who hasn't been told yet."""
    from .booking import notify_waitlist

    own_event_or_404(slug)
    e = store().get(slug)
    if e is None or not e.registration_open():
        flash("Open registration (publish the event and make sure seats are left) before messaging the waitlist.")
    else:
        n = notify_waitlist(e, e.spots_left)
        flash(f"Texted {n} {'person' if n == 1 else 'people'} on the waitlist." if n else "Everyone on the waitlist has already been texted.")
    return redirect(url_for("org.event_admin", slug=slug) + "#waitlist")


# ---------- Check-in ----------
@bp.route("/check-in", methods=["POST"])
@organizer_required
def check_in():
    """Mark a ticket as used. Only the event's own organizer can do this."""
    code = request.form.get("code", "").strip().upper()
    a = Attendee.query.filter_by(code=code).first()
    if a is None or db.session.get(EventRow, a.booking.event_slug).organizer_slug != g.org.slug:
        flash("No ticket with that code for your events.")
        return redirect(request.referrer or url_for("org.dashboard"))
    if a.booking.status != "confirmed":
        flash("This ticket is not valid (cancelled or unpaid).")
    elif a.checked_in_at:
        flash(f"Already checked in: {a.name}.")
    else:
        a.checked_in_at = utcnow()
        db.session.commit()
        flash(f"Checked in: {a.name} ({a.ticket_name}).")
    return redirect(url_for("booking.check_ticket", code=code))


@bp.app_template_global()
def can_check_in(attendee):
    if g.get("user") is None or not g.user.organizer_slug or attendee is None:
        return False
    row = db.session.get(EventRow, attendee.booking.event_slug)
    return row is not None and row.organizer_slug == g.user.organizer_slug


@bp.app_template_global()
def schedule_text(raw):
    return "\n".join(f"{item['time']} | {item['title']}" for item in raw.get("schedule") or [])


@bp.app_template_global()
def refund_tiers_text(raw):
    tiers = raw.get("refund_tiers")
    if tiers is None:
        return ""
    return "\n".join(f"{t['hours'] // 24} | {t['percent']}" for t in tiers) or "0 | 0"


@bp.app_template_global()
def faq_text(raw):
    return "\n".join(f"{item['q']} | {item['a']}" for item in raw.get("faqs") or [])
