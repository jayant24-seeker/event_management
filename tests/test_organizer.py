import html

from app.models import Attendee, Booking, ContactMessage, EventRow, Organizer, db
from test_booking import CSRF, app, client, post, sign_in, text  # noqa: F401  (fixtures)

EVENT = {
    "title": "Kota Monsoon 10K", "tagline": "A flat 10K along the Chambal", "category": "Running", "language": "Hindi",
    "start": "2026-12-27T06:00", "end": "2026-12-27T09:00", "mode": "venue", "city": "Kota",
    "venue_name": "Chambal Garden", "venue_address": "Chambal Garden, Kota, Rajasthan 324001",
    "about": "A flat and fast 10K with chip timing and breakfast at the finish.",
    "highlights": "Chip timing\nMedal for all", "schedule": "06:00 | Flag-off\n08:30 | Prizes",
    "faqs": "Is there parking? | Yes, at Gate 2.", "refund_policy": "Full refund up to 7 days before.",
    "ticket_name": ["10K", "5K"], "ticket_price": ["499", "0"], "ticket_capacity": ["300", "100"], "ticket_note": ["", ""],
    "field_gender": "1", "field_age": "1", "field_tshirt": "1",
}


def become_organizer(client):
    sign_in(client, phone="9811111111", name="Ritu Organizer")
    return post(client, "/organizer/start", name="Kota Runners Club", city="Kota",
                about="We organise city runs in Kota every monsoon and winter.")


def test_organizer_pages_need_sign_in_and_profile(client):
    assert "/login" in client.get("/organizer/").headers["Location"]
    sign_in(client)
    assert "/organizer/start" in client.get("/organizer/").headers["Location"]


def test_create_draft_publish_and_see_it_live(app, client):
    assert "/organizer/events/new" in become_organizer(client).headers["Location"]
    # Publishing with blanks and placeholder text is blocked, but the draft is kept.
    res = client.post("/organizer/events/new", data=dict(EVENT, about="TBD", venue_address="", action="publish", csrf_token=CSRF))
    page = text(res)
    assert "looks like placeholder text" in page and "Venue 'address' is required" in page
    with app.app_context():
        row = EventRow.query.filter_by(organizer_slug="kota-runners-club").one()
        assert row.status == "draft" and row.slug == "kota-monsoon-10k-2026"
        assert row.data["poster"].startswith("uploads/art/")  # original poster made for them
    assert client.get("/events/kota-monsoon-10k-2026").status_code == 404
    res = client.post("/organizer/events/kota-monsoon-10k-2026/edit", data=dict(EVENT, action="publish", csrf_token=CSRF))
    assert res.headers["Location"].endswith("/events/kota-monsoon-10k-2026")
    live = text(client.get("/events/kota-monsoon-10k-2026"))
    assert "Kota Monsoon 10K" in live and "Kota Runners Club" in live and "Flag-off" in live
    assert "Kota Monsoon 10K" in text(client.get("/events?city=Kota"))
    with app.app_context():
        assert db.session.get(EventRow, "kota-monsoon-10k-2026").data["attendee_fields"] == ["name", "gender", "age", "tshirt"]


def test_broken_edit_never_reaches_live_page(app, client):
    become_organizer(client)
    client.post("/organizer/events/new", data=dict(EVENT, action="publish", csrf_token=CSRF))
    res = client.post("/organizer/events/kota-monsoon-10k-2026/edit", data=dict(EVENT, title="Kota Monsoon 10K", about="Lorem ipsum", action="save", csrf_token=CSRF))
    assert "Not saved." in text(res)
    with app.app_context():
        row = db.session.get(EventRow, "kota-monsoon-10k-2026")
        assert row.status == "published" and "Lorem" not in row.data["about"]


def test_other_organizers_cannot_edit(app, client):
    become_organizer(client)
    assert client.get("/organizer/events/jaipur-night-run-2026/edit").status_code == 404
    assert client.get("/organizer/events/jaipur-night-run-2026/attendees.csv").status_code == 404


def test_attendees_csv_coupons_and_check_in(app, client):
    become_organizer(client)
    client.post("/organizer/events/new", data=dict(EVENT, action="publish", csrf_token=CSRF))
    post(client, "/organizer/events/kota-monsoon-10k-2026/coupons", code="rain 20", percent_off="20", max_uses="50")
    admin = text(client.get("/organizer/events/kota-monsoon-10k-2026"))
    assert "RAIN20" in admin and "No bookings yet" in admin
    # Someone books, with a name that looks like a spreadsheet formula.
    res = post(client, "/events/kota-monsoon-10k-2026/register", t1="1", action="book",
               **{"a0-name": "=HYPERLINK(1)", "a0-gender": "Male", "a0-age": "30", "a0-tshirt": "M"})
    assert "/bookings/" in res.headers["Location"]
    csv_text = client.get("/organizer/events/kota-monsoon-10k-2026/attendees.csv").get_data(as_text=True)
    assert "'=HYPERLINK(1)" in csv_text and "T-shirt size" in csv_text
    with app.app_context():
        code = Attendee.query.one().code
    page = text(client.get(f"/t/{code}"))
    assert "Organizer view" in page and "Check in" in page
    post(client, "/organizer/check-in", code=code)
    assert "Already checked in" in text(client.get(f"/t/{code}"))
    with app.app_context():
        assert Attendee.query.one().checked_in_at is not None


def test_attendee_cannot_check_in_tickets(app, client):
    sign_in(client)
    res = post(client, "/events/pushkar-sunrise-yoga/register", t0="1", action="book",
               **{"a0-name": "Asha", "a0-gender": "Female", "a0-age": "30"})
    with app.app_context():
        code = Attendee.query.one().code
    assert "Organizer view" not in text(client.get(f"/t/{code}"))
    assert post(client, "/organizer/check-in", code=code).status_code == 404


def test_demo_organizer_dashboard(app, client):
    sign_in(client, phone="9999999999")
    page = text(client.get("/organizer/"))
    assert "Pink Pace Runners Club" in page and "Jaipur Night Run 2026" in page
    # Events without a saved field list use the category defaults everywhere (runs: T-shirt, emergency...).
    header = client.get("/organizer/events/jaipur-night-run-2026/attendees.csv").get_data(as_text=True).splitlines()[0]
    assert "T-shirt size" in header and "Emergency contact" in header


def test_landing_about_and_contact(app, client):
    assert "Fill every slot" in text(client.get("/for-organizers"))
    assert "N Square Digital Solutions" in text(client.get("/about"))
    assert "Tell us a little more" in text(post(client, "/contact", name="Asha", reply_to="9876543210", message="hi"))
    assert "Thanks, Asha!" in text(post(client, "/contact", name="Asha", reply_to="9876543210", topic="organizer",
                                        message="I want to host a cyclothon in Udaipur."))
    post(client, "/contact", name="Bot", reply_to="bot@spam.com", message="Buy now buy now", website="http://spam")
    with app.app_context():
        assert ContactMessage.query.count() == 1


def test_sales_chart_with_demo_sales(tmp_path):
    from app import create_app

    demo = create_app({"TESTING": True, "DEMO_SALES": True, "MEDIA_ROOT": str(tmp_path)})
    c = demo.test_client()
    with c.session_transaction() as s:
        s["csrf"] = CSRF
    sign_in(c, phone="9999999999")
    page = text(c.get("/organizer/events/jaipur-night-run-2026"))
    assert "Tickets sold per day" in page and "data-tip=" in page and "Show as a table" in page
    past = text(c.get("/organizer/events/tricity-half-marathon-2026"))
    assert "Check-in rate" in past and "0%" not in past.split("Check-in rate")[1][:80]


def test_sales_chart_empty_state(client):
    sign_in(client, phone="9999999999")
    assert "No bookings on Eventouse yet" in text(client.get("/organizer/events/jaipur-night-run-2026"))


def test_duplicate_event_for_next_year(app, client):
    sign_in(client, phone="9999999999")
    res = post(client, "/organizer/events/tricity-half-marathon-2026/duplicate")
    assert res.status_code == 302 and "/organizer/events/tricity-half-marathon-2027/edit" in res.headers["Location"]
    with app.app_context():
        row = db.session.get(EventRow, "tricity-half-marathon-2027")
        old = db.session.get(EventRow, "tricity-half-marathon-2026")
        assert row.status == "draft" and row.data["title"] == "Tricity Half Marathon 2027"
        assert row.data["start"][:4] == "2027" and "results" not in row.data
        assert all(t["sold"] == 0 for t in row.data["tickets"])
        assert old.data["title"] == "Tricity Half Marathon 2026"  # original untouched
    assert client.get("/events/tricity-half-marathon-2027").status_code == 404  # draft, not public


def test_cannot_duplicate_someone_elses_event(client):
    become_organizer(client)
    assert post(client, "/organizer/events/tricity-half-marathon-2026/duplicate").status_code == 404


def test_group_discount_saved_from_form(app, client):
    become_organizer(client)
    post(client, "/organizer/events/new", action="draft", group_min="4", group_percent="10", **EVENT)
    post(client, "/organizer/events/new", action="draft", group_min="1", group_percent="90", **dict(EVENT, title="Kota Winter 5K"))
    with app.app_context():
        rows = {r.data["title"]: r.data for r in EventRow.query.filter_by(organizer_slug="kota-runners-club")}
        assert rows["Kota Monsoon 10K"]["group_discount"] == {"min": 4, "percent": 10}
        assert "group_discount" not in rows["Kota Winter 5K"]  # out of range: ignored


def test_attendee_list_does_not_query_per_attendee(tmp_path):
    from sqlalchemy import event

    from app import create_app

    demo = create_app({"TESTING": True, "DEMO_SALES": True, "MEDIA_ROOT": str(tmp_path)})
    c = demo.test_client()
    with c.session_transaction() as s:
        s["csrf"] = CSRF
    sign_in(c, phone="9999999999")
    queries = []
    with demo.app_context():
        event.listen(db.engine, "before_cursor_execute", lambda *a, **k: queries.append(1))
    page = c.get("/organizer/events/jaipur-night-run-2026")
    assert page.status_code == 200 and len(queries) < 30  # 70+ attendees; was ~100 queries


def test_scanner_check_in_api(app, client):
    from app.organizer import ticket_code

    assert ticket_code("https://eventouse.com/t/ab3cd5efgh") == "AB3CD5EFGH"
    assert ticket_code(" ab3cd5efgh ") == "AB3CD5EFGH"
    # A booking on the demo organizer's event.
    sign_in(client)
    with app.app_context():
        from app.models import User
        u = User.query.filter_by(phone="+919876543210").one()
        b = Booking(user_id=u.id, event_slug="jaipur-night-run-2026", status="confirmed")
        b.attendees.append(Attendee(ticket_name="5K Fun Run", price=0, details={"name": "Asha Verma"}))
        db.session.add(b)
        db.session.commit()
        code = b.attendees[0].code
    with client.session_transaction() as s:
        s.pop("uid")
    sign_in(client, phone="9999999999")
    assert client.get("/organizer/scan").status_code == 200
    call = lambda c: client.post("/organizer/check-in.json", json={"code": c}, headers={"X-CSRF-Token": CSRF}).json  # noqa: E731
    first = call(f"http://localhost/t/{code}")
    assert first["status"] == "ok" and first["name"] == "Asha Verma" and first["counts"] == {"checked": 1, "total": 1}
    assert call(code)["status"] == "already"
    assert call("NOSUCHCODE")["status"] == "unknown"
    assert client.post("/organizer/check-in.json", json={"code": code}).status_code == 400  # CSRF still required


def test_gate_staff_can_scan_but_nothing_else(app, client):
    from app.models import GateStaff

    sign_in(client, phone="9999999999")
    post(client, "/organizer/staff", name="Ravi Volunteer", phone="98111 22233")
    with app.app_context():
        assert GateStaff.query.one().phone == "+919811122233"
        b = Booking(user_id=1, event_slug="jaipur-night-run-2026", status="confirmed")
        b.attendees.append(Attendee(ticket_name="5K Fun Run", price=0, details={"name": "Asha"}))
        db.session.add(b)
        db.session.commit()
        code = b.attendees[0].code
    with client.session_transaction() as s:
        s.pop("uid")
    sign_in(client, phone="9811122233", name="Ravi Volunteer")
    assert "Scan tickets" in text(client.get("/"))
    assert client.get("/organizer/scan").status_code == 200
    res = client.post("/organizer/check-in.json", json={"code": code}, headers={"X-CSRF-Token": CSRF})
    assert res.json["status"] == "ok"
    assert "Organizer view" in text(client.get(f"/t/{code}"))
    # ...but not the dashboard, attendee lists or editing.
    assert "/organizer/start" in client.get("/organizer/").headers["Location"]
    assert client.get("/organizer/events/jaipur-night-run-2026").status_code == 302
    with app.app_context():
        staff_id = GateStaff.query.one().id
    with client.session_transaction() as s:
        s.pop("uid")
    sign_in(client, phone="9999999999")
    post(client, "/organizer/staff", remove=str(staff_id))
    with app.app_context():
        assert GateStaff.query.count() == 0


def test_dashboard_needs_attention(app, client):
    from app.models import Question, User

    sign_in(client, phone="9999999999")
    with app.app_context():
        asker = User.query.filter_by(phone="+919999999999").one()
        db.session.add(Question(event_slug="little-legs-kids-run", user_id=asker.id, name="Asha", text="Is there a stroller area?"))
        db.session.commit()
    page = text(client.get("/organizer/"))
    assert "Needs your attention" in page and "1 question waiting on Little Legs Kids Run" in page
