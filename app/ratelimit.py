"""Small per-IP rate limits for forms that send SMS or store what strangers type.

Counts live in memory, so each server process keeps its own. That is enough to stop one
script from sending thousands of OTP texts; put a shared store (Redis) behind `hit` if the
site ever runs many processes.
"""
import time
from collections import defaultdict, deque

from flask import current_app, request

# name: (max requests, per seconds)
LIMITS = {
    "otp": (20, 3600),       # sign-in codes asked for, any number
    "waitlist": (30, 3600),  # "notify me" sign-ups
    "contact": (10, 3600),   # contact form messages
}


def client_ip():
    # Behind a proxy (Render, Nginx) set TRUSTED_PROXY=1 so the real address is used.
    if current_app.config.get("TRUSTED_PROXY") and request.headers.get("X-Forwarded-For"):
        return request.headers["X-Forwarded-For"].split(",")[0].strip()
    return request.remote_addr or "?"


def hit(name):
    """Record one request; returns False when this IP is over the limit."""
    limit, window = LIMITS[name]
    hits = current_app.extensions.setdefault("ratelimit", defaultdict(deque))[(name, client_ip())]
    now = time.monotonic()
    while hits and hits[0] <= now - window:
        hits.popleft()
    if len(hits) >= limit:
        return False
    hits.append(now)
    return True
