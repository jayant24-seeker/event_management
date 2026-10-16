import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, abort, g, request, session

from .models import User, db


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.update(
        SITE_NAME="Eventouse",
        SECRET_KEY=os.environ.get("SECRET_KEY") or "dev-only-change-me",
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL") or f"sqlite:///{Path(app.instance_path) / 'eventouse.db'}",
        # "console" prints OTPs to the log and shows them on screen. Set to a real provider in production.
        SMS_PROVIDER=os.environ.get("SMS_PROVIDER", "console"),
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,  # poster uploads
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
    )
    # Where organizer uploads are written. Files are served from /static/uploads/.
    app.config["MEDIA_ROOT"] = app.static_folder
    if config:
        app.config.update(config)
    if app.config["SECRET_KEY"] == "dev-only-change-me" and not (app.debug or app.testing):
        app.logger.warning("SECRET_KEY is not set. Set it before going live.")

    db.init_app(app)
    with app.app_context():
        db.create_all()
        from .seed import seed_if_empty
        seed_if_empty()

    from .seed import register_cli
    register_cli(app)

    @app.template_filter("num")
    def num(amount):
        # Indian digit grouping: 1,00,000
        s = str(int(amount))
        if len(s) > 3:
            head, tail = s[:-3], s[-3:]
            groups = []
            while len(head) > 2:
                groups.insert(0, head[-2:])
                head = head[:-2]
            s = ",".join(([head] if head else []) + groups) + "," + tail
        return s

    @app.template_filter("inr")
    def inr(amount):
        return f"₹{num(amount)}"

    from .seo import event_jsonld, gcal_dates
    app.jinja_env.globals.update(event_jsonld=event_jsonld, gcal_dates=gcal_dates)

    # ---- Signed-in user and CSRF protection for every form.
    @app.before_request
    def load_user_and_check_csrf():
        uid = session.get("uid")
        g.user = db.session.get(User, uid) if uid else None
        if request.method == "POST":
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
                abort(400, "Your session expired. Please go back and try again.")

    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]

    @app.context_processor
    def globals_():
        return {"site_name": app.config["SITE_NAME"], "current_user": g.get("user"), "csrf_token": csrf_token}

    from .auth import bp as auth_bp
    from .booking import bp as booking_bp
    from .organizer import bp as org_bp
    from .routes import bp
    app.register_blueprint(bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(org_bp)
    return app
