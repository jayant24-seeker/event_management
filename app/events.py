"""Event data: loading, computed status/badges, search and filters, and publish checks.

Events and organizers are read from data/*.json. Later phases swap this for a database,
but templates only use the Event properties below, so they won't need to change.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
DATA_FILE = Path(__file__).parent / "data" / "events.json"
ORGANIZERS_FILE = Path(__file__).parent / "data" / "organizers.json"

SELLING_FAST_RATIO = 0.8

# Text that means an organizer left a field unfinished (see live-site issue #6).
PLACEHOLDER_PATTERNS = re.compile(
    r"\b(tbd|tba|lorem|ipsum|xxx+|placeholder|coming soon|to be announced|final route)\b|\{\{|\[insert",
    re.IGNORECASE,
)
REQUIRED_FIELDS = ["slug", "title", "category", "city", "start", "end", "about", "poster", "refund_policy", "organizer"]
REQUIRED_VENUE_FIELDS = ["name", "address"]

DATE_FILTERS = [("today", "Today"), ("weekend", "This weekend"), ("week", "This week"), ("month", "This month")]
PRICE_FILTERS = [("free", "Free"), ("u500", "Under ₹500"), ("u1000", "Under ₹1,000"), ("paid", "Paid")]
SORTS = [("date", "Soonest"), ("price", "Price: low to high"), ("popular", "Most popular")]


def now_ist():
    return datetime.now(IST)


@dataclass
class Ticket:
    name: str
    price: int
    capacity: int
    sold: int = 0
    note: str = ""

    @property
    def left(self):
        return max(self.capacity - self.sold, 0)

    @property
    def sold_out(self):
        return self.left == 0


@dataclass
class Event:
    raw: dict
    tickets: list = field(default_factory=list)
    org: dict = field(default_factory=dict)  # organizer profile, filled in by EventStore

    def __getattr__(self, name):
        # Plain JSON fields (title, city, faqs, ...) read straight from raw.
        try:
            return self.raw[name]
        except KeyError:
            raise AttributeError(name) from None

    @property
    def start(self):
        return datetime.fromisoformat(self.raw["start"]).replace(tzinfo=IST)

    @property
    def end(self):
        return datetime.fromisoformat(self.raw["end"]).replace(tzinfo=IST)

    @property
    def is_online(self):
        return self.raw.get("mode") == "online"

    @property
    def reg_closes(self):
        """When registration closes: its own date if set, else when the event starts."""
        value = self.raw.get("reg_closes")
        return datetime.fromisoformat(value).replace(tzinfo=IST) if value else self.start

    def registration_open(self, at=None):
        at = at or now_ist()
        return not self.sold_out and at < self.reg_closes and not self.is_past(at)

    def status(self, at=None):
        at = at or now_ist()
        if at > self.end:
            return "past"
        if at >= self.start:
            return "live"
        return "upcoming"

    def is_past(self, at=None):
        return self.status(at) == "past"

    @property
    def is_free(self):
        return all(t.price == 0 for t in self.tickets)

    @property
    def sold_out(self):
        return bool(self.tickets) and all(t.sold_out for t in self.tickets)

    @property
    def sold_ratio(self):
        cap = sum(t.capacity for t in self.tickets)
        return sum(min(t.sold, t.capacity) for t in self.tickets) / cap if cap else 0

    @property
    def registered(self):
        return sum(min(t.sold, t.capacity) for t in self.tickets)

    @property
    def selling_fast(self):
        return not self.sold_out and self.sold_ratio >= SELLING_FAST_RATIO

    @property
    def spots_left(self):
        return sum(t.left for t in self.tickets)

    @property
    def price_from(self):
        """Lowest price still on sale, falling back to the lowest overall."""
        open_prices = [t.price for t in self.tickets if not t.sold_out]
        prices = open_prices or [t.price for t in self.tickets]
        return min(prices) if prices else 0

    def badges(self, at=None):
        """Card badges, most important first. Each is (label, style)."""
        if self.is_past(at):
            return [("Event ended", "muted")]
        out = []
        if self.status(at) == "live":
            out.append(("Happening now", "live"))
        if self.sold_out:
            out.append(("Sold out", "soldout"))
        elif not self.registration_open(at):
            out.append(("Registration closed", "muted"))
        elif self.selling_fast:
            out.append(("Selling fast", "hot"))
        if self.is_free:
            out.append(("Free", "free"))
        if self.is_online:
            out.append(("Online", "muted"))
        return out


def problems(raw):
    """Return a list of reasons this event can't be published (empty list = OK)."""
    issues = []
    for key in REQUIRED_FIELDS:
        if not str(raw.get(key, "")).strip():
            issues.append(f"'{key}' is required")
    venue = raw.get("venue") or {}
    for key in REQUIRED_VENUE_FIELDS:
        if not str(venue.get(key, "")).strip():
            issues.append(f"venue '{key}' is required")
    if not raw.get("tickets"):
        issues.append("at least one ticket type is required")
    for t in raw.get("tickets", []):
        if t.get("price", -1) < 0:
            issues.append(f"ticket '{t.get('name')}' has a negative price")
        if t.get("capacity", 0) <= 0:
            issues.append(f"ticket '{t.get('name')}' needs a capacity above 0")
    try:
        if datetime.fromisoformat(raw["end"]) < datetime.fromisoformat(raw["start"]):
            issues.append("end time is before start time")
    except (KeyError, ValueError):
        issues.append("start and end must be valid dates (YYYY-MM-DDTHH:MM)")

    def walk(value, path):
        if isinstance(value, str):
            if PLACEHOLDER_PATTERNS.search(value):
                issues.append(f"'{path}' looks like placeholder text: {value[:60]!r}")
        elif isinstance(value, dict):
            for k, v in value.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, f"{path}[{i}]")

    walk(raw, "")
    return issues


def date_window(key, at=None):
    """(start, end) for the date filter: today, weekend, week or month. None means any date."""
    at = at or now_ist()
    day = at.replace(hour=0, minute=0, second=0, microsecond=0)
    if key == "today":
        return at, day + timedelta(days=1)
    if key == "weekend":
        # Saturday and Sunday of this week; on a Sunday, just the rest of today.
        saturday = day - timedelta(days=1) if day.weekday() == 6 else day + timedelta(days=5 - day.weekday())
        return max(at, saturday), saturday + timedelta(days=2)
    if key == "week":
        return at, day + timedelta(days=7 - day.weekday())
    if key == "month":
        return at, (day.replace(day=1) + timedelta(days=32)).replace(day=1)
    return None


def _build(raw, organizers):
    tickets = [Ticket(**t) for t in raw.get("tickets", [])]
    return Event(raw=raw, tickets=tickets, org=organizers.get(raw.get("organizer"), {}))


class EventStore:
    def __init__(self, path=DATA_FILE, organizers_path=ORGANIZERS_FILE):
        with open(path, encoding="utf-8") as f:
            raws = json.load(f)
        with open(organizers_path, encoding="utf-8") as f:
            self.organizers = {o["slug"]: o for o in json.load(f)}
        self.invalid = {r.get("slug", "?"): problems(r) for r in raws if problems(r)}
        for r in raws:
            if r.get("slug") not in self.invalid and r.get("organizer") not in self.organizers:
                self.invalid[r["slug"]] = [f"unknown organizer {r.get('organizer')!r}"]
        # Never show an event that fails the publish checks.
        self.events = [_build(r, self.organizers) for r in raws if r.get("slug") not in self.invalid]
        self._by_slug = {e.slug: e for e in self.events}

    def get(self, slug):
        return self._by_slug.get(slug)

    def by_organizer(self, slug):
        return [e for e in self.events if e.organizer == slug]

    def upcoming(self, at=None):
        """Upcoming and live events, soonest first."""
        return sorted((e for e in self.events if not e.is_past(at)), key=lambda e: e.start)

    def past(self, at=None):
        """Archive, most recent first."""
        return sorted((e for e in self.events if e.is_past(at)), key=lambda e: e.start, reverse=True)

    def featured(self, at=None):
        return [e for e in self.upcoming(at) if e.raw.get("featured")]

    def similar(self, event, limit=4, at=None):
        """Upcoming events in the same category first, then the same city."""
        pool = [e for e in self.upcoming(at) if e.slug != event.slug]
        pool.sort(key=lambda e: (e.category != event.category, e.city != event.city, e.start))
        return pool[:limit]

    def cities(self):
        return sorted({e.city for e in self.events})

    def categories(self):
        return sorted({e.category for e in self.events})

    def counts(self, attr, at=None, when="upcoming"):
        """Events per city or category, busiest first: [(name, count), ...]."""
        totals = {}
        for e in self.past(at) if when == "past" else self.upcoming(at):
            key = getattr(e, attr)
            totals[key] = totals.get(key, 0) + 1
        return sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))

    def suggest(self, q, limit=5, at=None):
        """Search-box suggestions: matching upcoming events, cities and categories."""
        q = q.strip().lower()
        if len(q) < 2:
            return {"events": [], "cities": [], "categories": []}
        events = self.search(q, at=at)
        # Titles that start with the query feel most relevant, so they go first.
        events.sort(key=lambda e: not e.title.lower().startswith(q))
        return {
            "events": events[:limit],
            "cities": [c for c, _ in self.counts("city", at) if q in c.lower()],
            "categories": [c for c, _ in self.counts("category", at) if q in c.lower()],
        }

    def search(self, q="", city=None, category=None, max_price=None, when="upcoming", sort="date",
               date=None, price=None, at=None):
        pool = self.past(at) if when == "past" else self.upcoming(at)
        q = q.strip().lower()
        window = date_window(date, at) if when != "past" else None
        price_cap = {"u500": 500, "u1000": 1000}.get(price, max_price)
        out = []
        for e in pool:
            haystack = " ".join([e.title, e.tagline, e.city, e.category, e.venue["name"], e.org.get("name", ""),
                                 " ".join(e.raw.get("tags", []))]).lower()
            if q and q not in haystack:
                continue
            if city and e.city != city:
                continue
            if category and e.category != category:
                continue
            if price_cap is not None and e.price_from > price_cap:
                continue
            if price == "free" and not e.is_free:
                continue
            if price == "paid" and e.is_free:
                continue
            if window and not (e.start < window[1] and e.end >= window[0]):
                continue
            out.append(e)
        if sort == "price":
            out.sort(key=lambda e: e.price_from)
        elif sort == "popular":
            out.sort(key=lambda e: -e.sold_ratio)
        return out
