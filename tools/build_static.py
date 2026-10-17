"""Render the public website to static files for a GitHub Pages preview.

    python tools/build_static.py --base /event_management --host jayant24-seeker.github.io --out _site

Runs the real Flask app with the demo data, crawls every public page from the homepage and
saves it as HTML. Explore links with filters (?city=Jaipur...) become their own folders, and
pages that need a server (sign-in, booking, organizer tools) point to a short explainer page.
static/js/preview.js handles search and filter forms in the browser.
"""
import argparse
import json
import os
import re
import shutil
import sys
from collections import deque
from html import unescape
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SMS_PROVIDER", "console")

from app import create_app  # noqa: E402

SERVER_ONLY = ("/login", "/account", "/logout", "/organizer/", "/admin", "/bookings", "/pay", "/tickets",
               "/saved", "/pass/", "/t/", "/lang/", "/api/", "/sw.js", "/manifest.webmanifest")
SERVER_ONLY_SUFFIXES = ("/register", "/notify", "/questions", "/review", "/follow")
KINDS = [("city", "cities"), ("category", "categories")]
LINK = re.compile(r'(href|src|action|content)="([^"]*)"')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="", help="URL prefix, e.g. /event_management")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--out", default="_site")
    ap.add_argument("--max-pages", type=int, default=2000)
    args = ap.parse_args()
    base, out = args.base.rstrip("/"), Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    app = create_app({"TESTING": True, "DEMO_SALES": True, "STATIC_PREVIEW": True,
                      "MEDIA_ROOT": str(ROOT / "app" / "static")})
    client = app.test_client()
    env = {"SCRIPT_NAME": base, "HTTP_HOST": args.host, "wsgi.url_scheme": "https"}

    def fetch(path):
        return client.get(path, environ_overrides=env)

    filtered = {}  # "city=Jaipur&when=past" -> "/events/f/city-Jaipur-when-past/"

    def local(url):
        """Where an internal URL lives in the static site (None if it needs the server)."""
        parts = urlsplit(url)
        path = parts.path[len(base):] if base and parts.path.startswith(base) else parts.path
        if not path.startswith("/") or path.startswith("//"):
            return None
        if path.startswith(SERVER_ONLY) or path.endswith(SERVER_ONLY_SUFFIXES):
            return "/preview/"
        if parts.query and path == "/events":
            query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if k != "page" and v))
            if not query:
                return "/events"
            if query not in filtered:
                filtered[query] = "/events/f/" + re.sub(r"[^A-Za-z0-9]+", "-", query).strip("-") + "/"
            return filtered[query]
        return path

    def rewrite(html):
        def repl(m):
            attr, url = m.group(1), unescape(m.group(2))
            parts = urlsplit(url)
            if parts.scheme and parts.netloc != args.host:
                return m.group(0)
            if parts.path.startswith(f"{base}/static/") or not (parts.path.startswith(base + "/") or parts.path == base):
                return m.group(0)
            target = local(url)
            if target is None:
                return m.group(0)
            new = ("https://" + args.host if parts.netloc else "") + base + target + (f"#{parts.fragment}" if parts.fragment else "")
            return f'{attr}="{new}"'
        return LINK.sub(repl, html)

    def save(path, body):
        dest = out / path.lstrip("/")
        if path.endswith("/") or "." not in Path(path).name:
            dest = dest / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)

    seen, queue = set(), deque(["/", "/offline", "/share.png", "/sitemap.xml", "/robots.txt"])
    index = search_index(app, base)
    # Suggestions link cities and categories to their Explore pages, so make sure those exist.
    queue.extend(f"/events?{kind}={v}" for kind, key in KINDS for v in index[key])
    pages = 0
    while queue and pages < args.max_pages:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        target = local(base + url) if not url.startswith(base) else local(url)
        if target is None or target == "/preview/":
            continue
        res = fetch(url)
        if res.status_code != 200:
            print(f"  skip {url} ({res.status_code})")
            continue
        body = res.data
        if res.mimetype == "text/html":
            html = res.get_data(as_text=True)
            for _, link in LINK.findall(html):
                link = unescape(link)
                parts = urlsplit(link)
                if parts.netloc and parts.netloc != args.host:
                    continue
                if parts.path.startswith(base + "/") and not parts.path.startswith(f"{base}/static/"):
                    # Explore with up to two filters (plus the past/calendar switch) covers what
                    # people click; every combination would be thousands of pages.
                    params = [k for k, v in parse_qsl(parts.query) if v and k not in ("when", "view", "page")]
                    if len(params) > 2 or {"sort", "month"} & set(params):
                        continue
                    rel = parts.path[len(base):] + (f"?{parts.query}" if parts.query else "")
                    if rel not in seen:
                        queue.append(rel)
            body = rewrite(html).encode()
        save(target, body)
        pages += 1

    # Explainer for anything that needs the live server, and GitHub Pages' not-found page.
    save("/preview/", rewrite(fetch("/preview-only").get_data(as_text=True)).encode())
    save("/404.html", rewrite(fetch("/this-page-does-not-exist").get_data(as_text=True)).encode())
    # Search index and filter map for preview.js.
    for kind, key in KINDS:
        index[key] = [{"name": v, "url": base + local(f"/events?{kind}={v}")} for v in index[key]]
    save("/preview/search.json", json.dumps(index).encode())
    save("/preview/pages.json", json.dumps({q: base + p for q, p in filtered.items()}).encode())
    shutil.copytree(ROOT / "app" / "static", out / "static", dirs_exist_ok=True)
    (out / ".nojekyll").write_text("")
    print(f"Built {pages} pages and {len(filtered)} filtered Explore views into {out}/")


def search_index(app, base):
    from app.routes import store
    with app.test_request_context("/", base_url=f"https://localhost{base}/"):
        from flask import url_for
        s = store()
        return {
            "events": [{"title": e.title, "url": url_for("main.event", slug=e.slug),
                        "poster": url_for("static", filename=e.poster),
                        "meta": f"{e.start.strftime('%d %b')} · {e.city}",
                        "text": " ".join([e.title, e.tagline, e.city, e.category, e.venue["name"], e.org.get("name", ""),
                                          " ".join(e.raw.get("tags", []))]).lower()} for e in s.upcoming()],
            "cities": sorted({e.city for e in s.upcoming()}),
            "categories": sorted({e.category for e in s.upcoming()}),
        }


if __name__ == "__main__":
    main()
