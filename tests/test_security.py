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


def test_content_security_policy_and_no_inline_handlers(client):
    import pathlib
    import re

    res = client.get("/events/jaipur-night-run-2026")
    csp = res.headers["Content-Security-Policy"]
    nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
    page = res.get_data(as_text=True)
    assert "object-src 'none'" in csp and "frame-ancestors 'self'" in csp
    # Every inline script carries this request's nonce; no on*="" handlers anywhere in the templates.
    for tag in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", page):
        assert f'nonce="{nonce}"' in tag
    templates = pathlib.Path(__file__).parent.parent / "app" / "templates"
    for f in templates.rglob("*.html"):
        assert not re.search(r"\son(click|submit|change|load|input)=", f.read_text()), f
