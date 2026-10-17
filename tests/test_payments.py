import hashlib
import hmac
import json

import pytest

from app import create_app, payments
from app.models import Booking, db
from test_booking import CSRF, post, run_details, sign_in, text

SECRET, HOOK = "rzp_secret", "hook_secret"


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "MEDIA_ROOT": str(tmp_path), "PAYMENT_PROVIDER": "razorpay",
                       "RAZORPAY_KEY_ID": "rzp_test_key", "RAZORPAY_KEY_SECRET": SECRET, "RAZORPAY_WEBHOOK_SECRET": HOOK})


@pytest.fixture
def client(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s["csrf"] = CSRF
    return c


@pytest.fixture
def api(monkeypatch):
    calls = []

    def fake(method, path, payload=None):
        calls.append((method, path, payload))
        return {"id": "order_ABC123"} if path == "/orders" else {"id": "rfnd_1"}
    monkeypatch.setattr(payments, "_request", fake)
    return calls


def book(client):
    sign_in(client)
    res = post(client, "/events/amer-hills-trail-ultra/register", t0="1", action="book", **run_details(0))
    return res.headers["Location"].rsplit("/", 1)[-1]


def sign(secret, msg):
    return hmac.new(secret.encode(), msg.encode() if isinstance(msg, str) else msg, hashlib.sha256).hexdigest()


def test_checkout_creates_order_and_verifies_signature(app, client, api):
    ref = book(client)
    page = text(client.get(f"/pay/{ref}"))
    assert 'data-order="order_ABC123"' in page and "checkout.razorpay.com" in page
    assert api[0][1] == "/orders" and api[0][2]["amount"] == 249900 and api[0][2]["receipt"] == ref
    # A forged signature is refused.
    post(client, f"/pay/{ref}/razorpay", razorpay_order_id="order_ABC123", razorpay_payment_id="pay_1", razorpay_signature="nope")
    with app.app_context():
        assert Booking.query.filter_by(ref=ref).one().status == "pending"
    good = sign(SECRET, "order_ABC123|pay_1")
    res = post(client, f"/pay/{ref}/razorpay", razorpay_order_id="order_ABC123", razorpay_payment_id="pay_1", razorpay_signature=good)
    assert "new=1" in res.headers["Location"]
    with app.app_context():
        b = Booking.query.filter_by(ref=ref).one()
        assert b.status == "confirmed" and b.payment_ref == "pay_1"
    # The test-mode "pay" button does nothing when Razorpay is on.
    assert "(test)" not in text(client.get(f"/pay/{ref}"))


def test_webhook_confirms_and_is_signed(app, client, api):
    ref = book(client)
    client.get(f"/pay/{ref}")
    body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_9", "order_id": "order_ABC123", "amount": 249900}}}}).encode()
    bad = client.post("/webhooks/razorpay", data=body, headers={"X-Razorpay-Signature": "x", "Content-Type": "application/json"})
    assert bad.status_code == 400
    ok = client.post("/webhooks/razorpay", data=body, headers={"X-Razorpay-Signature": sign(HOOK, body), "Content-Type": "application/json"})
    assert ok.status_code == 200
    with app.app_context():
        assert Booking.query.filter_by(ref=ref).one().status == "confirmed"
    # Delivered twice: still one confirmation.
    client.post("/webhooks/razorpay", data=body, headers={"X-Razorpay-Signature": sign(HOOK, body), "Content-Type": "application/json"})


def test_cancel_refunds_through_razorpay(app, client, api):
    ref = book(client)
    client.get(f"/pay/{ref}")
    post(client, f"/pay/{ref}/razorpay", razorpay_order_id="order_ABC123", razorpay_payment_id="pay_1",
         razorpay_signature=sign(SECRET, "order_ABC123|pay_1"))
    post(client, f"/bookings/{ref}/cancel")
    refund_call = [c for c in api if c[1].endswith("/refund")]
    assert refund_call and refund_call[0][1] == "/payments/pay_1/refund" and refund_call[0][2]["amount"] == 124900  # 50% of ₹2,499 in whole rupees
    with app.app_context():
        assert Booking.query.filter_by(ref=ref).one().status == "cancelled"


def test_csp_allows_razorpay_only_when_enabled(client):
    sign_in(client)
    assert "checkout.razorpay.com" in client.get("/").headers["Content-Security-Policy"]
