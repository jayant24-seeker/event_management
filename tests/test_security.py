from app.auth import safe_next
from app.ratelimit import LIMITS

from test_booking import CSRF, app, client, post, sign_in, text  # noqa: F401  (fixtures)


def test_safe_next_blocks_other_sites(app):
    with app.test_request_context():
        assert safe_next("/tickets") == "/tickets"
        for bad in ("//evil.com", "/\\evil.com", "https://evil.com", "", None):
            assert safe_next(bad) == "/"


def test_otp_requests_are_limited_per_ip(client):
    limit = LIMITS["otp"][0]
    for i in range(limit):
        post(client, "/login", phone=f"98765{i:05d}")
    res = post(client, "/login", phone="9123456789")
    assert "Too many codes" in text(res)


def test_contact_form_is_limited_per_ip(client):
    msg = dict(name="Asha", reply_to="9876543210", topic="other", message="Hello there, a question.")
    for _ in range(LIMITS["contact"][0]):
        post(client, "/contact", **msg)
    assert "a lot of messages" in text(post(client, "/contact", **msg))


def test_bad_coupon_expiry_does_not_crash(client):
    sign_in(client, phone="9999999999")
    res = post(client, "/organizer/events/jaipur-night-run-2026/coupons", code="NIGHT5", percent_off="5",
               valid_until="not-a-date")
    assert res.status_code == 302
