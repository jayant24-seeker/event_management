"""Structured data and calendar helpers used by templates."""
from datetime import timezone

from flask import url_for


def event_jsonld(e):
    """schema.org Event, so Google can show the event with date, place and price."""
    page = url_for("main.event", slug=e.slug, _external=True)
    if e.is_online:
        location = {"@type": "VirtualLocation", "url": page}
    else:
        location = {
            "@type": "Place",
            "name": e.venue["name"],
            "address": {"@type": "PostalAddress", "streetAddress": e.venue["address"],
                        "addressLocality": e.city, "addressCountry": "IN"},
        }
    data = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": e.title,
        "description": e.tagline,
        "startDate": e.start.isoformat(),
        "endDate": e.end.isoformat(),
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/" + ("OnlineEventAttendanceMode" if e.is_online else "OfflineEventAttendanceMode"),
        "location": location,
        "image": [url_for("static", filename=e.poster, _external=True), url_for("static", filename=e.banner, _external=True)],
        "url": page,
        "organizer": {"@type": "Organization", "name": e.org.get("name"),
                      "url": url_for("main.organizer", slug=e.organizer, _external=True)},
        "offers": [
            {
                "@type": "Offer",
                "name": t.name,
                "price": t.price,
                "priceCurrency": "INR",
                "availability": "https://schema.org/" + ("SoldOut" if t.sold_out else "InStock"),
                "validThrough": e.reg_closes.isoformat(),
                "url": page,
            }
            for t in e.tickets
        ],
    }
    if e.raw.get("language"):
        data["inLanguage"] = e.raw["language"]
    return data


def gcal_dates(e):
    """Start/end in the format Google Calendar's add-event link wants."""
    fmt = "%Y%m%dT%H%M%SZ"
    return f"{e.start.astimezone(timezone.utc).strftime(fmt)}/{e.end.astimezone(timezone.utc).strftime(fmt)}"
