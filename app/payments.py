"""Payments. PAYMENT_PROVIDER=test (default) keeps the test page; "razorpay" uses Razorpay
Checkout (UPI, cards, net banking, wallets) with the keys from the environment:

    RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET

Flow: create an order for the booking -> Checkout in the browser -> our callback verifies the
signature and confirms. The webhook (payment.captured) confirms too, in case the person
closes the tab before the callback. Confirming is idempotent, so both arriving is fine.
"""
import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request

from flask import current_app

API = "https://api.razorpay.com/v1"


class PaymentError(RuntimeError):
    pass


def provider():
    return current_app.config.get("PAYMENT_PROVIDER", "test")


def _request(method, path, payload=None):
    """Call the Razorpay API with the key id/secret (basic auth). Tests replace this."""
    cfg = current_app.config
    token = base64.b64encode(f"{cfg['RAZORPAY_KEY_ID']}:{cfg['RAZORPAY_KEY_SECRET']}".encode()).decode()
    req = urllib.request.Request(API + path, method=method, data=json.dumps(payload).encode() if payload else None,
                                 headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.load(res)
    except (urllib.error.URLError, ValueError) as err:
        current_app.logger.exception("Razorpay %s %s failed", method, path)
        raise PaymentError("The payment service didn't respond. Please try again.") from err


def create_order(booking):
    """Razorpay order for the booking total (in paise). Returns the order id."""
    order = _request("POST", "/orders", {"amount": booking.total * 100, "currency": "INR", "receipt": booking.ref,
                                         "notes": {"booking": booking.ref, "event": booking.event_slug}})
    return order["id"]


def _sign(secret, message):
    return hmac.new(secret.encode(), message.encode() if isinstance(message, str) else message, hashlib.sha256).hexdigest()


def verify_payment(order_id, payment_id, signature):
    """Checkout's handler returns these three; the signature proves Razorpay sent them."""
    expected = _sign(current_app.config["RAZORPAY_KEY_SECRET"], f"{order_id}|{payment_id}")
    return bool(signature) and hmac.compare_digest(expected, signature)


def verify_webhook(body, signature):
    secret = current_app.config.get("RAZORPAY_WEBHOOK_SECRET") or ""
    return bool(secret and signature) and hmac.compare_digest(_sign(secret, body), signature)


def refund(booking, amount):
    """Send money back for a cancelled booking. Test payments need nothing."""
    if amount <= 0 or not booking.payment_ref or booking.payment_ref.startswith(("TEST-", "DEMO")):
        return None
    if provider() != "razorpay":
        return None
    return _request("POST", f"/payments/{booking.payment_ref}/refund", {"amount": amount * 100})["id"]
