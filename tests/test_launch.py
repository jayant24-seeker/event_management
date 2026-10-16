import html

from test_booking import app, client, sign_in  # noqa: F401  (fixtures)


def test_city_page_with_faq_schema(client):
    page = html.unescape(client.get("/events-in-jaipur").get_data(as_text=True))
    assert "Events in Jaipur" in page and "Jaipur Night Run 2026" in page and "Surat Street Food Fest" not in page
    assert '"@type": "FAQPage"' in page
    assert client.get("/events-in-atlantis").status_code == 404
    # Homepage city tiles and event breadcrumbs point at city pages.
    assert 'href="/events-in-jaipur"' in client.get("/").get_data(as_text=True)


def test_sitemap_and_robots(client):
    xml = client.get("/sitemap.xml").get_data(as_text=True)
    assert "/events/amer-hills-trail-ultra</loc>" in xml and "/events-in-kota</loc>" in xml
    assert "/organizers/pink-pace-runners</loc>" in xml and "/privacy</loc>" in xml
    robots = client.get("/robots.txt").get_data(as_text=True)
    assert "Disallow: /organizer" in robots and "Sitemap: http://localhost/sitemap.xml" in robots


def test_hindi_toggle(client):
    res = client.get("/lang/hi", headers={"Referer": "http://localhost/events"})
    assert res.headers["Location"] == "http://localhost/events"
    page = client.get("/").get_data(as_text=True)
    assert 'lang="hi"' in page and "अभी रजिस्टर करें" in page and "निःशुल्क" in page
    # Event details stay as the organizer wrote them.
    assert "Run the Pink City under the lights" in page
    client.get("/lang/en")
    assert 'lang="en"' in client.get("/").get_data(as_text=True)
    # Never redirects to another site.
    assert client.get("/lang/hi", headers={"Referer": "https://evil.example/"}).headers["Location"] == "/"


def test_404_page_and_headers(client):
    res = client.get("/no-such-page")
    assert res.status_code == 404 and "left the venue" in res.get_data(as_text=True)
    home = client.get("/")
    assert home.headers["X-Content-Type-Options"] == "nosniff"
    assert "app.css?v=" in home.get_data(as_text=True)
    assert client.get("/tickets").headers["Cache-Control"] == "private, no-store"


def test_installable_app_files(client):
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200 and m.json["display"] == "standalone" and len(m.json["icons"]) == 2
    for icon in m.json["icons"]:
        assert client.get(icon["src"]).status_code == 200
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.content_type and sw.headers["Cache-Control"] == "no-cache"
    assert 'rel="manifest"' in client.get("/").get_data(as_text=True)


def test_offline_page_never_shows_who_is_signed_in(client):
    sign_in(client, name="Asha Verma")
    page = client.get("/offline").get_data(as_text=True)
    assert "No internet right now" in page and "Asha" not in page
