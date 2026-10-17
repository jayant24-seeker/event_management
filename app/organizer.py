"""Organizer side: sign up as an organizer, dashboard, create and edit events,
attendee lists with CSV export, coupons, waitlist and QR check-in."""
import csv
import io
import re
import secrets
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import (Blueprint, Response, abort, current_app, flash, g, jsonify, redirect, render_template, request,
                   url_for)
from sqlalchemy import func
from sqlalchemy.orm import contains_eager

from .auth import login_required
from .booking import FIELDS, field_keys
from .events import EventStore, now_ist, problems
from .models import (Announcement, Attendee, Booking, Coupon, EventRow, Organizer, Question, User, WaitlistEntry, db,
                     utcnow)
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


def claim_co_admin(user):
    """Someone an organizer added as co-admin becomes part of that organizer on their first visit."""
    from .models import GateStaff

    if user.organizer_slug:
        return
    row = GateStaff.query.filter_by(phone=user.phone, role="admin").order_by(GateStaff.created_at).first()
    if row:
        user.organizer_slug = row.organizer_slug
        db.session.commit()


@bp.before_app_request
def link_co_admins():
    if g.get("user") is not None and not g.user.organizer_slug:
        claim_co_admin(g.user)


def organizer_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        claim_co_admin(g.user)
        if not g.user.organizer_slug:
            return redirect(url_for("org.start"))
        g.org = db.session.get(Organizer, g.user.organizer_slug)
        return view(*args, **kwargs)
    return wrapped


def staff_org_slug(user):
    """The organizer this person scans tickets for: their own, or one that added them as gate staff."""
    from .models import GateStaff

    if user is None:
        return None
    if user.organizer_slug:
        return user.organizer_slug
    row = GateStaff.query.filter_by(phone=user.phone).order_by(GateStaff.created_at.desc()).first()
    return row.organizer_slug if row else None


def check_in_required(view):
    """Organizers, and the gate staff they added."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        slug = staff_org_slug(g.user)
        if slug is None:
            abort(404)
        g.org = db.session.get(Organizer, slug)
        return view(*args, **kwargs)
    return wrapped


@bp.app_template_global()
def is_gate_staff():
    user = g.get("user")
    return user is not None and not user.organizer_slug and staff_org_slug(user) is not None


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
    from .models import GateStaff
    return render_template("organizer/dashboard.html", upcoming=upcoming, past=past, sales=sales,
                           todo=attention_items(rows),
                           totals=totals, waitlist=waitlist, followers=follower_count(g.org.slug),
                           staff=GateStaff.query.filter_by(organizer_slug=g.org.slug).order_by(GateStaff.created_at).all())


def attention_items(rows):
    """Short to-do list for the dashboard: (text, link, button label), most urgent first."""
    live = store()
    slugs = [r.slug for r in rows]
    questions = dict(db.session.query(Question.event_slug, func.count(Question.id))
                     .filter(Question.event_slug.in_(slugs), Question.hidden.is_(False), Question.answered_at.is_(None))
                     .group_by(Question.event_slug)) if slugs else {}
    waiting = dict(db.session.query(WaitlistEntry.event_slug, func.count(WaitlistEntry.id))
                   .filter(WaitlistEntry.event_slug.in_(slugs), WaitlistEntry.notified_at.is_(None))
                   .group_by(WaitlistEntry.event_slug)) if slugs else {}
    out = []
    for r in rows:
        title = r.data.get("title") or "Untitled event"
        e = live.get(r.slug)
        if questions.get(r.slug):
            n = questions[r.slug]
            out.append((f"{n} question{'s' if n != 1 else ''} waiting on {title}",
                        url_for("main.event", slug=r.slug) + "#questions", "Answer"))
        if r.status == "draft":
            out.append((f"{title} is still a draft", url_for("org.edit_event", slug=r.slug), "Finish and publish"))
        elif e and not e.is_past() and e.sold_out and waiting.get(r.slug):
            out.append((f"{title} is sold out and {waiting[r.slug]} people are waiting",
                        url_for("org.edit_event", slug=r.slug), "Add seats"))
        elif e and not e.is_past() and e.selling_fast:
            out.append((f"{title} is {round(e.sold_ratio * 100)}% sold", url_for("org.edit_event", slug=r.slug), "Add seats"))
    return out[:6]


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
    for key in ("reg_closes", "age_min", "refund_tiers", "group_discount"):
        raw.pop(key, None)
    group_min, group_pct = form.get("group_min", "").strip(), form.get("group_percent", "").strip()
    if group_min.isdigit() and group_pct.isdigit() and int(group_min) >= 2 and 1 <= int(group_pct) <= 50:
        raw["group_discount"] = {"min": int(group_min), "percent": int(group_pct)}
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
    # Re-encode: at most 1200 px tall WebP (a few hundred KB instead of megabytes on mobile data),
    # and the photo's hidden metadata (camera, GPS location) is dropped.
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img.thumbnail((900, 1200) if img.height >= img.width else (1600, 1200))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "transparency" in img.info else "RGB")
        out = io.BytesIO()
        img.save(out, "WEBP", quality=82, method=6)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return None, "That image couldn't be read. Try exporting it again as JPG or PNG."
    rel = f"uploads/posters/{slug}-{secrets.token_hex(4)}.webp"
    path = Path(current_app.config["MEDIA_ROOT"]) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out.getvalue())
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


def shifted_copy(data, shift):
    """A fresh copy of an event's details moved by `shift`: no sales, results or featuring."""
    raw = {k: v for k, v in data.items() if k not in ("results", "featured")}
    for key in ("start", "end", "reg_closes"):
        if raw.get(key):
            try:
                raw[key] = (datetime.fromisoformat(raw[key]) + shift).strftime("%Y-%m-%dT%H:%M")
            except ValueError:
                pass  # left as is; the publish checks will ask for a valid date
    raw["tickets"] = [dict(t, sold=0) for t in raw.get("tickets", [])]
    if raw.get("poster", "").startswith("uploads/art/"):
        raw.pop("poster", None)  # generated posters show the date, so draw a new one
        raw.pop("banner", None)
        if raw.get("start") and raw.get("city"):
            raw["poster"], raw["banner"] = write_art(raw, current_app.config["MEDIA_ROOT"], folder="uploads/art")
    return raw


REPEATS = {"weekly": 7, "fortnightly": 14, "every4weeks": 28}


@bp.route("/events/<slug>/repeat", methods=["POST"])
@organizer_required
def repeat_event(slug):
    """Add more dates: copies every week / 2 weeks / 4 weeks, linked as one series."""
    row = own_event_or_404(slug)
    step = REPEATS.get(request.form.get("every"))
    count = request.form.get("count", type=int) or 0
    if not step or not 1 <= count <= 12:
        flash("Pick how often and how many more dates (1 to 12).")
        return redirect(url_for("org.event_admin", slug=slug) + "#repeat")
    series = row.data.get("series") or row.slug
    if row.data.get("series") != series:
        row.data = dict(row.data, series=series)
    made, drafts = 0, 0
    for i in range(1, count + 1):
        raw = shifted_copy(row.data, timedelta(days=step * i))
        raw["series"] = series
        raw["slug"] = unique_slug(EventRow, slugify(f"{raw['title']} {raw.get('start', '')[:10]}"))
        raw["organizer"] = g.org.slug
        live = row.status == "published" and not checks_for(raw)
        db.session.add(EventRow(slug=raw["slug"], organizer_slug=g.org.slug, status="published" if live else "draft", data=raw))
        made += 1
        drafts += not live
    db.session.commit()
    flash(f"Added {made} more date{'s' if made != 1 else ''}." + (f" {drafts} saved as drafts to check." if drafts else ""))
    return redirect(url_for("org.dashboard"))


@bp.route("/events/<slug>/duplicate", methods=["POST"])
@organizer_required
def duplicate_event(slug):
    """Start the next edition: same details as a draft, a year later (same weekday), no sales."""

    row = own_event_or_404(slug)
    raw = shifted_copy(row.data, timedelta(days=364))  # 52 weeks keeps the weekday
    raw.pop("series", None)
    old_year, new_year = row.data.get("start", "")[:4], raw.get("start", "")[:4]
    if old_year.isdigit() and old_year in raw.get("title", ""):
        raw["title"] = raw["title"].replace(old_year, new_year)
    year = raw.get("start", "")[:4]
    raw["slug"] = unique_slug(EventRow, slugify(raw["title"] if year in raw["title"] else f"{raw['title']} {year}"))
    db.session.add(EventRow(slug=raw["slug"], organizer_slug=g.org.slug, status="draft", data=raw))
    db.session.commit()
    flash("Copied as a draft for next year. Check the dates and prices, then publish.")
    return redirect(url_for("org.edit_event", slug=raw["slug"]))


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
    # Load each attendee's booking and buyer in the same query (the list shows the buyer's phone).
    return (Attendee.query.join(Booking).filter(Booking.event_slug == slug, Booking.status == "confirmed")
            .options(contains_eager(Attendee.booking).joinedload(Booking.user))
            .order_by(Booking.confirmed_at.desc(), Attendee.id).all())


def payout_summary(revenue):
    """(gross, platform fee, payment charges, payout) in rupees for ticket revenue."""
    cfg = current_app.config
    fee = round(revenue * cfg["PLATFORM_FEE_PCT"] / 100)
    charges = round(revenue * cfg["PAYMENT_FEE_PCT"] / 100)
    return revenue, fee, charges, revenue - fee - charges


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
    sources = (db.session.query(Booking.source, func.count(Booking.id), func.sum(Booking.subtotal - Booking.discount))
               .filter(Booking.event_slug == slug, Booking.status == "confirmed")
               .group_by(Booking.source).order_by(func.count(Booking.id).desc()).all())
    cancelled = Booking.query.filter(Booking.event_slug == slug, Booking.status == "cancelled",
                                     Booking.confirmed_at.isnot(None)).count()
    return render_template("organizer/event_admin.html", row=row, e=e, attendees=attendees, coupons=coupons,
                           used=used, waitlist=waitlist, keys=keys, fields=FIELDS,
                           sales=sales_by_event([slug]).get(slug, (0, 0, 0)), daily=daily_sales(slug),
                           bookings=bookings, cancelled=cancelled, sources=sources,
                           payout=payout_summary(sales_by_event([slug]).get(slug, (0, 0, 0))[1]),
                           announcements=Announcement.query.filter_by(event_slug=slug)
                           .order_by(Announcement.created_at.desc()).all(),
                           open_questions=Question.query.filter_by(event_slug=slug, hidden=False, answered_at=None).count())


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


MAX_ANNOUNCEMENTS_PER_DAY = 3


@bp.route("/events/<slug>/announce", methods=["POST"])
@organizer_required
def announce(slug):
    """Text every ticket holder (the person who booked) and pin the update on the event page."""

    from .sms import SmsNotConfigured, send_sms

    row = own_event_or_404(slug)
    text = " ".join(request.form.get("text", "").split())[:300]
    back = redirect(url_for("org.event_admin", slug=slug) + "#announce")
    if len(text) < 10:
        flash("Write a short message (at least 10 characters).")
        return back
    today = Announcement.query.filter(Announcement.event_slug == slug,
                                      Announcement.created_at > utcnow() - timedelta(days=1)).count()
    if today >= MAX_ANNOUNCEMENTS_PER_DAY:
        flash(f"You can send {MAX_ANNOUNCEMENTS_PER_DAY} updates a day. Try again tomorrow.")
        return back
    phones = sorted({p for (p,) in db.session.query(User.phone).join(Booking, Booking.user_id == User.id)
                     .filter(Booking.event_slug == slug, Booking.status == "confirmed")})
    title = row.data.get("title", "your event")
    sent = 0
    for phone in phones:
        try:
            send_sms(phone, f"{title}: {text} - {g.org.data['name']}")
            sent += 1
        except SmsNotConfigured:
            current_app.logger.exception("Announcement SMS not sent")
            break
    db.session.add(Announcement(event_slug=slug, text=text, sent_to=sent))
    db.session.commit()
    flash(f"Update posted on the event page and texted to {sent} ticket holder{'s' if sent != 1 else ''}.")
    return back


# ---------- Gate staff ----------
@bp.route("/staff", methods=["POST"])
@organizer_required
def staff():
    from .auth import normalize_phone
    from .models import GateStaff

    if request.form.get("remove"):
        row = GateStaff.query.filter_by(id=request.form.get("remove", type=int), organizer_slug=g.org.slug).first_or_404()
        if row.role == "admin":
            member = User.query.filter_by(phone=row.phone, organizer_slug=g.org.slug).first()
            if member is not None and member.id != g.user.id:
                member.organizer_slug = None
        db.session.delete(row)
        db.session.commit()
        flash(f"{row.name or row.phone} no longer has access.")
    else:
        phone = normalize_phone(request.form.get("phone"))
        if not phone:
            flash("Enter a 10-digit mobile number for the volunteer.")
        elif phone == g.user.phone:
            flash("That's you. You can already scan tickets.")
        elif GateStaff.query.filter_by(organizer_slug=g.org.slug, phone=phone).first():
            flash("They're already on your team.")
        else:
            role = "admin" if request.form.get("role") == "admin" else "gate"
            other = User.query.filter_by(phone=phone).first()
            if role == "admin" and other is not None and other.organizer_slug and other.organizer_slug != g.org.slug:
                flash("That number already runs another organizer profile, so it can't be added as a co-admin.")
                return redirect(url_for("org.dashboard") + "#staff")
            db.session.add(GateStaff(organizer_slug=g.org.slug, phone=phone, role=role,
                                     name=request.form.get("name", "").strip()[:120]))
            db.session.commit()
            flash("Added. They sign in with that number and find " +
                  ("the Organizer dashboard in their menu." if role == "admin" else "Scan tickets in their menu."))
    return redirect(url_for("org.dashboard") + "#staff")


@bp.route("/events/<slug>/flyer")
@organizer_required
def flyer(slug):
    """A4 flyer to print and pin up: artwork, details and a QR code to the event page."""
    import segno

    own_event_or_404(slug)
    e = store().get(slug)
    if e is None:
        flash("Publish the event first, so the QR code leads somewhere.")
        return redirect(url_for("org.event_admin", slug=slug))
    link = url_for("main.event", slug=slug, src="flyer", _external=True)
    qr = segno.make(link, error="m").svg_inline(scale=6, border=1, dark="#1A1423", omitsize=True)
    return render_template("organizer/flyer.html", e=e, qr=qr, link=url_for("main.event", slug=slug, _external=True))


# ---------- Check-in ----------
def ticket_code(text):
    """The code from what was typed or scanned: a bare code, or the /t/<code> link in the QR."""
    text = (text or "").strip()
    return text.rstrip("/").rsplit("/t/", 1)[-1].split("?")[0].strip().upper()[:16]


def check_in_code(code):
    """(status, attendee): ok | already | invalid (cancelled/unpaid) | unknown (not ours)."""
    a = Attendee.query.filter_by(code=code).first() if code else None
    if a is None or db.session.get(EventRow, a.booking.event_slug).organizer_slug != g.org.slug:
        return "unknown", None
    if a.booking.status != "confirmed":
        return "invalid", a
    if a.checked_in_at:
        return "already", a
    a.checked_in_at = utcnow()
    db.session.commit()
    return "ok", a


@bp.route("/check-in", methods=["POST"])
@check_in_required
def check_in():
    """Mark a ticket as used. Only the event's own organizer can do this."""
    code = ticket_code(request.form.get("code"))
    status, a = check_in_code(code)
    if status == "unknown":
        flash("No ticket with that code for your events.")
        return redirect(request.referrer or url_for("org.scan"))
    flash({"invalid": "This ticket is not valid (cancelled or unpaid).",
           "already": f"Already checked in: {a.name}.",
           "ok": f"Checked in: {a.name} ({a.ticket_name})."}[status])
    return redirect(url_for("booking.check_ticket", code=code))


@bp.route("/scan")
@check_in_required
def scan():
    """Gate scanner: point the phone camera at tickets; results show instantly."""
    now = now_ist()
    rows = EventRow.query.filter_by(organizer_slug=g.org.slug, status="published").all()
    events = sorted((e for _, e in wrap(rows) if e and not e.is_past(now - timedelta(days=1))), key=lambda e: e.start)
    return render_template("organizer/scan.html", events=events)


@bp.route("/check-in.json", methods=["POST"])
@check_in_required
def check_in_json():
    data = request.get_json(silent=True) or {}
    status, a = check_in_code(ticket_code(data.get("code")))
    out = {"status": status}
    if a is not None:
        e = store().get(a.booking.event_slug)
        total, checked = (db.session.query(func.count(Attendee.id), func.count(Attendee.checked_in_at))
                          .join(Booking).filter(Booking.event_slug == a.booking.event_slug,
                                                Booking.status == "confirmed").one())
        out.update(name=a.name, ticket=a.ticket_name, event=e.title if e else a.booking.event_slug,
                   at=current_app.jinja_env.filters["ist"](a.checked_in_at, "%-I:%M %p"),
                   counts={"checked": checked, "total": total})
    return jsonify(out)


@bp.app_template_global()
def can_check_in(attendee):
    slug = staff_org_slug(g.get("user"))
    if slug is None or attendee is None:
        return False
    row = db.session.get(EventRow, attendee.booking.event_slug)
    return row is not None and row.organizer_slug == slug


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
